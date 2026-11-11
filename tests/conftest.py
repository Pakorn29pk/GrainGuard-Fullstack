"""Shared fixtures. Broker: real Mosquitto if installed (preferred), else the pure-python amqtt broker.
Force one with GG_BROKER=mosquitto|amqtt."""
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "hub-core"))
sys.path.insert(0, os.path.join(ROOT, "sim"))

from grainguard_hub.config import Config  # noqa: E402
from grainguard_hub.engine import Engine  # noqa: E402
from grainguard_hub.store import Store  # noqa: E402


from stack import free_port, wait_port, start_broker as _start_broker  # noqa: E402


def wait_for(cond, timeout=10.0, step=0.1, msg="condition"):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        try:
            last = cond()
            if last:
                return last
        except Exception as e:  # keep polling
            last = e
        time.sleep(step)
    raise AssertionError("timeout waiting for %s (last=%r)" % (msg, last))


def http_json(url, data=None, method=None, headers=None, timeout=5):
    req = urllib.request.Request(url, method=method or ("POST" if data is not None else "GET"),
                                 data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, body


# DF-42 makes the admin token mandatory for a real hub start. Most tests build throw-away hubs without one, so the start
# gate is switched off for the whole test session (module-level, because some fixtures are module-scoped).
# tests/test_df_token.py puts the real check back (monkeypatch) to prove the gate works.
import grainguard_hub.app as _app  # noqa: E402
_app.check_admin_token = lambda cfg: None


@pytest.fixture
def broker(tmp_path):
    try:
        b = _start_broker(str(tmp_path))
    except RuntimeError as e:
        pytest.skip(str(e))
    yield b
    b.stop()


# ----------------------------------------------------------- engine harness
MACS = ["a4cf12ab34%02x" % (0x10 + i) for i in range(6)]


class Harness:
    """Engine + Store with a fake clock, no MQTT, no HTTP."""

    def __init__(self, tmp_path, assign=6, start=None, **cfgkw):
        kw = dict(data_dir=str(tmp_path), mqtt_enabled=False, tz="Asia/Bangkok")
        kw.update(cfgkw)
        self.cfg = Config(**kw)
        self.store = Store(self.cfg.db(), self.cfg.tz)
        self.now = start if start is not None else 1_790_000_000.0
        self.changes = 0
        self.eng = Engine(self.cfg, self.store, clock=lambda: self.now,
                          on_class_change=self._chg)
        self.macs = MACS[:assign]
        for i, m in enumerate(self.macs):
            self.eng.assign(i + 1, m)
        self.seqs = {m: 0 for m in MACS}
        self.t0 = {m: self.now for m in MACS}

    def _chg(self):
        self.changes += 1

    def frame(self, mac, **kw):
        f = {"v": 1, "seq": self.seqs[mac], "up": int(self.now - self.t0[mac]) + 100, "st": "RUN", "mode": "ALARM_ON",
             "env": 150.0, "base": 150.0, "ratio": 1.0, "act": 90.0, "sat": 0, "flat": 0, "vin": 24.1, "tc": 40.0,
             "fw": "1.0.0", "ack": 0, "tl": {"r": 0, "y": 0, "g": 1, "b": 1}, "rst": 1, "link": 100}
        f.update(kw)
        return f

    def tele(self, mac, **kw):
        self.eng.on_tele(mac, self.frame(mac, **kw), self.now)
        self.seqs[mac] += 1

    def run(self, seconds, macs=None, per=None, **kw):
        """Advance `seconds` one by one: every mac in `macs` sends a tele (kw / per(i,mac)->dict|None), then tick."""
        macs = self.macs if macs is None else macs
        for i in range(int(seconds)):
            for m in macs:
                o = dict(kw)
                if per is not None:
                    r = per(i, m)
                    if r is None:
                        continue
                    o.update(r)
                if o.pop("_lose", False):       # packet lost on the wire: node's seq advances, hub sees nothing
                    self.seqs[m] += 1
                    continue
                self.tele(m, **o)
            self.now += 1
            self.eng.tick(self.now)
        return self

    def idle(self, seconds):
        return self.run(seconds, macs=[])

    def events(self, type_=None, n=None):
        rows = self.store.list_events(1000, n=n, types=[type_] if type_ else None)
        return list(reversed(rows))

    def cls(self, n):
        return self.eng.snapshot(self.now)["nodes"][n - 1]["cls"]

    def node(self, n):
        return self.eng.snapshot(self.now)["nodes"][n - 1]

    def flags(self, n):
        return set(self.node(n)["health"])

    def cloud_queue(self):
        return self.store.q("SELECT * FROM cloud_queue ORDER BY seq")


@pytest.fixture
def H(tmp_path):
    made = []

    def make(**kw):
        h = Harness(tmp_path / ("h%d" % len(made)), **kw)
        made.append(h)
        return h
    yield make
    for h in made:
        h.store.close()
