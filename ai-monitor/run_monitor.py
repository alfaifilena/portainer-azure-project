"""Persistent monitoring and AI queue; independent of user sessions."""
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from ai_client import analyze
from monitor import collect_report
from portainer import Portainer
from rules import redact
from settings import load_settings
from storage import Store, fingerprint

def utcnow():
    return datetime.now(timezone.utc).isoformat()

def observations(container):
    return {key: container.get(key) for key in
            ("id", "name", "state", "health", "restart_count", "oom_killed", "exit_code",
             "findings", "log_sample")}

class MonitorService:
    def __init__(self, config, store, portainer=None, analyze_fn=analyze):
        self.config, self.store = config, store
        self.portainer = portainer or Portainer(config)
        self.analyze_fn = analyze_fn
        self.stop = threading.Event()

    def collect_once(self):
        now = time.time()
        try:
            envs = self.portainer.environments(service=True)
            self.store.put("collector", {"status": "ok", "checked_at": utcnow()})
        except Exception:
            self.store.put("collector", {"status": "failed", "checked_at": utcnow(),
                                        "message": "Cannot reach Portainer with the monitor credentials."})
            return
        for env in envs:
            eid = env["Id"]
            try:
                report = collect_report({**self.config, "environment_id": eid},
                    lambda path: self.portainer.request(path, service=True), now=now)
                report["environment_name"] = env["Name"]
                for container in report["containers"]:
                    cid = container["id"]
                    for finding in container.get("findings") or []:
                        self.store.notice(eid, cid, "rule", finding["category"],
                            {"container_name": container["name"], **finding},
                            [finding["rule"], finding.get("facts", {})])
                self.store.put(f"report:{eid}", report)
            except Exception:
                self.store.put(f"report:{eid}", {"checked_at": utcnow(), "environment_id": eid,
                    "collection_status": "failed", "containers": [],
                    "collection_error": "Environment collection failed. Check monitor access and connectivity."})
        self.store.prune(self.config["retention_days"])

    def queue_detection(self, eid, container, now):
        if not self.config.get("ai_enabled", True):
            self.store.put("ai_status", {"status": "disabled", "updated_at": utcnow()})
            return
        if container.get("collection_status") != "ok":
            return
        cid = container["id"]
        key = f"detection:{eid}:{cid}"
        previous = self.store.get(key, {})
        if now - previous.get("at", 0) < self.config["ai_interval_seconds"]:
            return
        sample = container.get("log_sample") or []
        seen = set(previous.get("seen", []))
        new = [line for line in sample if fingerprint(line) not in seen]
        if not new:
            return
        if not Path(os.environ.get("OPENROUTER_KEY_FILE", "/run/secrets/openrouter_api_key")).is_file():
            self.store.put("ai_status", {"status": "not_configured", "updated_at": utcnow()})
            return
        payload = observations(container)
        payload["log_sample"] = new[-100:]
        job = self.store.enqueue(eid, cid, "detect", payload)
        self.store.put(key, {"at": now, "seen": list(dict.fromkeys(
            previous.get("seen", []) + [fingerprint(line) for line in new]))[-2000:], "job": job})

    def work_once(self):
        if not self.config.get("ai_enabled", True):
            return False
        job = self.store.claim()
        if not job:
            return False
        if not self.store.consume("global_ai", self.config["ai_daily_requests"]):
            self.store.finish(job["id"], "failed", error="Daily AI request limit reached; resets at 00:00 UTC.")
            self.store.put("ai_status", {"status": "daily_limit", "updated_at": utcnow()})
            return True
        try:
            result = self.analyze_fn(job["kind"], job["payload"], self.config["model"])
            self.store.finish(job["id"], "ready", result=result)
            self.store.put("ai_status", {"status": "available", "updated_at": utcnow()})
            if job["kind"] == "detect":
                for issue in result["output"]["issues"]:
                    self.store.notice(job["env"], job["cid"], "ai", issue["category"],
                        {**issue, "container_name": job["payload"]["name"],
                         "model": result["model"], "assessment": "AI observation; verify the evidence."},
                        issue["evidence"])
        except Exception as error:
            code = getattr(error, "code", None)
            message = ("AI provider authentication or credits need attention." if code in (401, 402, 403)
                       else "AI provider is rate limited." if code == 429
                       else "AI analysis unavailable or its response failed validation.")
            self.store.finish(job["id"], "failed", error=message)
            self.store.put("ai_status", {"status": "unavailable", "message": message, "updated_at": utcnow()})
            self.stop.wait(60 if code not in (401, 402, 403, 429) else 300)
        return True

    def collect_loop(self):
        while not self.stop.is_set():
            try:
                self.collect_once()
            except Exception:
                # Never print reports, tokens or sampled logs to the container log.
                print("Monitoring cycle failed; retrying.", flush=True)
            self.stop.wait(self.config["poll_seconds"])

    def worker_loop(self):
        while not self.stop.is_set():
            try:
                worked = self.work_once()
            except Exception:
                print("AI worker failed; retrying.", flush=True)
                worked = False
            self.stop.wait(1 if worked else 3)

def main():
    from report_api import start_report_api
    config = load_settings()
    store = Store(os.environ.get("MONITOR_DB", "/data/monitor.sqlite3"))
    service = MonitorService(config, store)
    server = start_report_api(service)
    threads = [threading.Thread(target=fn, daemon=True) for fn in (service.collect_loop, service.worker_loop)]
    for thread in threads:
        thread.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        service.stop.set()
        server.shutdown()
        server.server_close()

if __name__ == "__main__":
    main()

