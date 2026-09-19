import json
import ssl
import sys
import time
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = Path(__file__).with_name("config.json")

HTTP_404 = re.compile(
    r'"[A-Z]+ [^"]+ HTTP/\d(?:\.\d)?"\s+404\s'
)


def decode_logs(data, tty):
    if tty:
        return data.decode("utf-8", errors="replace")

    chunks = []
    position = 0

    while position < len(data):
        header = data[position:position + 8]

        if (
            len(header) != 8
            or header[0] not in (0, 1, 2)
            or header[1:4] != b"\x00\x00\x00"
        ):
            raise ValueError("Invalid Docker log header.")

        size = int.from_bytes(header[4:8], "big")
        start = position + 8
        end = start + size

        if end > len(data):
            raise ValueError("Incomplete Docker log message.")

        chunks.append(data[start:end])
        position = end

    return b"".join(chunks).decode("utf-8", errors="replace")


def detect_errors(logs):
    matches = [
        line for line in logs.splitlines()
        if HTTP_404.search(line)
    ]

    if not matches:
        return []

    return [{
        "rule": "nginx_http_404",
        "category": "HTTP resource not found",
        "severity": "LOW",
        "matched_requests": len(matches),
        "confirmed_evidence": "HTTP 404 responses appear in access logs.",
        "possible_cause": "Missing resource or incorrect request path.",
        "suggested_check": "Verify the requested URL and routing.",
        "evidence": matches[-3:],
    }]


def main():
    config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))

    token_path = PROJECT_ROOT / config["token_file"]
    certificate_path = PROJECT_ROOT / config["certificate_file"]
    token = token_path.read_text(encoding="utf-8").strip()

    if not token:
        raise ValueError("The token file is empty.")

    base_url = config["portainer_url"].rstrip("/")
    if not base_url.startswith("https://"):
        raise ValueError("Portainer URL must use HTTPS.")

    tls = ssl.create_default_context(cafile=str(certificate_path))
    environment_id = int(config["environment_id"])
    docker_path = f"/api/endpoints/{environment_id}/docker"

    def get(path):
        request = Request(
            base_url + path,
            headers={"X-API-Key": token},
            method="GET",
        )
        with urlopen(request, context=tls, timeout=10) as response:
            return response.read()

    query = urlencode({
        "all": "true",
        "filters": json.dumps(config["container_filters"]),
    })

    containers = json.loads(get(f"{docker_path}/containers/json?{query}"))

    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "environment_id": environment_id,
        "collection_status": "ok",
        "matched_containers": len(containers),
        "rule_coverage": ["nginx_http_404"],
        "containers": [],
    }

    since = int(time.time()) - int(config["log_window_seconds"])

    for container in containers:
        names = container.get("Names") or [container["Id"][:12]]
        item = {
            "id": container["Id"],
            "name": names[0].lstrip("/"),
            "collection_status": "ok",
        }

        path = f"{docker_path}/containers/{container['Id']}"

        try:
            details = json.loads(get(f"{path}/json"))
            state = details["State"]

            item.update({
                "state": state["Status"],
                "health": state.get("Health", {}).get(
                    "Status", "not configured"
                ),
                "restart_count": details.get("RestartCount", 0),
                "oom_killed": state.get("OOMKilled", False),
                "exit_code": (
                    state.get("ExitCode")
                    if state["Status"] in ("exited", "dead")
                    else None
                ),
            })

            log_query = urlencode({
                "stdout": "true",
                "stderr": "true",
                "timestamps": "true",
                "tail": int(config["log_tail"]),
                "since": since,
            })

            raw_logs = get(f"{path}/logs?{log_query}")
            logs = decode_logs(
                raw_logs, details["Config"].get("Tty", False)
            )

            item["log_lines_received"] = len(logs.splitlines())
            item["findings"] = detect_errors(logs)

        except (HTTPError, URLError, OSError, ValueError, KeyError) as error:
            item["collection_status"] = "failed"
            item["collection_error"] = str(error)
            item["findings"] = None
            report["collection_status"] = "partial"

        report["containers"].append(item)

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["collection_status"] == "ok" else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (HTTPError, URLError, OSError, ValueError, KeyError) as error:
        print(f"Monitor failed: {error}", file=sys.stderr)
        sys.exit(1)
