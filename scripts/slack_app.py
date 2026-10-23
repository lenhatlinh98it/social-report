"""
slack_app.py — Slack app (Socket Mode)
  /social-report              fetch và gửi báo cáo vào channel hiện tại (kèm nút Refresh)
  /social-channels ...        quản lý danh sách kênh trong config/channels.json
  Gửi tự động hằng ngày lúc schedule_time (channels.json) vào slack.channel
Chạy: python scripts/slack_app.py
"""
import os, re, shlex, sys, threading, time, logging
from datetime import datetime, timedelta
import pytz
import requests

from config import load_config, load_env, update_config
from fetch_stats import fetch_report
from send_slack import build_message

REFRESH_ACTION = "refresh_report"
SCHEDULE_WINDOW = timedelta(hours=2)  # máy bật muộn trong khoảng này vẫn gửi báo cáo sáng

USAGE = (
    "*Cách dùng `/social-channels`:*\n"
    "• `/social-channels list`\n"
    "• `/social-channels add youtube <url hoặc @handle> [\"Tên hiển thị\"]`\n"
    "• `/social-channels add tiktok @username [\"Tên hiển thị\"]`\n"
    "• `/social-channels remove <tên | url | @username>`"
)

_fetch_lock = threading.Lock()
log = logging.getLogger("social-report")

# ─── REPORT ───────────────────────────────────────────────────────────────────

def build_report_text():
    try:
        return build_message(fetch_report(load_config()))
    except Exception as e:
        log.exception("Fetch report thất bại")
        return f"⚠️ *[ERROR] Social Morning Report thất bại*\n```{str(e)[:500]}```"

def report_blocks(text):
    # Section block giới hạn 3000 ký tự → chia nhỏ theo dòng
    blocks, chunk = [], ""
    for line in text.split("\n"):
        if chunk and len(chunk) + len(line) + 1 > 2900:
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": chunk}})
            chunk = ""
        chunk += line + "\n"
    if chunk.strip():
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": chunk}})
    blocks.append({"type": "actions", "elements": [{
        "type": "button", "action_id": REFRESH_ACTION,
        "text": {"type": "plain_text", "text": "🔄 Refresh"},
    }]})
    return blocks

def _respond_report(respond):
    try:
        text = build_report_text()
        respond(replace_original=True, response_type="in_channel", text=text, blocks=report_blocks(text))
    finally:
        _fetch_lock.release()

def post_scheduled_report(client, channel):
    with _fetch_lock:
        text = build_report_text()
    client.chat_postMessage(channel=channel, text=text, blocks=report_blocks(text))

def schedule_loop(client):
    last_sent = None
    while True:
        try:
            cfg = load_config()
            schedule_time = cfg.get("schedule_time")
            if schedule_time:
                now = datetime.now(pytz.timezone(cfg["timezone"]))
                hh, mm = map(int, schedule_time.split(":"))
                due = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
                if last_sent != now.date() and due <= now < due + SCHEDULE_WINDOW:
                    last_sent = now.date()
                    post_scheduled_report(client, cfg["slack"]["channel"])
                    log.info("Đã gửi báo cáo định kỳ vào %s", cfg["slack"]["channel"])
        except Exception:
            log.exception("Gửi báo cáo định kỳ thất bại")
        time.sleep(30)

# ─── CHANNELS ─────────────────────────────────────────────────────────────────

