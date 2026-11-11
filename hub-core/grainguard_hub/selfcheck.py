"""Hub self-checks -> E5xx codes (E501 disk, E502 database, E503/E504 cloud uplink, E505 clock, E507 CPU temperature).

E506 (service restart) and E508 (NIC-A) are raised by the engine / app because they come from events, not polling.
All inputs are injectable so every rule is unit-testable with a fake clock.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import threading
import time
from typing import Any, Callable, Dict, Optional

from .config import Config

log = logging.getLogger("gg.selfcheck")

CORRUPT_RE = re.compile(r"malformed|corrupt|disk i/o|not a database|disk image|database disk", re.I)


def default_disk_pct(path: str) -> Callable[[], float]:
    def fn() -> float:
        try:
            du = shutil.disk_usage(path if os.path.isdir(path) else ".")
            return 100.0 * du.used / du.total
        except Exception:
            return -1.0
    return fn


def chrony_synced(cmd: str) -> Optional[bool]:
    """True = synchronised, False = not, None = cannot tell (no chronyc installed / timeout): tolerated, never an error."""
    if not cmd:
        return None
    try:
        out = subprocess.run(cmd.split(), capture_output=True, text=True, timeout=3).stdout
    except Exception:
        return None
    if not out:
        return None
    m = re.search(r"Leap status\s*:\s*(.+)", out)
    if m:
        return "not synchronised" not in m.group(1).lower()
    if re.search(r"Reference ID\s*:\s*0{8}", out):
        return False
    return None


class SelfCheck:
    def __init__(self, cfg: Config, engine, store, uplink=None, cpu_fn: Optional[Callable[[], float]] = None,
                 disk_fn: Optional[Callable[[], float]] = None, ntp_fn: Optional[Callable[[], Optional[bool]]] = None,
                 clock: Callable[[], float] = time.time, mono: Callable[[], float] = time.monotonic,
                 threaded: bool = True):
        self.cfg, self.eng, self.store, self.uplink = cfg, engine, store, uplink
        self.cpu_fn = cpu_fn
        self.disk_fn = disk_fn or default_disk_pct(cfg.data_dir)
        self.ntp_fn = ntp_fn or (lambda: chrony_synced(cfg.ntp_cmd))
        self.clock, self.mono = clock, mono
        self.threaded = threaded
        t = clock()
        self._last_run = -1e9
        self._last_wall, self._last_mono = t, mono()
        self._boot = t
        self._ntp_t = -1e9
        self._ntp_bad_since: Optional[float] = None
        self._jump_until = 0.0
        self._db_seen_errors = 0
        self._db_check_t = -1e9
        self._db_bad = False
        self._db_pending = False
        self._db_day = ""
        self._db_running = False
        self._first_done = cfg.integrity_first_s <= 0
        self.last_db_result = ""

    # ------------------------------------------------------------------
    def tick(self, now: Optional[float] = None, mono: Optional[float] = None) -> None:
        now = self.clock() if now is None else now
        mono = self.mono() if mono is None else mono
        # wall-clock jump detection must look at every tick, the rest is throttled
        dw, dm = now - self._last_wall, mono - self._last_mono
        self._last_wall, self._last_mono = now, mono
        if abs(dw - dm) > self.cfg.clock_jump_s:
            self._jump_until = now + 3600.0
            log.warning("system clock jumped by %.0f s", dw - dm)
        if now - self._last_run < self.cfg.selfcheck_s:
            return
        self._last_run = now
        for name, fn in (("disk", self._disk), ("cpu", self._cpu), ("uplink", self._uplink), ("clock", self._clock),
                         ("db", self._db)):
            try:
                fn(now)
            except Exception:
                log.exception("self-check %s failed", name)

    # ------------------------------------------------------------------
    def _hyst(self, code: str, value: float, hi: float, lo: float, now: float, detail: Dict[str, Any], note: str) -> None:
        on = self.eng.errors.is_open(code, "hub")
        if value < 0:                      # unknown reading: do not change anything
            return
        if not on and value > hi:
            self.eng.set_hub_code(code, True, now, detail, note)
        elif on and value <= lo:
            self.eng.set_hub_code(code, False, now)

    def _disk(self, now: float) -> None:
        v = self.disk_fn()
        self._hyst("E501", v, self.cfg.disk_warn_pct, self.cfg.disk_clear_pct, now, {"disk_pct": round(v)},
                   "ใช้ไปแล้ว %d%%" % round(v))

    def _cpu(self, now: float) -> None:
        if self.cpu_fn is None:
            return
        v = self.cpu_fn()
        self._hyst("E507", v, self.cfg.cpu_hot_c, self.cfg.cpu_clear_c, now, {"cpu_temp": v}, "%.0f °C" % v)

    def _uplink(self, now: float) -> None:
        if self.uplink is None:
            return
        h = self.uplink.health()
        auth = h["auth_fail_streak"] >= self.cfg.auth_fail_count
        if auth:
            self.eng.set_hub_code("E504", True, now, {"http": h["last_code"]})
            self.eng.set_hub_code("E503", False, now)
            return
        self.eng.set_hub_code("E504", False, now)
        if h["configured"] and h["since_ok_s"] > self.cfg.uplink_fail_s:
            self.eng.set_hub_code("E503", True, now, {"since_ok_s": round(h["since_ok_s"])},
                                  "ส่งข้อมูลไม่สำเร็จมา %d นาที" % round(h["since_ok_s"] / 60))
        elif h["since_ok_s"] <= self.cfg.uplink_fail_s:
            self.eng.set_hub_code("E503", False, now)

    def _clock(self, now: float) -> None:
        if now - self._ntp_t >= 60:
            self._ntp_t = now
            ok = self.ntp_fn()
            if ok is False:
                if self._ntp_bad_since is None:
                    self._ntp_bad_since = now
            else:
                self._ntp_bad_since = None
        bad = self._ntp_bad_since is not None and now - self._ntp_bad_since >= self.cfg.ntp_unsync_s
        jumped = now < self._jump_until
        if bad or jumped:
            self.eng.set_hub_code("E505", True, now, {"unsynced": bool(bad), "jump": bool(jumped)},
                                  "นาฬิกาไม่ sync นาน" if bad else "เวลากระโดด")
        else:
            self.eng.set_hub_code("E505", False, now)

    # --- E502 --------------------------------------------------------
    def _due_daily(self, now: float) -> bool:
        try:
            hh, mm = (int(x) for x in self.cfg.integrity_time.split(":"))
        except ValueError:
            return False
        ld = self.store.local_dt(now)
        slot = ld.replace(hour=hh, minute=mm, second=0, microsecond=0)
        day = ld.date().isoformat()
        if now >= slot.timestamp() and self._db_day != day:
            return True
        return False

    def _db(self, now: float) -> None:
        errs = self.store.db_errors
        if errs != self._db_seen_errors:
            self._db_seen_errors = errs
            if CORRUPT_RE.search(self.store.last_db_error or ""):
                self.eng.set_hub_code("E502", True, now, {"error": self.store.last_db_error[:160]})
                self._db_bad = True
            self._db_pending = True               # verify right away, whatever the error was
        first = not self._first_done and now - self._boot >= self.cfg.integrity_first_s
        if self._db_running or not (self._db_pending or self._due_daily(now) or first):
            return
        if now - self._db_check_t < 30:
            return
        self._first_done = True
        self._db_pending = False
        self._db_check_t = now
        self._db_day = self.store.local_dt(now).date().isoformat()
        if self.threaded:
            self._db_running = True
            threading.Thread(target=self._run_check, args=(now,), name="gg-dbcheck", daemon=True).start()
        else:
            self._run_check(now)

    def _run_check(self, now: float) -> None:
        try:
            res = self.store.integrity_quick()
            self.last_db_result = res
            if res != "ok":
                self._db_bad = True
                self.eng.set_hub_code("E502", True, self.clock() if self.threaded else now,
                                      {"quick_check": res}, "ตรวจฐานข้อมูลพบปัญหา: %s" % res[:80])
            else:
                self._db_bad = False
                self.eng.set_hub_code("E502", False, self.clock() if self.threaded else now)
        except Exception:
            log.exception("integrity check failed")
        finally:
            self._db_running = False
