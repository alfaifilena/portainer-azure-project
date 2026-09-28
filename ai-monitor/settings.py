"""All paths and deployment choices are explicit; never disable TLS verification."""
import json
import os
from pathlib import Path

def load_settings():
    path = Path(os.environ.get("MONITOR_CONFIG", Path(__file__).with_name("config.json")))
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    config.setdefault("environment_ids", [])
    config.setdefault("container_filters", {})
    config.setdefault("log_tail", 300)
    config.setdefault("log_window_seconds", 300)
    config.setdefault("poll_seconds", 30)
    config.setdefault("ai_daily_requests", 100)
    config.setdefault("analysis_user_daily_requests", 10)
    config.setdefault("model", "openai/gpt-oss-20b")
    config.setdefault("retention_days", 30)
    config["ai_enabled"] = os.environ.get("AI_ENABLED", "true").lower() == "true"
    if config["poll_seconds"] < 10:
        raise ValueError("Polling must be >=10s.")
    if not 1 <= config["ai_daily_requests"] <= 10000:
        raise ValueError("Set a daily AI request cap between 1 and 10000.")
    if not 1 <= config["analysis_user_daily_requests"] <= 1000 or not 1 <= config["retention_days"] <= 365:
        raise ValueError("Invalid user request limit or retention period.")
    return config

