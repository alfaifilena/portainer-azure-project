import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from report_api import start_report_api, publish_report
from ai_client import analyze_incident

APP_DIR = Path(__file__).resolve().parent

INTERVAL = int(os.environ.get("POLL_INTERVAL_SECONDS", "30"))
CACHE_SECONDS = int(os.environ.get("AI_CACHE_SECONDS", "900"))
MAX_REQUESTS = int(os.environ.get("AI_MAX_REQUESTS_PER_RUN", "10"))

if INTERVAL < 5 or CACHE_SECONDS < 60 or MAX_REQUESTS < 0:
    raise SystemExit("Invalid monitoring settings.")

# Memory only: nothing is written to a database or report file.
cache = {}
requests_used = 0


def collect_report():
    result = subprocess.run(
        [sys.executable, str(APP_DIR / "monitor.py")],
        capture_output=True,
        text=True,
    )

    if not result.stdout.strip():
        raise RuntimeError(
            result.stderr.strip() or "Monitor returned no report."
        )

    report = json.loads(result.stdout)

    if result.returncode != 0 and report.get("collection_status") != "partial":
        raise RuntimeError("Monitoring failed.")

    return report


def add_ai_analysis(report):
    global requests_used
    sent_this_cycle = False

    for container in report.get("containers", []):
        if container.get("collection_status") != "ok":
            continue

        for finding in container.get("findings") or []:
            if finding["rule"] != "nginx_http_404":
                finding["ai"] = {"status": "unsupported_rule"}
                continue

            identity = (
                report["environment_id"],
                container["id"],
                finding["rule"],
                finding["severity"],
                container["state"],
                container["health"],
            )

            now = time.monotonic()
            saved = cache.get(identity)

            if saved and now < saved["expires_at"]:
                finding["ai"] = {
                    **saved["output"],
                    "source": "memory",
                }
                continue

            if requests_used >= MAX_REQUESTS:
                finding["ai"] = {"status": "session_limit_reached"}
                continue

            if sent_this_cycle:
                finding["ai"] = {"status": "deferred_to_next_cycle"}
                continue

            requests_used += 1
            sent_this_cycle = True

            try:
                analysis = analyze_incident(container, finding)
                output = {
                    "status": "ready",
                    "source": "openrouter",
                    **analysis,
                }
            except Exception as error:
                # AI failure must not stop container monitoring.
                output = {
                    "status": "failed",
                    "source": "openrouter",
                    "error": str(error),
                    "retry_after_seconds": CACHE_SECONDS,
                }

            cache[identity] = {
                "expires_at": time.monotonic() + CACHE_SECONDS,
                "output": output,
            }
            finding["ai"] = output

    report["ai_requests_used_this_run"] = requests_used
    report["ai_request_limit_this_run"] = MAX_REQUESTS


def run():
    while True:
        try:
            report = collect_report()
            add_ai_analysis(report)
        except Exception as error:
            report = {
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "collection_status": "failed",
                "collection_error": str(error),
            }
        publish_report(report)
        print(json.dumps(report, indent=2, ensure_ascii=False), flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    server = start_report_api()

    try:
        run()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
