import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_lock = threading.Lock()
_latest_report = None


def publish_report(report):
    global _latest_report

    encoded = json.dumps(report, ensure_ascii=False).encode("utf-8")

    with _lock:
        _latest_report = encoded


class ReportHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/report":
            self.send_error(404)
            return

        with _lock:
            body = _latest_report

        if body is None:
            status = 503
            body = json.dumps({
                "collection_status": "starting",
                "message": "Waiting for the first monitoring report.",
            }).encode("utf-8")
        else:
            status = 200

        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def start_report_api():
    server = ThreadingHTTPServer(("0.0.0.0", 8090), ReportHandler)

    thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
    )
    thread.start()
    return server
