"""Persistent demo container: one real HTTP 500 log, only on an explicit request."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/error':
            status, body = 500, b'Demo: intentional HTTP 500 for rule detection and Telegram.\n'
            # Docker supplies the timestamp. Exactly one rule-matching access log.
            print('"GET /error HTTP/1.1" 500 0', flush=True)
        elif path in ('/', '/health'):
            status, body = 200, b'Monitor demo is ready. Request /error to trigger one alert.\n'
        else:
            status, body = 404, b'Use /health or /error.\n'
        self.send_response(status)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        # Health checks must not generate rule alerts or noisy logs.
        pass


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
