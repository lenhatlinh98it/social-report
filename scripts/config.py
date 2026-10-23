"""
config.py — Đọc/ghi config/channels.json; secrets lấy từ .env hoặc biến môi trường
"""
import json, os, threading

BASE        = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE, "../config/channels.json")
ENV_PATH    = os.path.join(BASE, "../.env")

_write_lock = threading.Lock()

def load_env():
    if not os.path.exists(ENV_PATH):
        return
    with open(ENV_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

def load_config():
    load_env()
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.setdefault("slack", {})["webhook_url"] = os.environ.get("SLACK_WEBHOOK_URL", "")
    cfg.setdefault("tiktok", {})["rapidapi_key"] = os.environ.get("RAPIDAPI_KEY", "")
    return cfg

def update_config(mutate):
    """Đọc channels.json (không kèm secrets), gọi mutate(cfg), ghi lại. Trả về kết quả của mutate."""
    with _write_lock:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        result = mutate(cfg)
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CONFIG_PATH)
        return result
