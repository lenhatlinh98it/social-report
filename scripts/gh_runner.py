"""
gh_runner.py — Entry point cho GitHub Actions (Cloudflare Worker trigger hoặc chạy theo lịch)
  python gh_runner.py report     # RESPONSE_URL: gửi report mới vào channel đã gõ lệnh
  python gh_runner.py refresh    # RESPONSE_URL: thay tin nhắn report cũ bằng số liệu mới
  python gh_runner.py channels   # RESPONSE_URL + COMMAND_TEXT: /social-channels add|remove
  python gh_runner.py scheduled  # SLACK_BOT_TOKEN: gửi report vào slack.channel trong channels.json
"""
import os, sys
import requests

from config import load_config
from slack_app import build_report_text, report_blocks, handle_channels_command

def post_response(payload):
    r = requests.post(os.environ["RESPONSE_URL"], json=payload, timeout=15)
    r.raise_for_status()

def post_to_channel(channel, text):
    r = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": f"Bearer {os.environ['SLACK_BOT_TOKEN']}"},
        json={"channel": channel, "text": text, "blocks": report_blocks(text)},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise Exception(f"chat.postMessage lỗi: {data.get('error')}")

def main():
    action = sys.argv[1] if len(sys.argv) > 1 else ""

    if action in ("report", "refresh"):
        text = build_report_text()
        post_response({
            "response_type": "in_channel",
            "replace_original": action == "refresh",
            "text": text,
            "blocks": report_blocks(text),
        })
    elif action == "channels":
        msg, public = handle_channels_command(os.environ.get("COMMAND_TEXT", ""))
        post_response({"response_type": "in_channel" if public else "ephemeral", "text": msg})
    elif action == "scheduled":
        post_to_channel(load_config()["slack"]["channel"], build_report_text())
    else:
        sys.exit(f"Action không hợp lệ: {action!r}")

if __name__ == "__main__":
    main()
