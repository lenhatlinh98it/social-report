/**
 * Cloudflare Worker — nhận request từ Slack, trả lời trong 3s và trigger GitHub Actions
 *   /social-report            → workflow action=report
 *   nút 🔄 Refresh            → workflow action=refresh
 *   /social-channels list     → đọc config/channels.json từ GitHub, trả lời ngay
 *   /social-channels add|remove → workflow action=channels (validate + commit config)
 */

const REFRESH_ACTION = "refresh_report";

const USAGE = [
  "*Cách dùng `/social-channels`:*",
  "• `/social-channels list`",
  "• `/social-channels add youtube <url hoặc @handle> [\"Tên hiển thị\"]`",
  "• `/social-channels add tiktok @username [\"Tên hiển thị\"]`",
  "• `/social-channels remove <tên | url | @username>`",
].join("\n");

export default {
  async fetch(request, env, ctx) {
    if (request.method !== "POST") return new Response("OK");

    const body = await request.text();
    if (!(await verifySlackSignature(request, body, env.SLACK_SIGNING_SECRET))) {
      return new Response("invalid signature", { status: 401 });
    }

    const form = new URLSearchParams(body);
    if (form.has("payload")) {
      return handleInteraction(JSON.parse(form.get("payload")), env, ctx);
    }
    return handleCommand(form, env, ctx);
  },
};

// ─── SLACK ────────────────────────────────────────────────────────────────────

async function verifySlackSignature(request, body, secret) {
  const ts = request.headers.get("x-slack-request-timestamp");
  const signature = request.headers.get("x-slack-signature") || "";
  if (!secret || !ts || Math.abs(Date.now() / 1000 - Number(ts)) > 300) return false;

  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"],
  );
  const mac = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(`v0:${ts}:${body}`));
  const expected = "v0=" + [...new Uint8Array(mac)].map((b) => b.toString(16).padStart(2, "0")).join("");

  if (expected.length !== signature.length) return false;
  let diff = 0;
  for (let i = 0; i < expected.length; i++) diff |= expected.charCodeAt(i) ^ signature.charCodeAt(i);
  return diff === 0;
}

function slackJson(payload) {
  return new Response(JSON.stringify(payload), { headers: { "content-type": "application/json" } });
}

async function postResponse(responseUrl, payload) {
  await fetch(responseUrl, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
}

async function handleCommand(form, env, ctx) {
  const command = form.get("command");
  const text = (form.get("text") || "").trim();
  const responseUrl = form.get("response_url");

  if (command === "/social-report") {
    triggerInBackground(ctx, env, responseUrl, { action: "report" });
    return slackJson({ response_type: "ephemeral", text: "⏳ Đang fetch số liệu YouTube/TikTok… (~1 phút)" });
  }

  if (command === "/social-channels") {
    const sub = text.split(/\s+/)[0];
    if (sub === "list") {
      return slackJson({ response_type: "ephemeral", text: await listChannels(env) });
    }
    if (sub === "add" || sub === "remove") {
      if (!isAllowed(env, form.get("user_id"))) {
        return slackJson({ response_type: "ephemeral", text: "❌ Bạn không có quyền thay đổi danh sách kênh." });
      }
      triggerInBackground(ctx, env, responseUrl, { action: "channels", text });
      return slackJson({ response_type: "ephemeral", text: "⏳ Đang xử lý… (~1 phút)" });
    }
    return slackJson({ response_type: "ephemeral", text: USAGE });
  }

  return slackJson({ response_type: "ephemeral", text: `Lệnh không hỗ trợ: ${command}` });
}

function handleInteraction(payload, env, ctx) {
  const action = (payload.actions || [])[0];
  if (payload.type === "block_actions" && action && action.action_id === REFRESH_ACTION) {
    ctx.waitUntil(
      postResponse(payload.response_url, { replace_original: true, text: "⏳ Đang cập nhật số liệu… (~1 phút)" })
        .then(() => dispatchWorkflow(env, { action: "refresh", response_url: payload.response_url }))
        .catch((e) => reportError(payload.response_url, e)),
    );
  }
  return new Response("", { status: 200 });
}

function isAllowed(env, userId) {
  const allowed = (env.ALLOWED_USER_IDS || "").split(",").map((s) => s.trim()).filter(Boolean);
  return allowed.length === 0 || allowed.includes(userId);
}

// ─── GITHUB ───────────────────────────────────────────────────────────────────

function githubHeaders(env, accept = "application/vnd.github+json") {
  return {
    Authorization: `Bearer ${env.GITHUB_TOKEN}`,
    Accept: accept,
    "User-Agent": "social-report-worker",
    "X-GitHub-Api-Version": "2022-11-28",
  };
}

async function dispatchWorkflow(env, inputs) {
  const url = `https://api.github.com/repos/${env.GITHUB_REPO}/actions/workflows/${env.WORKFLOW_FILE}/dispatches`;
  const r = await fetch(url, {
    method: "POST",
    headers: { ...githubHeaders(env), "content-type": "application/json" },
    body: JSON.stringify({ ref: env.GITHUB_REF, inputs }),
  });
  if (!r.ok) throw new Error(`GitHub ${r.status}: ${(await r.text()).slice(0, 200)}`);
}

function triggerInBackground(ctx, env, responseUrl, inputs) {
  ctx.waitUntil(
    dispatchWorkflow(env, { ...inputs, response_url: responseUrl }).catch((e) => reportError(responseUrl, e)),
  );
}

async function reportError(responseUrl, err) {
  await postResponse(responseUrl, {
    response_type: "ephemeral",
    replace_original: false,
    text: `❌ Không trigger được GitHub Actions: ${String(err.message || err).slice(0, 300)}`,
  });
}

async function listChannels(env) {
  const url = `https://api.github.com/repos/${env.GITHUB_REPO}/contents/config/channels.json?ref=${env.GITHUB_REF}`;
  const r = await fetch(url, { headers: githubHeaders(env, "application/vnd.github.raw+json") });
  if (!r.ok) return `❌ Không đọc được channels.json từ GitHub (${r.status})`;
  const cfg = await r.json();

  const yt = cfg.youtube.channels.map((c) => `• ${c.name} — ${c.channel_url}`);
  const tt = cfg.tiktok.channels.map((c) => `• ${c.name} — ${c.username}`);
  return ["📺 *YouTube*", ...(yt.length ? yt : ["• (trống)"]), "🎵 *TikTok*", ...(tt.length ? tt : ["• (trống)"])].join("\n");
}
