"""
fetch_stats.py — Lấy stats video hôm qua từ YouTube và TikTok
"""
import json, sys, os, time
from datetime import datetime, timedelta
import pytz
import requests
from config import load_config

# ─── YOUTUBE (via yt-dlp, không cần API key) ──────────────────────────────────

def fetch_youtube_channel(channel_url, channel_name, tz_name):
    import yt_dlp
    tz = pytz.timezone(tz_name)
    now = datetime.now(tz)
    yesterday = now - timedelta(days=1)
    date_str = yesterday.strftime("%Y%m%d")

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "daterange": yt_dlp.DateRange(date_str, date_str),
        "playlistend": 20,
        "ignoreerrors": True,
    }

    videos = []
    total_views = 0

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(channel_url, download=False)
        if not info:
            raise Exception("Không truy cập được kênh (sai URL hoặc kênh không tồn tại)")
        if "entries" not in info:
            return {"name": channel_name, "videos": [], "total_views": 0}

        for entry in info["entries"]:
            if not entry:
                continue
            upload_date = entry.get("upload_date", "")
            if upload_date != date_str:
                continue
            views    = entry.get("view_count",    0) or 0
            comments = entry.get("comment_count", 0) or 0
            likes    = entry.get("like_count",    0) or 0
            total_views += views
            videos.append({
                "title":    entry.get("title", "Không có tiêu đề"),
                "views":    views,
                "comments": comments,
                "likes":    likes,
            })

    videos.sort(key=lambda x: x["views"], reverse=True)
    return {"name": channel_name, "videos": videos, "total_views": total_views}

def fetch_all_youtube(cfg):
    results = []
    tz_name = cfg["timezone"]
    for ch in cfg["youtube"]["channels"]:
        try:
            data = fetch_youtube_channel(ch["channel_url"], ch["name"], tz_name)
            results.append(data)
        except Exception as e:
            results.append({"name": ch["name"], "error": str(e), "videos": [], "total_views": 0})
    return results

# ─── TIKTOK (via tiktok-scraper7 / tikwm trên RapidAPI) ───────────────────────

def fetch_tiktok_channel(username, channel_name, api_key, api_host, tz_name):
    tz = pytz.timezone(tz_name)
    now = datetime.now(tz)
    yesterday_start = (now - timedelta(days=1)).replace(hour=0,  minute=0,  second=0,  microsecond=0)
    yesterday_end   = yesterday_start.replace(           hour=23, minute=59, second=59)

    clean = username.lstrip("@")
    headers = {
        "X-RapidAPI-Key":  api_key,
        "X-RapidAPI-Host": api_host,
    }

    url = f"https://{api_host}/user/posts"
    params = {"unique_id": f"@{clean}", "count": "30"}
    r = requests.get(url, headers=headers, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    if data.get("code", 0) != 0:
        raise Exception(f"TikTok API: {data.get('msg') or data.get('code')}")

    # tikwm có thể trả về nhiều format khác nhau
    items = (
        data.get("data", {}).get("videos")
        or data.get("data", {}).get("aweme_list")
        or data.get("videos")
        or []
    )

    videos = []
    total_views = 0

    for item in items:
        create_time = datetime.fromtimestamp(
            item.get("create_time") or item.get("createTime") or 0, tz=tz
        )
        if not (yesterday_start <= create_time <= yesterday_end):
            continue

        stats    = item.get("statistics") or item.get("stats") or {}
        views    = stats.get("play_count")    or stats.get("playCount")    or item.get("play_count",    0)
        comments = stats.get("comment_count") or stats.get("commentCount") or item.get("comment_count", 0)
        likes    = stats.get("digg_count")    or stats.get("diggCount")    or item.get("digg_count",    0)
        desc     = item.get("title") or item.get("desc") or ""
        title    = (desc[:60] + ("…" if len(desc) > 60 else "")) if desc else "(No caption)"

        total_views += views
        videos.append({
            "title":    title,
            "views":    views,
            "comments": comments,
            "likes":    likes,
        })

    videos.sort(key=lambda x: x["views"], reverse=True)
    return {"name": channel_name, "videos": videos, "total_views": total_views}

def fetch_all_tiktok(cfg):
    results = []
    api_key  = cfg["tiktok"].get("rapidapi_key",  "")
    api_host = cfg["tiktok"].get("rapidapi_host", "tiktok-scraper7.p.rapidapi.com")
    tz_name  = cfg["timezone"]

    if not api_key or api_key == "YOUR_RAPIDAPI_KEY_HERE":
        for ch in cfg["tiktok"]["channels"]:
            results.append({
                "name": ch["name"],
                "error": "Chưa điền rapidapi_key vào channels.json",
                "videos": [], "total_views": 0,
            })
        return results

    for i, ch in enumerate(cfg["tiktok"]["channels"]):
        if i > 0:
            time.sleep(2)
        try:
            data = fetch_tiktok_channel(ch["username"], ch["name"], api_key, api_host, tz_name)
            results.append(data)
        except Exception as e:
            results.append({"name": ch["name"], "error": str(e), "videos": [], "total_views": 0})
    return results

# ─── MAIN ─────────────────────────────────────────────────────────────────────

def fetch_report(cfg):
    return {
        "date": (datetime.now(pytz.timezone(cfg["timezone"])) - timedelta(days=1)).strftime("%d/%m/%Y"),
        "youtube": fetch_all_youtube(cfg),
        "tiktok":  fetch_all_tiktok(cfg),
    }

def main():
    dry_run = "--dry-run" in sys.argv
    output = fetch_report(load_config())

    if dry_run:
        print("[DRY RUN] Kết quả fetch:")
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(output, ensure_ascii=False))

if __name__ == "__main__":
    main()