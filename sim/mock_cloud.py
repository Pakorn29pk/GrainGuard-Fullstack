#!/usr/bin/env python3
"""Mock of the Cloudflare Worker: verifies X-GG-Ts / X-GG-Sig (HMAC-SHA256 of ts + "." + body),
stores heartbeats and events, de-duplicates events by (hub, seq), and can simulate outages.

  python sim/mock_cloud.py --port 8787 --secret test-secret
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional


class MockCloud:
    def __init__(self, secret: str = "test-secret", port: int = 0, host: str = "127.0.0.1", max_skew: int = 300):
        self.secret = secret
        self.max_skew = max_skew
        self.lock = threading.Lock()
        self.heartbeats: List[Dict[str, Any]] = []
        self.events: List[Dict[str, Any]] = []        # accepted, de-duplicated, in arrival order
        self.arrivals: List[int] = []                 # seq of every accepted POST (incl. duplicates)
        self.bad_sig = 0
        self.dups = 0
        self.fail_mode: Optional[str] = None          # None | "500" | "503" | "drop" | "401" | "400" | "lose_ack"
        self.fail_count: Optional[int] = None         # None: fail until cleared; N: fail only the next N requests
        self.requests = 0
        self._seen = set()
        outer = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):  # silence
                pass

            def _reply(self, code: int, obj: dict):
                b = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def do_POST(self):
                n = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(n)
                with outer.lock:
                    outer.requests += 1
                    fm = outer.fail_mode
                    if fm and outer.fail_count is not None:
                        outer.fail_count -= 1
                        if outer.fail_count <= 0:
                            outer.fail_mode = None
                if fm == "drop":
                    self.close_connection = True
                    self.connection.close()
                    return
                if fm in ("500", "503", "401", "400"):
                    return self._reply(int(fm), {"error": fm})
                ts = self.headers.get("X-GG-Ts", "")
                sig = self.headers.get("X-GG-Sig", "")
                want = hmac.new(outer.secret.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()
                ok = hmac.compare_digest(sig, want)
                try:
                    skew_ok = abs(time.time() - int(ts)) <= outer.max_skew
                except ValueError:
                    skew_ok = False
                if not (ok and skew_ok):
                    with outer.lock:
                        outer.bad_sig += 1
                    return self._reply(401, {"error": "bad signature"})
                try:
                    d = json.loads(body)
                except ValueError:
                    return self._reply(400, {"error": "bad json"})
                if self.path == "/api/heartbeat":
                    with outer.lock:
                        outer.heartbeats.append(d)
                    return self._reply(200, {"ok": True})
                if self.path == "/api/event":
                    key = (d.get("hub"), d.get("seq"))
                    with outer.lock:
                        outer.arrivals.append(d.get("seq"))
                        if key in outer._seen:
                            outer.dups += 1
                            return self._reply(200, {"ok": True, "dup": True})
                        outer._seen.add(key)
                        outer.events.append(d)
                    if fm == "lose_ack":      # event stored, but the hub never sees the 2xx
                        self.close_connection = True
                        self.connection.close()
                        return
                    return self._reply(200, {"ok": True})
                return self._reply(404, {"error": "not found"})

        self.httpd = ThreadingHTTPServer((host, port), H)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.url = "http://%s:%d" % (host, self.port)
        self._t = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def start(self) -> "MockCloud":
        self._t.start()
        return self

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()

    def event_types(self) -> List[str]:
        with self.lock:
            return [e["type"] for e in self.events]

    def fail_next(self, mode: str, count: int) -> None:
        """Fail the next `count` requests with `mode`, then behave normally."""
        with self.lock:
            self.fail_mode, self.fail_count = mode, count

    def set_outage(self, mode: Optional[str]) -> None:
        """Fail every request with `mode` until set_outage(None)."""
        with self.lock:
            self.fail_mode, self.fail_count = mode, None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--secret", default="test-secret")
    a = ap.parse_args()
    m = MockCloud(a.secret, a.port).start()
    print("mock cloud on", m.url)
    try:
        while True:
            time.sleep(5)
            with m.lock:
                print("heartbeats=%d events=%d dups=%d bad_sig=%d" % (len(m.heartbeats), len(m.events), m.dups, m.bad_sig))
    except KeyboardInterrupt:
        m.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
