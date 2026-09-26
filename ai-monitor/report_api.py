"""Private API. Every data request revalidates the user's Portainer access."""
import copy
import json
import secrets
import threading
import time
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from run_monitor import observations

class APIError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message

class API:
    def __init__(self, service):
        self.service, self.store, self.portainer = service, service.store, service.portainer
        self.sessions = {}
        self.attempts = defaultdict(deque)
        self.lock = threading.Lock()

    def login(self, body, address):
        username, password = body.get("username"), body.get("password")
        if not isinstance(username, str) or not isinstance(password, str) or not username or not password:
            raise APIError(400, "Enter your Portainer username and password.")
        if len(username) > 256 or len(password) > 4096:
            raise APIError(400, "Invalid credentials.")
        now = time.time()
        with self.lock:
            # A single private dashboard is the API caller; also limit by username.
            self.attempts = defaultdict(deque, {k: deque(t for t in v if t > now - 60)
                                               for k, v in self.attempts.items() if v and v[-1] > now - 60})
            for key, limit in (("global", 60), ("user:" + username.casefold(), 6)):
                if len(self.attempts[key]) >= limit:
                    raise APIError(429, "Too many sign-in attempts. Try again in one minute.")
                self.attempts[key].append(now)
        try:
            jwt, user, expires = self.portainer.login(username, password)
        except HTTPError as error:
            if error.code in (400, 401, 403, 404):
                raise APIError(401, "Portainer sign-in failed.") from None
            raise APIError(503, "Portainer is unavailable.") from None
        token = secrets.token_urlsafe(32)
        session = {"jwt": jwt, "uid": user["Id"], "role": user.get("Role"), "expires": min(expires, now + 3600)}
        with self.lock:
            self.sessions = {k: v for k, v in self.sessions.items() if v["expires"] > now}
            if len(self.sessions) >= 1000:
                raise APIError(503, "Sign-in capacity reached. Try again later.")
            self.sessions[token] = session
        return {"token": token, "username": user["Username"]}

    def identity(self, token):
        with self.lock:
            session = self.sessions.get(token)
        if not session or session["expires"] <= time.time():
            raise APIError(401, "Your session expired. Sign in again.")
        try:
            user = self.portainer.json(f"/api/users/{session['uid']}", jwt=session["jwt"])
        except HTTPError as error:
            if error.code in (401, 403, 404):
                with self.lock:
                    self.sessions.pop(token, None)
                raise APIError(401, "Your session is no longer authorized.") from None
            raise APIError(503, "Cannot verify your Portainer permissions.") from None
        if user["Id"] != session["uid"]:
            raise APIError(401, "Identity mismatch.")
        if user.get("Role") != session["role"]:
            with self.lock:
                self.sessions.pop(token, None)
            raise APIError(401, "Your Portainer role changed. Sign in again.")
        return session, user

    def scope(self, session, eid):
        envs = self.portainer.environments(jwt=session["jwt"])
        if eid not in {env["Id"] for env in envs}:
            raise APIError(403, "You do not have access to this environment.")
        allowed = {c["Id"] for c in self.portainer.containers(eid, jwt=session["jwt"])}
        return allowed

    def dispatch(self, method, path, token, body=None, address=""):
        body = body or {}
        if path == "/health" and method == "GET":
            return {"status": "ok"}
        if path == "/login" and method == "POST":
            return self.login(body, address)
        if path == "/logout" and method == "POST":
            with self.lock:
                self.sessions.pop(token, None)
            return {"ok": True}
        session, user = self.identity(token)
        parsed = urlsplit(path)
        if parsed.path == "/environments" and method == "GET":
            return {"environments": [{"id": x["Id"], "name": x["Name"]}
                    for x in self.portainer.environments(jwt=session["jwt"])],
                    "username": user["Username"]}
        query = parse_qs(parsed.query)
        try:
            eid = int(query.get("environment", [None])[0])
            if eid < 1:
                raise ValueError()
        except (TypeError, ValueError):
            raise APIError(400, "Select an environment.") from None
        allowed = self.scope(session, eid)
        if parsed.path == "/report" and method == "GET":
            report = copy.deepcopy(self.store.get(f"report:{eid}"))
            if report is None:
                report = {"environment_id": eid, "collection_status": "starting", "containers": []}
            report["containers"] = [c for c in report.get("containers", []) if c["id"] in allowed]
            report["matched_containers"] = len(report["containers"])
            for container in report["containers"]:
                previous = self.store.get(f"detection:{eid}:{container['id']}", {})
                job = self.store.job(previous.get("job", "")) if previous else None
                container["ai_detection"] = self.public_job(job)
            # Global collection details may expose other environments; only return status.
            report["collector"] = self.store.get("collector", {"status": "starting"})
            report["ai_status"] = self.store.get("ai_status", {"status": "waiting"})
            report["notices"] = self.store.notices(eid, user["Id"], allowed)
            return report
        if parsed.path == "/notices/read" and method == "POST":
            ids = body.get("ids")
            if not isinstance(ids, list) or len(ids) > 500 or not all(isinstance(x, str) for x in ids):
                raise APIError(400, "Invalid notification selection.")
            visible = {n["id"] for n in self.store.notices(eid, user["Id"], allowed)}
            if not set(ids) <= visible:
                raise APIError(403, "Notification access denied.")
            self.store.mark_read(user["Id"], ids)
            return {"ok": True}
        if parsed.path == "/analysis" and method == "POST":
            if not self.service.config.get("ai_enabled", True):
                raise APIError(409, "AI analysis is disabled for this deployment.")
            cid = body.get("container_id")
            if not isinstance(cid, str) or cid not in allowed:
                raise APIError(403, "Container access denied.")
            report = self.store.get(f"report:{eid}", {})
            try:
                from datetime import datetime, timezone
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(report["checked_at"])).total_seconds()
            except (KeyError, ValueError, TypeError):
                age = 10000
            if age > 150 or age < -10 or report.get("collection_status") not in ("ok", "partial"):
                raise APIError(409, "Wait for a fresh monitoring sample before requesting analysis.")
            container = next((c for c in report.get("containers", []) if c["id"] == cid), None)
            if not container or container.get("collection_status") == "failed":
                raise APIError(409, "No usable monitoring sample is available for this container.")
            if not self.store.consume(f"user:{user['Id']}", self.service.config["analysis_user_daily_requests"]):
                raise APIError(429, "Your daily analysis request limit has been reached.")
            job = self.store.enqueue(eid, cid, "analysis", observations(container))
            return {"job_id": job}
        if parsed.path == "/job" and method == "GET":
            job = self.store.job(query.get("id", [""])[0])
            if not job or job["env"] != eid or job["cid"] not in allowed:
                raise APIError(404, "Analysis not found.")
            return self.public_job(job)
        raise APIError(404, "Not found.")

    @staticmethod
    def public_job(job):
        return {k: job.get(k) for k in ("id", "status", "result", "error", "updated")} if job else {"status": "waiting"}

def start_report_api(service, host="0.0.0.0", port=8090):
    api = API(service)
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(20)

        def handle_request(self):
            status = 200
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 <= length <= 16384:
                    raise APIError(413, "Request too large.")
                body = json.loads(self.rfile.read(length)) if length else {}
                if not isinstance(body, dict):
                    raise APIError(400, "Expected a JSON object.")
                token = self.headers.get("Authorization", "").removeprefix("Bearer ")
                result = api.dispatch(self.command, self.path, token, body, self.client_address[0])
            except APIError as error:
                status, result = error.status, {"message": error.message}
            except HTTPError as error:
                status = 403 if error.code in (401, 403, 404) else 503
                result = {"message": "Portainer could not authorize this request."}
            except (ValueError, TypeError):
                status, result = 400, {"message": "Invalid request."}
            except Exception:
                status, result = 503, {"message": "Monitoring service is temporarily unavailable."}
            encoded = json.dumps(result, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        do_GET = handle_request
        do_POST = handle_request

        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server

