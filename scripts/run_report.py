"""
run_report.py — Pipeline đầy đủ: fetch → format → gửi Slack
Dùng cho cron job hoặc trigger thủ công
"""
import subprocess, sys, os, json
from datetime import datetime
import pytz

BASE = os.path.dirname(__file__)
LOG_DIR     = os.path.join(BASE, "../logs")
os.makedirs(LOG_DIR, exist_ok=True)

def log_error(msg):
    log_file = os.path.join(LOG_DIR, "errors.log")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")
    print(f"[ERROR] {msg}", file=sys.stderr)

def main():
    dry_run = "--dry-run" in sys.argv
    extra   = ["--dry-run"] if dry_run else []

    try:
        # Step 1: Fetch stats
        fetch = subprocess.run(
            [sys.executable, os.path.join(BASE, "fetch_stats.py")] + extra,
            capture_output=True, text=True, timeout=120
        )
        if fetch.returncode != 0:
            raise Exception(f"fetch_stats.py thất bại:\n{fetch.stderr}")

        if dry_run:
            print(fetch.stdout)
            return

        # Step 2: Gửi Slack
        send = subprocess.run(
            [sys.executable, os.path.join(BASE, "send_slack.py")],
            input=fetch.stdout,
            capture_output=True, text=True, timeout=30
        )
        if send.returncode != 0:
            raise Exception(f"send_slack.py thất bại:\n{send.stderr}")

        print(send.stdout)

    except Exception as e:
        err_msg = str(e)
        log_error(err_msg)

        # Gửi error notification vào Slack
        try:
            from config import load_config
            cfg = load_config()
            import requests
            requests.post(cfg["slack"]["webhook_url"], json={
                "text": f"⚠️ *[ERROR] Social Morning Report thất bại*\n```{err_msg[:500]}```"
            }, timeout=10)
        except Exception:
            pass

        sys.exit(1)

if __name__ == "__main__":
    main()