# Social Morning Report

Collects **yesterday’s** YouTube and TikTok video stats and posts a Slack report each morning (or on demand).

The report includes views, comments, and likes per channel. Only videos published on the previous calendar day (in the configured timezone) are counted.

## How it works

Production flow:

```
Slack slash command / Refresh button
        ↓
Cloudflare Worker (verify signature, respond within 3s)
        ↓
GitHub Actions (.github/workflows/slack.yml)
        ↓
scripts/gh_runner.py  →  fetch YouTube (yt-dlp) + TikTok (RapidAPI)
        ↓
chat.postMessage / response_url  →  Slack
```

The scheduled run uses the workflow cron (default 08:30 in `Asia/Ho_Chi_Minh`). It does not depend on a local machine staying on.

You can also run locally: dry-run, Incoming Webhook, or Slack Socket Mode.

## Repository layout

```
config/
  channels.json          # timezone, Slack channel, channel list, schedule time
  slack-manifest.yaml    # Slack App Manifest (replace WORKER_URL)
scripts/
  fetch_stats.py         # YouTube + TikTok stats
  send_slack.py          # format message, send Incoming Webhook
  run_report.py          # pipeline: fetch → Slack
  slack_app.py           # Socket Mode (local)
  gh_runner.py           # GitHub Actions entrypoint
  config.py              # load channels.json + .env
  requirements.txt
worker/
  src/index.js           # Cloudflare Worker for Slack
  wrangler.toml
.github/workflows/slack.yml
.env.example
```

## Requirements

- Python 3.11+
- Slack workspace (Incoming Webhook and/or Slack app)
- [RapidAPI](https://rapidapi.com/) key for TikTok (`tiktok-scraper7`)
- Production: GitHub repo (preferably private), Cloudflare Workers, GitHub PAT

## Local setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r scripts/requirements.txt
```

Copy secrets:

```bash
cp .env.example .env
```

Fill in `.env` (never commit this file):

| Variable | Used for |
|----------|----------|
| `SLACK_WEBHOOK_URL` | Incoming Webhook (`run_report.py`) |
| `RAPIDAPI_KEY` | TikTok fetch |
| `SLACK_BOT_TOKEN` | Bot API (`xoxb-…`) — Slack app / Actions |
| `SLACK_APP_TOKEN` | Local Socket Mode (`xapp-…`) |
| `ALLOWED_USER_IDS` | Slack user IDs allowed to add/remove channels; empty = anyone |

## Channel config

Edit `config/channels.json`. Use your own handles and URLs — examples below are placeholders:

```json
{
  "timezone": "Asia/Ho_Chi_Minh",
  "schedule_time": "08:30",
  "slack": {
    "channel": "#your-channel"
  },
  "youtube": {
    "channels": [
      {
        "name": "Example YouTube",
        "channel_url": "https://www.youtube.com/@yourhandle/shorts"
      }
    ]
  },
  "tiktok": {
    "rapidapi_host": "tiktok-scraper7.p.rapidapi.com",
    "channels": [
      {
        "name": "Example TikTok",
        "username": "@yourhandle"
      }
    ]
  }
}
```

- YouTube: Shorts tab URL or `/videos`. Only videos whose `upload_date` is yesterday are included.
- TikTok: username with or without `@`.
- `schedule_time`: local Socket Mode send time. Production uses workflow cron `30 1 * * *` (08:30 UTC+7).
- Webhook URL and RapidAPI key are **not** stored in JSON; they come from `.env` / GitHub Secrets.

You can also add/remove channels from Slack with `/social-channels`. On Actions, those changes are committed back to `channels.json`.

## Manual runs

Dry-run (print JSON, do not post to Slack):

```bash
python scripts/run_report.py --dry-run
```

Fetch only:

```bash
python scripts/fetch_stats.py --dry-run
```

Send via Incoming Webhook:

```bash
python scripts/run_report.py
```

Errors are appended to `logs/errors.log` (gitignored).

Local Slack app (Socket Mode — enable `socket_mode_enabled` on the app and set `SLACK_APP_TOKEN`):

```bash
python scripts/slack_app.py
```

## Slack commands

| Command | Purpose |
|---------|---------|
| `/social-report` | Fetch and post yesterday’s report in the current channel (~1 min) |
| **Refresh** on the report message | Re-fetch and replace the message |
| `/social-channels list` | List channels (ephemeral) |
| `/social-channels add youtube <url or @handle> ["Display name"]` | Add YouTube |
| `/social-channels add tiktok @username ["Display name"]` | Add TikTok |
| `/social-channels remove <name \| url \| @username>` | Remove a channel |

Invite the bot: `/invite @Social Report`.

## Production deploy (Worker + Actions)

1. Push a **private** repo (`.env` is already in `.gitignore`).
2. GitHub → Settings → Secrets and variables → Actions: `SLACK_BOT_TOKEN`, `RAPIDAPI_KEY`.
3. Create a fine-grained PAT for this repo only: `Actions: Read and write`, `Contents: Read`.
4. Set `GITHUB_REPO` in `worker/wrangler.toml` (`owner/repo`).
5. Deploy the Worker:

   ```bash
   cd worker
   npx wrangler login
   npx wrangler secret put SLACK_SIGNING_SECRET
   npx wrangler secret put GITHUB_TOKEN
   npx wrangler deploy
   ```

6. Slack → [App Manifest](https://api.slack.com/apps) → paste `config/slack-manifest.yaml`, replace `WORKER_URL` with the Worker URL.
7. Install the app and invite the bot into `slack.channel`.

Flow: Slack → Worker → `slack.yml` → `gh_runner.py` → report. The workflow cron posts to the channel in `channels.json`.

## Data sources

- **YouTube:** [yt-dlp](https://github.com/yt-dlp/yt-dlp); no YouTube Data API key. If a channel had no uploads yesterday, the report says there were no new videos.
- **TikTok:** RapidAPI host `tiktok-scraper7.p.rapidapi.com`. Missing `RAPIDAPI_KEY` produces a config error per TikTok channel.

## Security

- Do not commit `.env`, tokens, webhooks, or RapidAPI keys.
- The Worker verifies Slack request signatures before handling anything.
- `ALLOWED_USER_IDS` (local `.env` or Worker vars in `wrangler.toml`) restricts who can change the channel list.
