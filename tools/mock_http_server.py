"""Tiny stdlib mock HTTP server for `http_call` smoke tests.

No third-party deps, no API tokens — just enough surface to exercise complex
JSON parsing, nested templating and `data_in.from_` wiring end to end.

Run:
    python tools/mock_http_server.py            # listens on :8077

Endpoints:
    GET  /user/<id>   -> nested JSON: {"user": {... "address": {...}}, "meta": {...}}
    POST /echo        -> {"received": <parsed body>, "auth_header": <X-Auth>, "ok": true}

Reaching it from the API container (docker compose):
    localhost in the container is NOT the host. Use the compose network gateway:
        docker network inspect back_default \
            --format '{{range .IPAM.Config}}{{.Gateway}}{{end}}'      # e.g. 172.24.0.1
    then point the node's URL at http://<gateway>:8077/...
"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8077


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):  # keep test output quiet
        pass

    def _send(self, code: int, obj: object) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.startswith("/user/"):
            uid = self.path.rsplit("/", 1)[-1]
            self._send(200, {
                "user": {
                    "id": int(uid) if uid.isdigit() else uid,
                    "name": "Ada Lovelace",
                    "roles": ["admin", "dev"],
                    "address": {"city": "Berlin", "zip": "10115"},
                },
                "meta": {"count": 2, "ok": True},
            })
        else:
            self._send(404, {"error": "not found", "path": self.path})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        try:
            parsed = json.loads(raw or b"null")
        except Exception:
            parsed = raw.decode("utf-8", "replace")
        self._send(200, {
            "received": parsed,
            "auth_header": self.headers.get("X-Auth", ""),
            "ok": True,
        })


if __name__ == "__main__":
    print(f"mock server on :{PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
