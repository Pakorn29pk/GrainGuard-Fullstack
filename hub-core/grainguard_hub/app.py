"""Hub orchestrator: store + engine + MQTT + uplink + HTTP, 1 Hz housekeeping loop, graceful shutdown."""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import signal
import socket
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from . import __version__, sdnotify
from .config import Config, check_admin_token, load_config
from .engine import Engine
from .lifecycle import Lifecycle
from .selfcheck import SelfCheck
from .store import Store
from .uplink import Uplink, read_cpu_temp

log = logging.getLogger("gg.hub")


def make_carrier_fn(iface: str) -> Optional[Callable[[], Optional[bool]]]:
    if not iface:
        return None
    path = "/sys/class/net/%s/carrier" % iface

    def fn() -> Optional[bool]:
        try:
            with open(path) as fh:
                return fh.read().strip() == "1"
        except OSError:
            # file unreadable when the interface is administratively down
            return False if os.path.exists("/sys/class/net/%s" % iface) else None
    return fn


def daily_text(date: str, rows: List[Dict[str, Any]], until: str, label: Callable[[int], str]) -> str:
    if not rows:
        return "สรุปประจำวัน %s (%s)\nยังไม่มีข้อมูล" % (date, until)
    lines = ["สรุปประจำวัน %s (%s)" % (date, until)]
    tot_alarm = 0
    for r in rows:
        tot_alarm += r["alarm_count"]
        s = "%s: ขัด %.1f ชม. · พัก %.1f ชม. · ALARM %d ครั้ง" % (
            label(r["node"]), r["run_min"] / 60.0, r["rest_min"] / 60.0, r["alarm_count"])
        if r["offline_min"] >= 1:
            s += " · ไม่เชื่อมต่อ %d นาที" % round(r["offline_min"])
        if r["health_incidents"]:
            s += " · ผิดปกติ %d ครั้ง" % r["health_incidents"]
        lines.append(s)
    lines.append("รวม ALARM %d ครั้ง" % tot_alarm)
    return "\n".join(lines)


