---
name: social-morning-report
description: >
  Tổng hợp stats video hôm qua từ các kênh YouTube và TikTok đã config,
  gửi báo cáo chi tiết vào Slack mỗi sáng. Trigger khi user nhắn
  "morning report", "báo cáo social", "thống kê kênh", hoặc "social stats".
version: 1.0.0
author: DevNta
requires:
  bins:
    - python3
---

## Purpose

Mỗi sáng hoặc khi được yêu cầu, skill này sẽ:
1. Lấy danh sách video đăng hôm qua từ các kênh YouTube và TikTok trong config
2. Tổng hợp views, comments, likes của từng video
3. Gửi báo cáo vào Slack channel đã chỉ định

## Trigger Phrases

Kích hoạt khi user nhắn một trong các câu sau:
- "Morning report"
- "Báo cáo social hôm nay"
- "Thống kê kênh hôm qua"
- "Social stats"
- "Gửi báo cáo"

## Setup

Config file: `scripts/../config/channels.json`
- Điền `youtube.channels[].channel_url` và `tiktok.channels[].username` (hoặc dùng `/social-channels` trong Slack)
- `schedule_time` (HH:MM, theo `timezone`): giờ Slack app tự gửi báo cáo vào `slack.channel`

Secrets: copy `.env.example` → `.env`, điền `SLACK_WEBHOOK_URL`, `RAPIDAPI_KEY`
(và `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN` nếu dùng Slack app)

### Slack app (Cloudflare Worker + GitHub Actions)
Slack → `worker/` (verify chữ ký, trả lời trong 3s) → GitHub Actions `.github/workflows/slack.yml`
→ `scripts/gh_runner.py` fetch và trả report về Slack. Lịch 08:30 chạy bằng cron của workflow.

1. Push project lên GitHub repo **private** (`.env` đã nằm trong `.gitignore`)
2. Repo → Settings → Secrets and variables → Actions: thêm `SLACK_BOT_TOKEN`, `RAPIDAPI_KEY`
3. Tạo fine-grained PAT chỉ cho repo này: `Actions: Read and write`, `Contents: Read`
4. Trong `worker/`: sửa `GITHUB_REPO` ở `wrangler.toml`, rồi
   `npx wrangler login`, `npx wrangler secret put SLACK_SIGNING_SECRET`,
   `npx wrangler secret put GITHUB_TOKEN`, `npx wrangler deploy`
5. Slack app → App Manifest: dán `config/slack-manifest.yaml` (thay `WORKER_URL`)
6. `/invite @Social Report` vào `slack.channel`

Chạy local (Socket Mode, cần bật lại `socket_mode_enabled`): `python scripts/slack_app.py`

## Instructions

### Trigger thủ công

Khi user yêu cầu báo cáo:

1. Chạy script fetch:
   ```
   python C:\Users\DevNta_stt\AppData\Roaming\npm\node_modules\openclaw\skills\social-morning-report\scripts\run_report.py
   ```
2. Nếu thành công, thông báo: "✅ Đã gửi báo cáo Social Media vào Slack"
3. Nếu lỗi, đọc file log tại `scripts/../logs/errors.log` và báo lỗi cho user

### Dry run (test không gửi Slack)

```
python C:\Users\DevNta_stt\AppData\Roaming\npm\node_modules\openclaw\skills\social-morning-report\scripts\run_report.py --dry-run
```

## Rules

- Không bao giờ log hoặc hiển thị API keys
- Không gửi Slack nếu không có dữ liệu
- Báo lỗi rõ ràng nếu script thất bại
- Không tự sửa `config/channels.json` khi không được yêu cầu