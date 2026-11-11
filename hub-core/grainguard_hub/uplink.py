"""Cloud uplink: signed heartbeat + store-and-forward /api/event queue.

* Heartbeat: every ``heartbeat_s`` and immediately (coalesced, <=1/s) on any class change.
  Heartbeats are *state*, not history: a failed one is simply replaced by the next.
* Events: persisted in SQLite (``cloud_queue``) in the same transaction as the event row.
  A single worker sends strictly in ``seq`` order; head-of-line retry with exponential
  backoff (1,2,4 .. 60 s, jitter) until 2xx.  409 (= already have it) counts as delivered,
  so ``(hub, seq)`` de-duplication works across retries and hub restarts (seq is the
  AUTOINCREMENT queue key).  A permanent 400/422 is parked ("dead") after 5 attempts so one
  bad row cannot block the queue; 401/403/5xx/network errors are retried forever.
* Works fully offline: with no CLOUD_URL (or no internet) the queue just grows (capped).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import random
import shutil
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, Optional, Tuple

from .config import Config
from .store import Store

log = logging.getLogger("gg.uplink")


def sign(secret: str, ts: str, body: bytes) -> str:
    return hmac.new(secret.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()


def read_cpu_temp() -> float:
    best = -1.0
    try:
        base = "/sys/class/thermal"
        for z in os.listdir(base):
            if not z.startswith("thermal_zone"):
                continue
            try:
                with open(os.path.join(base, z, "temp")) as fh:
                    best = max(best, int(fh.read().strip()) / 1000.0)
            except Exception:
                pass
    except Exception:
        pass
    return round(best, 1)


def backoff_s(attempts: int) -> float:
    base = min(60.0, 2.0 ** min(attempts, 6))
    return base * (0.75 + 0.5 * random.random())


class Uplink:
    def __init__(self, cfg: Config, store: Store, snapshot_fn: Callable[[], Dict[str, Any]],
                 carrier_fn: Optional[Callable[[], Optional[bool]]] = None,
                 clock: Callable[[], float] = time.time):
        self.cfg, self.store, self.snapshot_fn, self.clock = cfg, store, snapshot_fn, clock
        self.carrier_fn = carrier_fn
        self._stop = threading.Event()
        self._hb_wake = threading.Event()
        self._q_wake = threading.Event()
        self._threads: list = []
        self.hb_seq = int(clock())            # monotonic across restarts (grows >= 1 per 30 s)
        self.last_ok: Optional[float] = None  # last successful cloud round trip
        self.last_attempt_ok: Optional[bool] = None
        self.inet_ms = -1
        self.last_err = ""
        self.last_hb_ok: Optional[float] = None
        self.last_success: Optional[float] = None   # last 2xx/409 answer (delivery really worked)
        self.last_code: Optional[int] = None        # HTTP status of the most recent attempt (None = network error)
        self.auth_fail_streak = 0                   # consecutive 401/403 answers (E504)
        self.sent_events = 0
        self.boot_ts = clock()
        self.max_backoff = 60.0

    @property
    def configured(self) -> bool:
        return bool(self.cfg.cloud_url)

    # --------------------------------------------------------------- http
    def _post(self, path: str, payload: Dict[str, Any]) -> Tuple[Optional[int], str]:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ts = str(int(self.clock()))
        req = urllib.request.Request(
            self.cfg.cloud_url.rstrip("/") + path, data=body, method="POST",
            headers={"Content-Type": "application/json", "X-GG-Ts": ts,
                     "X-GG-Sig": sign(self.cfg.cloud_secret, ts, body), "User-Agent": "grainguard-hub/1"})
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.cloud_timeout_s) as r:
                r.read(1024)
                code = r.status
        except urllib.error.HTTPError as e:
            code = e.code
            try:
                e.read(256)
            except Exception:
                pass
        except Exception as e:  # DNS, refused, timeout, TLS ...
            self.last_code = None
            self.last_attempt_ok = False
            self.last_err = "%s: %s" % (type(e).__name__, e)
            return None, self.last_err
        ms = int((time.monotonic() - t0) * 1000)
        self.last_code = code
        self.auth_fail_streak = self.auth_fail_streak + 1 if code in (401, 403) else 0
        if 200 <= code < 300 or code == 409:
            self.last_ok, self.last_attempt_ok, self.inet_ms, self.last_err = self.clock(), True, ms, ""
            self.last_success = self.last_ok
        else:
            # server reachable but unhappy: internet is fine, delivery is not
            self.last_ok, self.inet_ms = self.clock(), ms
            self.last_attempt_ok = False
            self.last_err = "HTTP %d" % code
        return code, self.last_err

    # ---------------------------------------------------------- heartbeat
    def build_heartbeat(self) -> Dict[str, Any]:
        snap = self.snapshot_fn()
        self.hb_seq += 1
        nodes = []
        for nd in snap["nodes"] + snap["new"]:
            if nd["cls"] == "empty":
                continue
            nodes.append({
                "n": nd["n"] or 0, "mac": nd["mac"], "label": nd["label"], "state": nd["state"], "cls": nd["cls"],
                "last_seen_s": nd["last_seen_s"] if nd["last_seen_s"] is not None else -1,
                "ratio": nd.get("ratio") if nd.get("ratio") is not None else 0.0,
                "vin": nd.get("vin") if nd.get("vin") is not None else 0.0,
                "health": nd["health"], "codes": nd.get("codes", []), "since": nd["since"],
            })
        try:
            du = shutil.disk_usage(self.cfg.data_dir if os.path.isdir(self.cfg.data_dir) else ".")
            disk = int(round(100.0 * du.used / du.total))
        except Exception:
            disk = -1
        hub = snap["hub"]
        lan = hub["nic_a_up"] if hub["nic_a_up"] is not None else (not hub["plant_power_off"])
        return {
            "hub": self.cfg.hub_id, "seq": self.hb_seq, "up": hub["up_s"], "ts": int(self.clock()),
            "inet_ms": self.inet_ms, "disk_pct": disk, "cpu_temp": read_cpu_temp(),
            "node_lan_up": bool(lan), "plant_power_off": bool(hub["plant_power_off"]),
            "hub_codes": hub.get("codes", []), "nodes": nodes, "today": snap["today"],
        }

    def send_heartbeat(self) -> bool:
        if not self.configured:
            return False
        hb = self.build_heartbeat()
        code, _ = self._post("/api/heartbeat", hb)
        ok = code is not None and 200 <= code < 300
        if ok:
            self.last_hb_ok = self.clock()
        return ok

    def wake_heartbeat(self) -> None:
        self._hb_wake.set()

    def wake_events(self) -> None:
        self._q_wake.set()

    def _hb_loop(self) -> None:
        last = 0.0
        while not self._stop.is_set():
            woke = self._hb_wake.wait(timeout=max(0.2, self.cfg.heartbeat_s - (time.monotonic() - last)))
            if self._stop.is_set():
                break
            if woke:
                self._hb_wake.clear()
                # coalesce bursts of class changes; never more than one heartbeat per second
                self._stop.wait(max(0.3, 1.0 - (time.monotonic() - last)))
                self._hb_wake.clear()
                if self._stop.is_set():
                    break
            try:
                self.send_heartbeat()
            except Exception:
                log.exception("heartbeat failed")
            last = time.monotonic()

    # ------------------------------------------------------------- events
    @staticmethod
    def event_body(hub: str, row: Dict[str, Any]) -> Dict[str, Any]:
        try:
            data = json.loads(row["data"]) if row.get("data") else {}
        except Exception:
            data = {}
        body = {"hub": hub, "seq": row["seq"], "ts": int(row["ts"]), "n": row["n"], "type": row["type"],
                "text": row["text"] or "", "data": data}
        if row.get("code"):
            body["code"] = row["code"]
        return body

    def pump_once(self) -> str:
        """Try to deliver the head of the queue. Returns 'empty' | 'sent' | 'wait' | 'fail' | 'dead'."""
        row = self.store.queue_head()
        if row is None:
            return "empty"
        now = self.clock()
        if row["next_try"] > now:
            return "wait"
        code, err = self._post("/api/event", self.event_body(self.cfg.hub_id, row))
        if code is not None and (200 <= code < 300 or code == 409):
            self.store.queue_done(row["seq"])
            self.sent_events += 1
            return "sent"
        attempts = row["attempts"] + 1
        if code in (400, 422) and attempts >= 5:
            log.error("event seq=%s rejected permanently (HTTP %s) - parked", row["seq"], code)
            self.store.queue_fail(row["seq"], now, err or ("HTTP %s" % code), dead=True)
            return "dead"
        # Retry delay starts after the attempt, otherwise a slow timeout consumes it.
        self.store.queue_fail(row["seq"], self.clock() + min(self.max_backoff, backoff_s(attempts)),
                              err or ("HTTP %s" % code))
        return "fail"

    def _q_loop(self) -> None:
        idle = 0.0
        while not self._stop.is_set():
            if not self.configured:
                self._q_wake.wait(timeout=5.0)
                self._q_wake.clear()
                continue
            try:
                r = self.pump_once()
            except Exception:
                log.exception("queue pump failed")
                r = "fail"
                self._stop.wait(2.0)
            if r in ("sent", "dead"):
                continue                      # drain quickly
            if r == "empty":
                self._q_wake.wait(timeout=5.0)
                self._q_wake.clear()
            else:                              # wait / fail: sleep until next_try (or a wake)
                head = self.store.queue_head()
                delay = 1.0 if head is None else max(0.1, min(5.0, head["next_try"] - self.clock()))
                self._stop.wait(delay)

    # ------------------------------------------------------------- status
    def health(self) -> Dict[str, Any]:
        """Facts for the hub self-check (E503 / E504)."""
        now = self.clock()
        ref = max(self.last_success or 0.0, self.boot_ts)
        return {"configured": self.configured, "since_ok_s": now - ref, "auth_fail_streak": self.auth_fail_streak,
                "last_code": self.last_code}

    def status(self) -> Dict[str, Any]:
        qs = self.store.queue_stats()
        now = self.clock()
        if not self.configured:
            state = "unconfigured"
        elif self.last_ok is not None and now - self.last_ok < max(90.0, 3 * self.cfg.heartbeat_s) and self.last_attempt_ok is not False:
            state = "ok"
        elif self.last_ok is not None and now - self.last_ok < max(90.0, 3 * self.cfg.heartbeat_s):
            state = "degraded"
        else:
            state = "down"
        return {"state": state, "configured": self.configured, "inet_ms": self.inet_ms,
                "last_ok_age_s": round(now - self.last_ok, 1) if self.last_ok else None,
                "queue": qs["pending"], "queue_dead": qs["dead"],
                "oldest_age_s": round(now - qs["oldest_ts"]) if qs["oldest_ts"] else None,
                "last_err": self.last_err, "sent_events": self.sent_events}

    # ---------------------------------------------------------- lifecycle
    def start(self) -> None:
        for fn, name in ((self._hb_loop, "gg-heartbeat"), (self._q_loop, "gg-eventq")):
            t = threading.Thread(target=fn, name=name, daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self, flush_s: float = 3.0) -> None:
        self._stop.set()
        self._hb_wake.set()
        self._q_wake.set()
        for t in self._threads:
            t.join(timeout=3)
        # best effort: push whatever is still queued for a moment (queue is persistent anyway)
        if self.configured and flush_s > 0:
            end = time.monotonic() + flush_s
            while time.monotonic() < end:
                try:
                    if self.pump_once() in ("empty", "fail", "wait"):
                        break
                except Exception:
                    break