def parse_args(text):
    # Bỏ format link của Slack (<url|label>) và dấu nháy cong do client tự đổi
    text = re.sub(r"<([^|>]+)(\|[^>]*)?>", r"\1", text or "")
    text = text.translate(str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"}))
    return shlex.split(text)

def normalize_youtube(value):
    if value.startswith("@"):
        return f"https://www.youtube.com/{value}/shorts"
    if not re.match(r"^https?://(www\.|m\.)?youtube\.com/", value):
        raise ValueError("URL YouTube không hợp lệ (cần dạng https://www.youtube.com/@handle hoặc @handle)")
    return value

def check_youtube(url):
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True, "extract_flat": True, "playlistend": 1, "ignoreerrors": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        raise ValueError(f"Không truy cập được kênh YouTube: {url}")
    return info.get("channel") or info.get("uploader") or url

def check_tiktok(username, cfg):
    api_key, api_host = cfg["tiktok"].get("rapidapi_key"), cfg["tiktok"].get("rapidapi_host", "tiktok-scraper7.p.rapidapi.com")
    if not api_key:
        raise ValueError("Chưa cấu hình RAPIDAPI_KEY trong .env")
    r = requests.get(f"https://{api_host}/user/info", params={"unique_id": username},
                     headers={"X-RapidAPI-Key": api_key, "X-RapidAPI-Host": api_host}, timeout=15)
    r.raise_for_status()
    data = r.json()
    if data.get("code", 0) != 0:
        raise ValueError(f"Không tìm thấy TikTok {username}: {data.get('msg')}")
    return ((data.get("data") or {}).get("user") or {}).get("nickname") or username

def list_channels(cfg):
    lines = ["📺 *YouTube*"]
    lines += [f"• {c['name']} — {c['channel_url']}" for c in cfg["youtube"]["channels"]] or ["• (trống)"]
    lines.append("🎵 *TikTok*")
    lines += [f"• {c['name']} — {c['username']}" for c in cfg["tiktok"]["channels"]] or ["• (trống)"]
    return "\n".join(lines)

def add_channel(platform, value, name, cfg):
    if platform == "youtube":
        url = normalize_youtube(value)
        if any(c["channel_url"].lower() == url.lower() for c in cfg["youtube"]["channels"]):
            raise ValueError(f"Kênh đã có trong danh sách: {url}")
        channel_title = check_youtube(url)
        entry = {"name": name or f"Youtube {channel_title}", "channel_url": url}
    elif platform == "tiktok":
        username = "@" + value.lstrip("@")
        if any(c["username"].lower() == username.lower() for c in cfg["tiktok"]["channels"]):
            raise ValueError(f"Kênh đã có trong danh sách: {username}")
        nickname = check_tiktok(username, cfg)
        entry = {"name": name or f"TikTok {nickname}", "username": username}
    else:
        raise ValueError("Nền tảng phải là `youtube` hoặc `tiktok`")

    update_config(lambda c: c[platform]["channels"].append(entry))
    target = entry.get("channel_url") or entry["username"]
    return f"✅ Đã thêm {platform}: *{entry['name']}* ({target})"

def remove_channel(key):
    k = key.lower()
    def matches(c):
        return k in (c["name"].lower(), c.get("channel_url", "").lower(), c.get("username", "").lower().lstrip("@")) \
            or k.lstrip("@") == c.get("username", "").lower().lstrip("@")

    def mutate(cfg):
        removed = []
        for platform in ("youtube", "tiktok"):
            keep = [c for c in cfg[platform]["channels"] if not matches(c)]
            removed += [c["name"] for c in cfg[platform]["channels"] if matches(c)]
            cfg[platform]["channels"] = keep
        return removed

    removed = update_config(mutate)
    if not removed:
        raise ValueError(f"Không tìm thấy kênh: {key}")
    return "🗑 Đã xóa: " + ", ".join(f"*{n}*" for n in removed)

def handle_channels_command(text):
    """Trả về (message, public). public=True → hiển thị cho cả channel."""
    try:
        args = parse_args(text)
    except ValueError:
        return USAGE, False
    if not args or args[0] in ("help", "list"):
        return (list_channels(load_config()) if args else USAGE), False
    try:
        if args[0] == "add" and len(args) in (3, 4):
            return add_channel(args[1].lower(), args[2], args[3] if len(args) == 4 else None, load_config()), True
        if args[0] == "remove" and len(args) == 2:
            return remove_channel(args[1]), True
    except ValueError as e:
        return f"❌ {e}", False
    except Exception as e:
        log.exception("/social-channels thất bại")
        return f"❌ Lỗi: {str(e)[:300]}", False
    return USAGE, False

def is_allowed(user_id):
    allowed = [u.strip() for u in os.environ.get("ALLOWED_USER_IDS", "").split(",") if u.strip()]
    return not allowed or user_id in allowed

# ─── SLACK APP ────────────────────────────────────────────────────────────────

def register(app):
    @app.command("/social-report")
    def on_report(ack, respond):
        if not _fetch_lock.acquire(blocking=False):
            ack("⏳ Report đang được fetch, chờ chút nhé.")
            return
        ack()
        respond(response_type="in_channel", text="⏳ Đang fetch số liệu YouTube/TikTok…")
        threading.Thread(target=_respond_report, args=(respond,), daemon=True).start()

    @app.action(REFRESH_ACTION)
    def on_refresh(ack, respond):
        ack()
        if not _fetch_lock.acquire(blocking=False):
            respond(response_type="ephemeral", replace_original=False, text="⏳ Report đang được fetch, chờ chút nhé.")
            return
        respond(replace_original=True, text="⏳ Đang cập nhật số liệu…")
        threading.Thread(target=_respond_report, args=(respond,), daemon=True).start()

    @app.command("/social-channels")
    def on_channels(ack, respond, command):
        text = command.get("text", "")
        if text.strip().split(" ")[0] in ("add", "remove") and not is_allowed(command.get("user_id")):
            ack("❌ Bạn không có quyền thay đổi danh sách kênh.")
            return
        ack("⏳ Đang xử lý…" if text.strip().startswith("add") else None)

        def work():
            msg, public = handle_channels_command(text)
            respond(response_type="in_channel" if public else "ephemeral", text=msg)
        threading.Thread(target=work, daemon=True).start()

def main():
    from slack_bolt import App
    from slack_bolt.adapter.socket_mode import SocketModeHandler

    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(message)s")
    load_env()
    bot_token, app_token = os.environ.get("SLACK_BOT_TOKEN"), os.environ.get("SLACK_APP_TOKEN")
    if not bot_token or not app_token:
        sys.exit("❌ Thiếu SLACK_BOT_TOKEN hoặc SLACK_APP_TOKEN trong .env")

    app = App(token=bot_token)
    register(app)
    threading.Thread(target=schedule_loop, args=(app.client,), daemon=True).start()
    log.info("Slack app đang chạy (Socket Mode)…")
    SocketModeHandler(app, app_token).start()

if __name__ == "__main__":
    main()
