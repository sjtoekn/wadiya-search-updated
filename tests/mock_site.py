"""Tiny local HTTP site used by crawler/fetcher/e2e tests (no internet needed)."""
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class MockSite:
    """routes: path -> (status, content_type, body_bytes_or_str, extra_headers)"""
    def __init__(self, routes):
        self.routes, self.hits, self.hosts = routes, [], []
        site = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_GET(self):
                site.hits.append(self.path); site.hosts.append(self.headers.get("Host"))
                status, ctype, body, headers = (site.routes.get(self.path) or
                                                site.routes.get(self.path.split("?")[0]) or
                                                (404, "text/plain", "not found", {}))
                data = body.encode() if isinstance(body, str) else body
                self.send_response(status)
                if ctype:
                    self.send_header("Content-Type", ctype)
                for k, v in (headers or {}).items():
                    self.send_header(k, v.replace("{base}", site.base).replace("{base_port}", site.base.rsplit(":", 1)[1]))
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def __enter__(self):
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *a):
        self.server.shutdown(); self.server.server_close()
