"""Persistent monitoring with AI requests tied to active admin sessions."""
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from ai_client import analyze, AnalysisUnavailable
from monitor import collect_report
from portainer import Portainer
from settings import load_settings
from storage import Store
from telegram_alerts import TelegramAlerts


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def observations(container):
    return {
        key: container.get(key)
        for key in (
            "id",
            "name",
            "state",
            "health",
            "restart_count",
            "oom_killed",
            "exit_code",
            "findings",
            "log_sample",
        )
    }


def fresh_report(report):
    try:
        age = (
            datetime.now(timezone.utc)
            - datetime.fromisoformat(report["checked_at"])
        ).total_seconds()
    except (KeyError, ValueError, TypeError):
        return False

    return (
        -10 <= age <= 150
        and report.get("collection_status") in ("ok", "partial")
    )


class MonitorService:
    def __init__(self, config, store, portainer=None, analyze_fn=analyze):
        self.config, self.store = config, store
        self.portainer = portainer or Portainer(config)
        self.analyze_fn = analyze_fn
        self.stop = threading.Event()
        self.session_api = None
        self.ai_lock = threading.Lock()
        self.ai_busy = False
        self.telegram = TelegramAlerts(store, config)

    def collect_once(self):
        now = time.time()

        try:
            envs = self.portainer.environments(service=True)
            self.store.put(
                "collector",
                {"status": "ok", "checked_at": utcnow()},
            )
        except Exception:
            self.store.put(
                "collector",
                {
                    "status": "failed",
                    "checked_at": utcnow(),
                    "message": (
                        "Cannot reach Portainer with the monitor credentials."
                    ),
                },
            )
            return

        for env in envs:
            eid = env["Id"]

            try:
                report = collect_report(
                    {**self.config, "environment_id": eid},
                    lambda path: self.portainer.request(path, service=True),
                    now=now,
                )
                report["environment_name"] = env["Name"]

                for container in report["containers"]:
                    cid = container["id"]

                    for finding in container.get("findings") or []:
                        self.store.notice(
                            eid,
                            cid,
                            "rule",
                            finding["category"],
                            {
                                "container_name": container["name"],
                                **finding,
                            },
                            [
                                finding["rule"],
                                finding.get("facts", {}),
                            ],
                        )

                        try:
                            self.telegram.observe(eid, env["Name"], container, finding, now)
                        except Exception:
                            self.store.put("telegram_status", {"status": "unavailable",
                                "message": "Telegram delivery unavailable; monitoring continues."})

                self.store.put(f"report:{eid}", report)

            except Exception:
                self.store.put(
                    f"report:{eid}",
                    {
                        "checked_at": utcnow(),
                        "environment_id": eid,
                        "collection_status": "failed",
                        "containers": [],
                        "collection_error": (
                            "Environment collection failed. "
                            "Check monitor access and connectivity."
                        ),
                    },
                )

        self.store.prune(self.config["retention_days"])

    def analysis_status(self):
        status = self.store.get("ai_status", {"status": "on_demand"})
        if not self.config.get("ai_enabled", True):
            return {"status": "disabled"}
        if status.get("retry_at", 0) > time.time():
            return status
        with self.ai_lock:
            if self.ai_busy:
                return {"status": "running"}
        return {"status": "on_demand"}

    def start_analysis(self, eid, cid, payload, uid):
        with self.ai_lock:
            if self.stop.is_set() or not self.config.get("ai_enabled", True):
                raise AnalysisUnavailable(409, "AI analysis is disabled.")
            status = self.store.get("ai_status", {})
            remaining = status.get("retry_at", 0) - time.time()
            if remaining > 0:
                raise AnalysisUnavailable(429, f"AI is temporarily unavailable. Try again in {int(remaining) + 1} seconds. Your request was not saved.")
            if self.ai_busy:
                raise AnalysisUnavailable(409, "Another analysis is running. Try again shortly. Your request was not saved.")
            self.ai_busy = True

        job_id = None
        try:
            key = Path(os.environ.get("GROQ_KEY_FILE", "/run/secrets/groq_api_key"))
            if not key.is_file() or not key.read_text().strip():
                raise AnalysisUnavailable(503, "AI is not configured.")
            # Reserve both budgets and record the running job in one transaction.
            try:
                job_id = self.store.start_analysis(eid, cid, payload, uid,
                    self.config["analysis_user_daily_requests"], self.config["ai_daily_requests"])
            except ValueError as error:
                raise AnalysisUnavailable(429, str(error)) from None
            job = self.store.job(job_id)
            threading.Thread(target=self.run_analysis, args=(job,), daemon=True).start()
            return job_id
        except Exception:
            try:
                if job_id:
                    self.store.finish(job_id, "failed", error="Analysis could not start. Try again.")
            finally:
                with self.ai_lock:
                    self.ai_busy = False
            raise

    def run_analysis(self, job):
        try:
            if not self.session_api or not self.session_api.authorize_job(job):
                self.store.finish(job["id"], "cancelled", error="Session ended or access cannot be verified.")
                return
            report = self.store.get(f"report:{job['env']}", {})
            if not fresh_report(report) or time.time() - job["created"] > 150:
                self.store.finish(job["id"], "cancelled", error="Monitoring sample expired. Request analysis again.")
                return
            payload = {k: v for k, v in job["payload"].items() if k != "_session_id"}
            if not self.session_api.job_session_live(job):
                self.store.finish(job["id"], "cancelled", error="Session ended. Request analysis again.")
                return
            result = self.analyze_fn(payload, self.config["model"])
            self.store.finish(job["id"], "ready", result=result)
            self.store.put("ai_status", {"status": "on_demand", "updated_at": utcnow()})
        except Exception as error:
            code = getattr(error, "code", None)
            message = ("AI provider authentication or credits need attention." if code in (401, 402, 403)
                       else "AI provider is rate limited. Try again later." if code == 429
                       else "AI analysis unavailable or its response failed validation.")
            delay = 300 if code in (401, 402, 403, 429) else 60
            try:
                delay = max(delay, float(error.headers.get("Retry-After", 0)))
            except (AttributeError, ValueError, TypeError):
                pass
            self.store.finish(job["id"], "failed", error=message)
            self.store.put("ai_status", {"status": "unavailable", "message": message,
                "retry_at": time.time() + delay, "updated_at": utcnow()})
        finally:
            with self.ai_lock:
                self.ai_busy = False

    def session_loop(self):
        while not self.stop.is_set():
            try:
                if self.session_api:
                    self.session_api.expire_sessions()
            except Exception:
                print("Session cleanup failed; retrying.", flush=True)

            self.stop.wait(1)

    def collect_loop(self):
        while not self.stop.is_set():
            try:
                self.collect_once()
            except Exception:
                # Never print reports, tokens or sampled logs.
                print("Monitoring cycle failed; retrying.", flush=True)

            self.stop.wait(self.config["poll_seconds"])

    def telegram_loop(self):
        while not self.stop.is_set():
            try:
                self.telegram.send_once()
            except Exception:
                print("Telegram delivery unavailable; retrying.", flush=True)
            self.stop.wait(3)


def main():
    from report_api import start_report_api

    config = load_settings()
    store = Store(os.environ.get("MONITOR_DB", "/data/monitor.sqlite3"))
    service = MonitorService(config, store)
    server = start_report_api(service)

    threads = [
        threading.Thread(target=fn, daemon=True)
        for fn in (
            service.collect_loop,
            service.telegram_loop,
            service.session_loop,
        )
    ]

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