class Hub:
    def __init__(self, cfg: Config, clock: Callable[[], float] = time.time, mqtt_enabled: Optional[bool] = None,
                 http_enabled: bool = True, *, notify_systemd: bool = True):
        self.cfg = cfg
        self.clock = clock
        if mqtt_enabled is not None:
            cfg.mqtt_enabled = mqtt_enabled
        self.http_enabled = http_enabled
        self.notify_systemd = notify_systemd
        os.makedirs(cfg.data_dir, exist_ok=True)
        self.store = Store(cfg.db(), cfg.tz, cfg.tele_retention_days)
        self.carrier_fn = make_carrier_fn(cfg.nic_a)
        self.uplink: Uplink
        self.engine = Engine(cfg, self.store, clock, on_class_change=lambda: self.uplink.wake_heartbeat(),
                             on_event=lambda: self.uplink.wake_events(), carrier_fn=self.carrier_fn)
        self.uplink = Uplink(cfg, self.store, self.engine.snapshot, self.carrier_fn, clock)
        self.lifecycle = Lifecycle(self.store, cfg, clock, emit=self._lc_emit)
        self.selfcheck = SelfCheck(cfg, self.engine, self.store, self.uplink, cpu_fn=self.cpu_temp, clock=clock)
        self.mqtt = None
        self._stop = threading.Event()
        self._tick_thread: Optional[threading.Thread] = None
        self._http_thread: Optional[threading.Thread] = None
        self._server = None
        self._last_tick = time.monotonic()
        self._last_prune = 0.0
        self._last_touch = 0.0
        self._last_wd = 0.0
        self._cpu_cache = (0.0, -1.0)
        self.started = False

    # --------------------------------------------------------------- misc
    def tick_age(self) -> float:
        return time.monotonic() - self._last_tick

    def cpu_temp(self) -> float:
        t, v = self._cpu_cache
        if time.monotonic() - t > 15:
            v = read_cpu_temp()
            self._cpu_cache = (time.monotonic(), v)
        return v

    def _lc_emit(self, now: float, n: int, type_: str, text: str, data: Dict[str, Any]) -> None:
        eng = self.engine
        with eng.lock:
            mac = eng.slot_mac(n)
            lab = eng.label_of(eng.states[mac]) if mac else eng.default_label(n)
            eng._event(now, n, mac, type_, "%s: %s" % (lab, text), data, cloud="HEALTH", src="hub")

    def send_cmd(self, mac: str, payload: Dict[str, Any]) -> bool:
        return bool(self.mqtt and self.mqtt.send_cmd(mac, payload))

    # ----------------------------------------------------------- lifecycle
    def start(self) -> None:
        cfg = self.cfg
        bad = check_admin_token(cfg)
        if bad:                                         # DF-42: no admin token = the hub does not start
            raise SystemExit("GrainGuard hub: " + bad)
        logging.getLogger().info("GrainGuard hub %s starting (hub_id=%s, db=%s)", __version__, cfg.hub_id, cfg.db())
        unclean = self.store.meta_get("run_state") == "running"
        self.store.meta_set("run_state", "running")
        self.engine._event(self.clock(), 0, None, "HUB_BOOT", "ฮับเริ่มทำงาน (เปิดเครื่อง/รีสตาร์ท)",
                           {"version": __version__, "unclean_previous_stop": unclean}, cloud="HUB_BOOT")
        if unclean:
            self.engine.note_restart("unclean", self.clock(), {"what": "hub-core"})
        if cfg.mqtt_enabled:
            from .mqtt_io import MqttBridge
            self.mqtt = MqttBridge(cfg, self.engine)
            self.mqtt.start()
        self.uplink.start()
        self._tick_thread = threading.Thread(target=self._loop, name="gg-tick", daemon=True)
        self._tick_thread.start()
        if self.http_enabled:
            self._start_http()
        self.started = True
        if self.notify_systemd:
            sdnotify.notify("READY=1")

    def _start_http(self) -> None:
        import uvicorn
        from .api import create_app
        app = create_app(self)
        conf = uvicorn.Config(app, host=self.cfg.http_host, port=self.cfg.http_port, log_level="warning",
                              access_log=False, lifespan="off")
        self._server = uvicorn.Server(conf)
        extras = [h.strip() for h in (self.cfg.http_extra_hosts or "").split(",") if h.strip()]
        specific = self.cfg.http_host not in ("0.0.0.0", "127.0.0.1", "localhost", "::", "")
        if extras or specific:
            # listen on several specific addresses (node LAN + mill LAN) instead of 0.0.0.0. IP_FREEBIND lets us bind an address
            # that is not up yet (e.g. UE300 unplugged at boot) so the dashboard never depends on link order.
            socks = []
            for host in [self.cfg.http_host] + extras:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    s.setsockopt(socket.SOL_IP, getattr(socket, "IP_FREEBIND", 15), 1)
                except OSError:
                    pass
                try:
                    s.bind((host, self.cfg.http_port))
                    s.listen(64)
                    s.set_inheritable(True)
                    socks.append(s)
                except OSError as e:
                    s.close()
                    log.error("cannot listen on %s:%s (%s)", host, self.cfg.http_port, e)
            if not socks:
                raise SystemExit("GrainGuard hub: dashboard cannot listen on any configured address")
            self._http_thread = threading.Thread(target=lambda: self._server.run(sockets=socks), name="gg-http", daemon=True)
        else:
            self._http_thread = threading.Thread(target=self._server.run, name="gg-http", daemon=True)
        self._http_thread.start()
        for _ in range(100):            # wait until listening (so callers can use the port)
            if getattr(self._server, "started", False):
                break
            time.sleep(0.05)

    @property
    def http_port(self) -> int:
        try:
            return self._server.servers[0].sockets[0].getsockname()[1]
        except Exception:
            return self.cfg.http_port

    def stop(self) -> None:
        if not self.started:
            return
        self.started = False
        log.info("shutting down")
        if self.notify_systemd:
            sdnotify.notify("STOPPING=1")
        self._stop.set()
        if self._tick_thread:
            self._tick_thread.join(timeout=5)
        if self.mqtt:
            self.mqtt.stop()
        self.uplink.stop()
        try:
            self.store.meta_set("run_state", "stopped")
        except Exception:
            log.exception("could not record clean shutdown")
        if self._server is not None:
            self._server.should_exit = True
            if self._http_thread:
                self._http_thread.join(timeout=5)
        self.store.close()
        log.info("stopped cleanly")

    def wait(self) -> None:
        self._stop.wait()

    def request_stop(self) -> None:
        self._stop.set()

    # --------------------------------------------------------------- loop
    def _loop(self) -> None:
        nxt = time.monotonic()
        wd = sdnotify.watchdog_interval() if self.notify_systemd else 0
        while not self._stop.is_set():
            now = self.clock()
            for name, fn in (("engine", self.engine.tick), ("flush", self._flush),
                             ("housekeeping", self._housekeeping), ("daily", self._daily),
                             ("selfcheck", self.selfcheck.tick), ("lifecycle", self.lifecycle.tick)):
                try:
                    fn(now) if name != "flush" else fn()
                except Exception:
                    log.exception("%s step failed", name)
            self._last_tick = time.monotonic()
            if wd and self._last_tick - self._last_wd >= wd:
                sdnotify.notify("WATCHDOG=1")
                self._last_wd = self._last_tick
            nxt += 1.0
            delay = nxt - time.monotonic()
            if delay < -5:
                nxt = time.monotonic()
            self._stop.wait(max(0.0, delay))

    def _flush(self) -> None:
        self.store.flush_tele()

    def _housekeeping(self, now: float) -> None:
        mono = time.monotonic()
        if int(now) // 60 != getattr(self, "_last_min", None):
            self._last_min = int(now) // 60
            self.store.rollup(now)
        if mono - self._last_touch >= 60:
            self._last_touch = mono
            with self.engine.lock:
                rows = [(st.last_rx, st.last.get("fw"), st.mac) for st in self.engine.states.values() if st.last_rx]
            self.store.touch_nodes(rows)
        if mono - self._last_prune >= 3600:
            self._last_prune = mono
            n = self.store.prune(now)
            if n:
                log.info("pruned %d tele_1s rows", n)
            self.store.err_prune(now - 400 * 86400)

    # ------------------------------------------------------- daily summary
    def _daily(self, now: float) -> None:
        for hhmm in [x.strip() for x in self.cfg.daily_times.split(",") if x.strip()]:
            hh, mm = (int(x) for x in hhmm.split(":"))
            ld = self.store.local_dt(now)
            slot = ld.replace(hour=hh, minute=mm, second=0, microsecond=0)
            slot_ts = slot.timestamp()
            if not (slot_ts + 5 <= now < slot_ts + 6 * 3600):
                continue
            key = "daily_done:%s:%s" % (slot.date().isoformat(), hhmm)
            if self.store.meta_get(key) is not None:
                continue
            self.store.meta_set(key, str(int(now)))
            self.run_daily(now, slot, push=(now - slot_ts) <= 2 * 3600)

    def run_daily(self, now: float, slot, push: bool = True) -> List[Dict[str, Any]]:
        """Compute + store the summary for the slot's day (00:00 slot -> previous day, final)."""
        self.store.flush_tele()
        self.store.rollup(now)
        final = slot.hour == 0 and slot.minute == 0
        d = (slot.date() - dt.timedelta(days=1)) if final else slot.date()
        date = d.isoformat()
        rows = self.store.compute_daily(date, now, final=final, save=True)
        until = "ทั้งวัน" if final else "ถึง %02d:%02d" % (slot.hour, slot.minute)
        with self.engine.lock:
            labels = {s.machine: self.engine.label_of(s) for s in self.engine.states.values() if s.assigned}
        text = daily_text(date, rows, until, lambda n: labels.get(n) or self.engine.default_label(n))
        if push:
            self.engine._event(now, 0, None, "DAILY", text, {"date": date, "final": final, "rows": rows}, cloud="DAILY")
        log.info("daily summary %s computed (%d rows, push=%s)", date, len(rows), push)
        return rows


def setup_logging() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="grainguard_hub")
    ap.add_argument("--config", help="YAML config file (default: $HUB_CONFIG or ./config.yaml)")
    args = ap.parse_args(argv)
    setup_logging()
    cfg = load_config(args.config)
    hub = Hub(cfg)

    def on_sig(signum, frame):
        log.info("signal %s received", signum)
        hub.request_stop()

    signal.signal(signal.SIGTERM, on_sig)
    signal.signal(signal.SIGINT, on_sig)
    hub.start()
    hub.wait()
    hub.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
