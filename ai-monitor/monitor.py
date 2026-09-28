import json
import ssl
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from rules import CATALOG, detect, redact, log_records

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = Path(__file__).with_name("config.json")
MAX_RESPONSE = 4 * 1024 * 1024

def decode_logs(data, tty):
    if tty:
        return data.decode("utf-8", errors="replace")
    chunks, position = [], 0
    while position < len(data):
        header = data[position:position + 8]
        if len(header) != 8 or header[0] not in (0, 1, 2) or header[1:4] != b"\x00\x00\x00":
            raise ValueError("Invalid Docker log header.")
        size = int.from_bytes(header[4:8], "big")
        start, end = position + 8, position + 8 + size
        if end > len(data):
            raise ValueError("Incomplete Docker log message.")
        chunks.append(data[start:end])
        position = end
    return b"".join(chunks).decode("utf-8", errors="replace")

def validate_config(config):
    url = urlsplit(config["portainer_url"])
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError("Use an HTTPS Portainer base URL without credentials, query or fragment.")
    if type(config["environment_id"]) is not int or config["environment_id"] < 1:
        raise ValueError("environment_id must be a positive integer.")
    for key, upper in [("log_tail", 2000), ("log_window_seconds", 3600)]:
        if type(config[key]) is not int or not 1 <= config[key] <= upper:
            raise ValueError(f"{key} must be between 1 and {upper}.")
    filters = config["container_filters"]
    if not isinstance(filters, dict) or not all(isinstance(k, str) and isinstance(v, list)
        and all(isinstance(x, str) for x in v) for k, v in filters.items()):
        raise ValueError("container_filters must map strings to lists of strings; {} selects all accessible containers.")

def collect_report(config, get, now=None):
    validate_config(config)
    now = time.time() if now is None else now
    since = int(now) - config["log_window_seconds"]
    docker_path = f"/api/endpoints/{config['environment_id']}/docker"
    query = urlencode({"all": "true", "filters": json.dumps(config["container_filters"])})
    containers = json.loads(get(f"{docker_path}/containers/json?{query}"))
    if not isinstance(containers, list):
        raise ValueError("Invalid Docker container list.")
    report = {
        "checked_at": datetime.fromtimestamp(now, timezone.utc).isoformat(),
        "environment_id": config["environment_id"], "collection_status": "ok",
        "matched_containers": len(containers), "rule_coverage": list(CATALOG),
        "observation_window_seconds": config["log_window_seconds"],
        "containers": [],
    }
    for container in containers:
        names = container.get("Names") or [container["Id"][:12]]
        item = {"id": container["Id"], "name": names[0].lstrip("/"),
                "collection_status": "ok", "collection_warnings": []}
        path = f"{docker_path}/containers/{container['Id']}"
        try:
            details = json.loads(get(f"{path}/json"))
            state = details["State"]
            item.update({
                "state": state["Status"],
                "health": state.get("Health", {}).get("Status", "not configured"),
                "restart_count": details.get("RestartCount", 0),
                "restart_policy": details.get("HostConfig", {}).get("RestartPolicy"),
                "started_at": state.get("StartedAt"),
                "finished_at": state.get("FinishedAt"),
                "oom_killed": state.get("OOMKilled", False),
                "exit_code": state.get("ExitCode") if state["Status"] in ("exited", "dead") else None,
            })
        except (OSError, ValueError, KeyError, TypeError) as error:
            item.update(collection_status="failed", collection_error=redact(str(error)), findings=None)
            report["collection_status"] = "partial"
            report["containers"].append(item)
            continue

        logs = None
        try:
            log_query = urlencode({"stdout": "true", "stderr": "true", "timestamps": "true",
                                   "tail": config["log_tail"], "since": since})
            raw = get(f"{path}/logs?{log_query}")
            logs = decode_logs(raw, details.get("Config", {}).get("Tty", False))
            item["log_lines_received"] = len(logs.splitlines())
        except (OSError, ValueError, KeyError, TypeError) as error:
            # A logging-driver problem must not erase valid health/OOM findings.
            item["collection_status"] = "partial"
            item["log_lines_received"] = None
            item["collection_warnings"].append("Logs unavailable: " + redact(str(error)))
            report["collection_status"] = "partial"
        item["findings"] = detect(details, logs, since, now)
        item["log_sample"] = log_records(logs or "", since, now)[-100:]
        report["containers"].append(item)
    return report

def main():
    config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    validate_config(config)
    token = (PROJECT_ROOT / config["token_file"]).read_text(encoding="utf-8").strip()
    if not token:
        raise ValueError("The token file is empty.")
    tls = ssl.create_default_context(cafile=str(PROJECT_ROOT / config["certificate_file"]))
    base_url = config["portainer_url"].rstrip("/")
    def get(path):
        request = Request(base_url + path, headers={"X-API-Key": token}, method="GET")
        with urlopen(request, context=tls, timeout=10) as response:
            data = response.read(MAX_RESPONSE + 1)
        if len(data) > MAX_RESPONSE:
            raise ValueError("Response exceeded the 4 MiB collection limit; reduce log_tail or narrow the filter.")
        return data
    report = collect_report(config, get)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["collection_status"] == "ok" else 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, TypeError) as error:
        print("Monitor failed: " + redact(str(error)), file=sys.stderr)
        sys.exit(1)
