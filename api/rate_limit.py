"""访客 IP 每小时限流"""
import json
import os
import datetime
import threading

import config_data as config

RATE_LIMIT_FILE = "./data/rate_limit.json"
_lock = threading.Lock()

RATE_LIMIT_MESSAGE = "演示环境每小时仅限10次提问，如需深度体验请联系作者"


def _current_hour() -> str:
    """返回当前小时标识，如 '2026-06-22T17'"""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H")


def _load() -> dict:
    if not os.path.exists(RATE_LIMIT_FILE):
        return {}
    try:
        with open(RATE_LIMIT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}


def _save(data: dict):
    os.makedirs(os.path.dirname(RATE_LIMIT_FILE), exist_ok=True)
    with open(RATE_LIMIT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def get_client_ip(request) -> str:
    """从 X-Forwarded-For 提取真实 IP（nginx 透传）"""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_rate_limit(ip: str) -> tuple[bool, int]:
    """检查 guest IP 是否超出每小时限额。
    返回 (allowed, remaining)。超出时返回 (False, 0)。
    """
    hour = _current_hour()
    with _lock:
        data = _load()
        # 清理过期条目（超过 2 小时的）
        expired = [k for k in data if data[k].get("hour") != hour]
        for k in expired:
            del data[k]

        entry = data.get(ip, {"hour": hour, "count": 0})
        if entry["hour"] != hour:
            entry = {"hour": hour, "count": 0}

        if entry["count"] >= config.guest_daily_limit:
            data[ip] = entry
            _save(data)
            return False, 0

        entry["count"] += 1
        remaining = config.guest_daily_limit - entry["count"]
        data[ip] = entry
        _save(data)
        return True, remaining
