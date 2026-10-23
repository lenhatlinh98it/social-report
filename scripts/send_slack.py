"""
send_slack.py — Format và gửi báo cáo vào Slack
Nhận JSON từ stdin hoặc từ fetch_stats.py
"""
import json, sys, os
import requests
from config import load_config

def fmt_num(n):
    return f"{n:,}"

def build_message(data):
    lines = [f"📊 *Báo cáo Social Media — {data['date']}*\n"]

    # YouTube
    lines.append("━━━━━━━━━━━━━━━━━")
    lines.append("📺 *YouTube*")
    lines.append("━━━━━━━━━━━━━━━━━")
    for ch in data.get("youtube", []):
        if "error" in ch:
            lines.append(f"*{ch['name']}* — ❌ Lỗi: {ch['error']}")
            continue
        if not ch["videos"]:
            lines.append(f"*{ch['name']}* — Không có video mới hôm qua")
            continue
        lines.append(f"*{ch['name']}* — Tổng view hôm qua: *{fmt_num(ch['total_views'])}*")
        for i, v in enumerate(ch["videos"], 1):
            lines.append(
                f"  {i}. {v['title']}\n"
                f"     👁 {fmt_num(v['views'])} views  "
                f"💬 {fmt_num(v['comments'])} comments  "
                f"❤️ {fmt_num(v['likes'])} likes"
            )

    lines.append("")

    # TikTok
    lines.append("━━━━━━━━━━━━━━━━━")
    lines.append("🎵 *TikTok*")
    lines.append("━━━━━━━━━━━━━━━━━")
    for ch in data.get("tiktok", []):
        if "error" in ch:
            lines.append(f"*{ch['name']}* — ❌ Lỗi: {ch['error']}")
            continue
        if not ch["videos"]:
            lines.append(f"*{ch['name']}* — Không có video mới hôm qua")
            continue
        lines.append(f"*{ch['name']}* — Tổng view hôm qua: *{fmt_num(ch['total_views'])}*")
        for i, v in enumerate(ch["videos"], 1):
            lines.append(
                f"  {i}. {v['title']}\n"
                f"     👁 {fmt_num(v['views'])} views  "
                f"💬 {fmt_num(v['comments'])} comments  "
                f"❤️ {fmt_num(v['likes'])} likes"
            )

    lines.append("")

    # Grand total
    grand_total = (
        sum(ch["total_views"] for ch in data.get("youtube", []))
        + sum(ch["total_views"] for ch in data.get("tiktok", []))
    )
    lines.append("━━━━━━━━━━━━━━━━━")
    lines.append(f"📌 *Tổng tất cả kênh: {fmt_num(grand_total)} views*")

    return "\n".join(lines)

def send_to_slack(webhook_url, message):
    payload = {"text": message, "mrkdwn": True}
    r = requests.post(webhook_url, json=payload, timeout=10)
    if r.status_code != 200:
        raise Exception(f"Slack trả về {r.status_code}: {r.text}")

def main():
    cfg = load_config()
    raw = sys.stdin.read()
    if not raw.strip():
        print("❌ Không có dữ liệu từ stdin.", file=sys.stderr)
        sys.exit(1)

    data = json.loads(raw)
    msg  = build_message(data)

    # Preview nếu dry-run
    if "--dry-run" in sys.argv:
        print("[DRY RUN] Tin nhắn sẽ gửi:")
        print(msg)
        return

    send_to_slack(cfg["slack"]["webhook_url"], msg)
    print("✅ Đã gửi báo cáo vào Slack thành công!")

if __name__ == "__main__":
    main()