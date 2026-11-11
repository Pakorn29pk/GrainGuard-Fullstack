#!/usr/bin/env python3
"""GrainGuard virtual node fleet (protocol v1).

Spawns N virtual ESP32 nodes that talk to the hub's MQTT broker exactly like the real nodes:
  gg/<id>/status (retained, LWT "offline"), gg/<id>/tele @1 Hz, gg/<id>/evt, and listen on gg/<id>/cmd.

Realistic behaviour: REST/RUN cycling, noisy env/vin/temperature, occasional local ALARM,
and injectable faults: flatline, saturation, drift, vin sag, reboot, silent link, plant power off.
Design Freeze P2U-B (DF-50..54): optional second sensor channel B (chb=True -> tele gets dec/fa/b, FAULT carries "ch"),
faults flatline_b / saturation_b / alarm_b, a LATCHED alarm that survives a reboot (re-reported as ALARM_ON restored=1),
tele "ackms" (how long the ACK button has been held, ms) and the hub command {"cmd":"cal"} (event CAL).

CLI:
  python sim/node_sim.py --host 127.0.0.1 --port 1883 --nodes 6                 # steady-state mill
  python sim/node_sim.py ... --demo                                              # scripted fault tour
  mosquitto_pub -t gg-sim/ctl -m '{"node":3,"do":"alarm","dur":30}'              # live control

As a library (used by the tests):  fleet = Fleet(host, port); fleet.start(); fleet.nodes[2].inject("flatline", 70)
"""
from __future__ import annotations

import argparse
import json
import math
import random
import signal
import threading
import time
from typing import Any, Callable, Dict, List, Optional

import paho.mqtt.client as mqtt

DEFAULT_MACS = ["a4cf12ab34%02x" % (0x10 + i) for i in range(6)]


class VirtualNode:
    TRIP = 2.5

    def __init__(self, mac: str, host: str, port: int, user: Optional[str] = None, password: Optional[str] = None,
                 fw: str = "1.0.0", seed: Optional[int] = None, auto_cycle: bool = True, level: Optional[float] = None,
                 clock: Callable[[], float] = time.time, mode: str = "ALARM_ON",
                 chb: bool = False, dec: str = "OR"):
        self.mac, self.host, self.port, self.user, self.password = mac, host, port, user, password
        self.fw = fw
        self.rng = random.Random(seed if seed is not None else int(mac[-4:], 16))
        self.level = level if level is not None else self.rng.uniform(110, 220)   # running env energy
        self.clock = clock
        self.auto_cycle = auto_cycle
        self.client: Optional[mqtt.Client] = None
        self.lock = threading.RLock()
        self.powered = False
        self.silent_until = 0.0
        self.t_boot = clock()
        self.seq = 0
        self.state = "REST"
        self.mode = mode          # SHADOW | ALARM_ON | RECORD   (protocol v1.1: st is always the true state, mode separate)
        self.ack = 0
        self.base = self.level
        self.env = self.level * 0.15
        self.ratio = 0.15
        self.alarm_since: Optional[float] = None
        self.alarm_hi = 0
        self.below = 0
        self.faults: Dict[str, Dict[str, Any]] = {}
        self.next_switch = clock() + self.rng.uniform(20, 90)
        self.rst = 1
        self.drift_f = 1.0
        self.published = 0
        self.cmds: List[dict] = []
        self._flat_val = 0.0
        self._flat_val_b = 0.0
        # --- channel B (piezo puck), DF-51 -----------------------------------------------------------------------------
        self.chb = chb
        self.dec = dec                      # OR | A | B | AND
        self.level_b = self.level * 0.8
        self.base_b = self.level_b
        self.env_b = self.level_b * 0.15
        self.ratio_b = 0.15
        self.hi_b = 0
        self.fa = 0                         # fault kind channel A: 0 ok, 1 flatline, 2 saturation
        self.fb = 0
        # --- survives power cycles (the real board keeps these in NVS), DF-50 ------------------------------------------
        self.latched_nv = False
        self.ack_t0: Optional[float] = None       # ACK button physically held since (inject ack_press)
        self._stuck_t0: Optional[float] = None

    # ----------------------------------------------------------- connection
    def _mk_client(self) -> mqtt.Client:
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self.mac, clean_session=True)
        if self.user is not None:
            c.username_pw_set(self.user, self.password)
        c.will_set("gg/%s/status" % self.mac, "offline", qos=1, retain=True)
        c.reconnect_delay_set(1, 5)
        c.on_connect = self._on_connect
        c.on_message = self._on_message
        return c

    def _on_connect(self, c, ud, flags, rc, props=None):
        c.subscribe("gg/%s/cmd" % self.mac, qos=1)
        c.publish("gg/%s/status" % self.mac, "online", qos=1, retain=True)
        self._evt("BOOT", {"fw": self.fw, "rst": self.rst})
        if self.latched_nv:                  # DF-50: a latched alarm is restored after a reboot and re-reported
            self._evt("ALARM_ON", {"ratio": round(self.ratio, 2), "restored": 1})

    def _on_message(self, c, ud, msg):
        try:
            d = json.loads(msg.payload)
        except Exception:
            return
        self.cmds.append(d)
        cmd = d.get("cmd")
        with self.lock:
            if cmd == "ack":
                self.ack = 1
                self._evt("ACK", {"via": "hub"})
            elif cmd == "mode" and d.get("mode") in ("SHADOW", "ALARM_ON", "RECORD"):
                self.mode = d["mode"]
                self._evt("MODE", {"mode": self.mode})
            elif cmd == "cal":
                if self.state == "ALARM":
                    self._evt("CAL", {"src": "refused"})          # DF-53: refused while an alarm is latched
                else:
                    self._evt("CAL", {"src": "start"})
                    self.base, self.base_b = self.env, self.env_b
                    self._evt("CAL", {"src": "meas"})
            elif cmd == "reboot":
                threading.Thread(target=self.reboot, daemon=True).start()

    def power_on(self, rst: int = 1) -> None:
        with self.lock:
            if self.powered:
                return
            self.t_boot = self.clock()
            self.seq = 0
            self.rst = rst
            self.state = "ALARM" if self.latched_nv else "REST"
            self.ack = 0
            self.alarm_since = time.time() if self.latched_nv else None
            self.alarm_hi = self.below = 0
            self.hi_b = 0
            self.base = self.level * self.drift_f
            self.base_b = self.level_b
            self.client = self._mk_client()
            self.powered = True
            self.silent_until = 0.0
        self.client.connect_async(self.host, self.port, keepalive=15)
        self.client.loop_start()

    def _detach(self) -> Optional[mqtt.Client]:
        """Instantly stop publishing (power gone); returns the client so its thread can be stopped afterwards."""
        with self.lock:
            if not self.powered:
                return None
            self.powered = False
            c, self.client = self.client, None
        return c

    def power_off(self, graceful: bool = False, _client: Optional[mqtt.Client] = None) -> None:
        """graceful=False emulates yanking the plug: no DISCONNECT is sent, the broker's keepalive expires (LWT)."""
        c = _client if _client is not None else self._detach()
        if c is None:
            return
        if graceful:
            try:
                c.publish("gg/%s/status" % self.mac, "offline", qos=1, retain=True).wait_for_publish(2)
                c.disconnect()
            except Exception:
                pass
            c.loop_stop()
        else:
            c.loop_stop()      # stop the network thread; socket is left dangling -> broker times out after 1.5 x keepalive

    def reboot(self, down_s: float = 3.0) -> None:
        self.power_off(graceful=False)
        time.sleep(down_s)
        self.power_on(rst=3)

    # -------------------------------------------------------------- inject
    def inject(self, kind: str, dur: float = 30.0, **kw: Any) -> None:
        now = self.clock()
        with self.lock:
            if kind == "reboot":
                threading.Thread(target=self.reboot, kwargs={"down_s": kw.get("down_s", 2.0)}, daemon=True).start()
            elif kind == "silent":
                self.silent_until = now + dur
            elif kind == "clear":
                self.faults.clear()
                self.drift_f = 1.0
                if self.state == "ALARM":            # the real board always reports the end of an alarm (DF-54 relies on it)
                    self._evt("ALARM_OFF", {"ratio": round(self.ratio, 2)})
                    self.latched_nv = False
                    self.alarm_since = None
                    self.state = "REST"
            elif kind == "set_state":
                self.state = kw["state"]
                self.next_switch = now + 1e9
            elif kind == "alarm":
                self.faults["alarm"] = {"until": now + dur}
            elif kind == "flatline":
                self.faults["flatline"] = {"until": now + dur}
                self._flat_val = self.env
            elif kind == "flatline_b":
                self.faults["flatline_b"] = {"until": now + dur}
                self._flat_val_b = self.env_b
            elif kind == "saturation_b":
                self.faults["saturation_b"] = {"until": now + dur}
            elif kind == "alarm_b":
                self.faults["alarm_b"] = {"until": now + dur}
            elif kind == "ack_press":
                self.ack_t0 = now
            elif kind == "ack_release":
                self.ack_t0 = None
            elif kind == "chb":
                self.chb = bool(kw.get("on", True))
            elif kind == "dec":
                self.dec = kw["dec"]
            elif kind == "saturation":
                self.faults["saturation"] = {"until": now + dur}
            elif kind == "vin_sag":
                self.faults["vin_sag"] = {"until": now + dur, "volts": kw.get("volts", 17.5)}
            elif kind == "vin_high":
                self.faults["vin_sag"] = {"until": now + dur, "volts": kw.get("volts", 30.0)}
            elif kind == "temp":
                self.faults["temp"] = {"until": now + dur, "tc": kw.get("tc", 78.0)}
            elif kind == "drift":
                self.faults["drift"] = {"until": now + dur, "factor": kw.get("factor", 3.0)}
            elif kind == "ack_stuck":
                self.faults["ack_stuck"] = {"until": now + dur}
            elif kind == "mode":
                self.mode = kw["mode"]
            elif kind == "fw":
                self.fw = kw.get("fw", "0.9.9")
            elif kind == "fault":
                info = {"code": kw.get("code", 7)}
                if self.chb and kw.get("ch"):
                    info["ch"] = kw["ch"]
                self._evt("FAULT", info)
                self.state = "FAULT"
            elif kind == "fault_clear":
                info = {}
                if self.chb and kw.get("ch"):
                    info["ch"] = kw["ch"]
                self._evt("FAULT_CLEAR", info)
                self.state = "REST"
            else:
                raise ValueError(kind)

    def _active(self, kind: str, now: float) -> Optional[dict]:
        f = self.faults.get(kind)
        if f and now >= f["until"]:
            del self.faults[kind]
            return None
        return f

    # ---------------------------------------------------------------- tele
    def _evt(self, typ: str, info: dict) -> None:
        c = self.client
        if c is None:
            return
        c.publish("gg/%s/evt" % self.mac, json.dumps({"seq": self.seq, "up": int(self.clock() - self.t_boot),
                                                      "type": typ, "info": info}), qos=1)

    def step(self) -> Optional[dict]:
        """Advance one second and publish the tele frame. Returns the frame (or None if not publishing)."""
        now = self.clock()
        with self.lock:
            if not self.powered or self.client is None:
                return None
            rng = self.rng
            # --- RUN/REST schedule
            if self.auto_cycle and self.state in ("RUN", "REST") and now >= self.next_switch:
                self.state = "RUN" if self.state == "REST" else "REST"
                self.next_switch = now + (rng.uniform(120, 420) if self.state == "RUN" else rng.uniform(30, 120))
            # --- faults -> signal
            drift = self._active("drift", now)
            if drift:
                self.drift_f += (drift["factor"] - self.drift_f) * 0.2
            elif self.drift_f != 1.0:
                self.drift_f += (1.0 - self.drift_f) * 0.2
                if abs(self.drift_f - 1.0) < 0.01:
                    self.drift_f = 1.0
            gain = self.drift_f
            running = self.state in ("RUN", "ALARM")
            noise = 1.0 + rng.gauss(0, 0.04)
            env = self.level * gain * (1.0 if running else 0.15) * noise
            if self._active("alarm", now):
                env = self.level * gain * rng.uniform(3.2, 4.2)
            sat, flat = 0, 0
            if self._active("saturation", now):
                sat = rng.randint(40, 400)
                env = self.level * gain * 2.0
            if self._active("flatline", now):
                env = self._flat_val
                flat = 1
            if self.state == "RUN" and not (self.faults.get("alarm") or flat or sat):
                self.base += (env - self.base) * 0.002        # slow baseline tracking while running
            if drift or self.drift_f != 1.0:
                self.base = self.level * gain      # reference moves with sensor gain
            ratio = env / self.base if self.base else 0.0
            # --- channel B (own signal, own baseline, own faults)
            env_b, ratio_b, sat_b, flat_b = 0.0, 0.0, 0, 0
            if self.chb:
                noise_b = 1.0 + rng.gauss(0, 0.04)
                env_b = self.level_b * (1.0 if running else 0.15) * noise_b
                if self._active("alarm_b", now):
                    env_b = self.level_b * rng.uniform(3.2, 4.2)
                if self._active("saturation_b", now):
                    sat_b = rng.randint(40, 400)
                    env_b = self.level_b * 2.0
                if self._active("flatline_b", now):
                    env_b = self._flat_val_b
                    flat_b = 1
                ratio_b = env_b / self.base_b if self.base_b else 0.0
            self.fa = 2 if sat else (1 if flat else 0)
            self.fb = 2 if sat_b else (1 if flat_b else 0)
            # --- local alarm decision (node decides on its own); a faulted channel counts as quiet (OR) -> see DF-51 dec rules
            if self.state in ("RUN", "ALARM"):
                hot_a = ratio >= self.TRIP and not self.fa
                hot_b = self.chb and ratio_b >= self.TRIP and not self.fb
                if not self.chb:
                    hot = hot_a
                elif self.dec == "A":
                    hot = hot_a
                elif self.dec == "B":
                    hot = hot_b
                elif self.dec == "AND":
                    hot = hot_a and hot_b
                else:
                    hot = hot_a or hot_b
                if hot:
                    self.alarm_hi += 1
                    self.below = 0
                else:
                    self.alarm_hi = 0
                    self.below += 1
                if self.state == "RUN" and self.alarm_hi >= 3:
                    self.state, self.alarm_since, self.ack = "ALARM", now, 0
                    self.latched_nv = True
                    info = {"ratio": round(ratio, 2)}
                    if self.chb:
                        info.update({"dec": self.dec, "ch": "A" if hot_a and not hot_b else ("B" if hot_b and not hot_a else "AB"),
                                     "rb": round(ratio_b, 2)})
                    self._evt("ALARM_ON", info)
                elif self.state == "ALARM" and self.below >= 5:
                    self.state = "RUN"
                    self.ack = 0
                    self.latched_nv = False
                    self._evt("ALARM_OFF", {"ratio": round(ratio, 2)})
                    self.alarm_since = None
            self.env, self.ratio = env, ratio
            self.env_b, self.ratio_b = env_b, ratio_b
            vin = 24.1 + rng.gauss(0, 0.08)
            vs = self._active("vin_sag", now)
            if vs:
                vin = vs["volts"] + rng.gauss(0, 0.05)
            tc = 38.0 + (4.0 if running else 0.0) + 2.0 * math.sin(now / 900.0) + rng.gauss(0, 0.15)
            tmp = self._active("temp", now)
            if tmp:
                tc = tmp["tc"] + rng.gauss(0, 0.2)
            stuck = self._active("ack_stuck", now)
            if stuck and self._stuck_t0 is None:
                self._stuck_t0 = now
            if not stuck:
                self._stuck_t0 = None
            t0 = self.ack_t0 if self.ack_t0 is not None else self._stuck_t0
            ackms = int((now - t0) * 1000) if t0 is not None else 0
            frame = {
                "v": 1, "seq": self.seq, "up": int(now - self.t_boot), "st": self.state, "mode": self.mode,
                "env": round(env, 3), "base": round(self.base, 3), "ratio": round(ratio, 4),
                "act": round(env * 0.6 * (1 + rng.gauss(0, 0.03)), 3), "sat": sat, "flat": flat,
                "vin": round(vin, 2), "tc": round(tc, 1), "fw": self.fw,
                "ack": self.ack, "ackms": ackms,   # ack = alarm acknowledged; ackms = how long the button is held down
                "tl": {"r": int(self.state == "ALARM" and self.mode != "SHADOW"), "y": int(self.state == "FAULT" or self.ack == 1),
                       "g": int(self.state in ("RUN", "REST")), "b": int(self.mode == "SHADOW")},
                "rst": self.rst, "link": 100,
            }
            if self.chb:        # DF-51: v3 keys first and unchanged, then dec/fa/b are appended
                frame.update({"dec": self.dec, "fa": self.fa, "b": {
                    "env": round(env_b, 3), "base": round(self.base_b, 3), "ratio": round(ratio_b, 4),
                    "act": round(env_b * 0.6 * (1 + rng.gauss(0, 0.03)), 3), "sat": sat_b, "flat": flat_b, "flt": self.fb}})
            self.seq += 1
            if now < self.silent_until:
                return None          # link glitch: node keeps running (seq advances) but nothing arrives
            c = self.client
        c.publish("gg/%s/tele" % self.mac, json.dumps(frame, separators=(",", ":")), qos=0)
        self.published += 1
        return frame


class Fleet:
    def __init__(self, host: str = "127.0.0.1", port: int = 1883, macs: Optional[List[str]] = None,
                 user_pass: Optional[Callable[[str], tuple]] = None, **node_kw: Any):
        macs = macs or DEFAULT_MACS
        self.nodes: List[VirtualNode] = []
        for m in macs:
            u, p = user_pass(m) if user_pass else (None, None)
            self.nodes.append(VirtualNode(m, host, port, u, p, **node_kw))
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.ctl: Optional[mqtt.Client] = None
        self.host, self.port = host, port

    def start(self, stagger: float = 0.05) -> None:
        for n in self.nodes:
            n.power_on(rst=1)
            time.sleep(stagger)
        self._thread = threading.Thread(target=self._loop, daemon=True, name="sim-fleet")
        self._thread.start()

    def _loop(self) -> None:
        nxt = time.monotonic()
        while not self._stop.is_set():
            for n in self.nodes:
                try:
                    n.step()
                except Exception as e:  # pragma: no cover
                    print("sim step error", n.mac, e)
            nxt += 1.0
            self._stop.wait(max(0.0, nxt - time.monotonic()))

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        for n in self.nodes:
            n.power_off(graceful=True)
        if self.ctl:
            self.ctl.loop_stop()

    # ------------------------------------------------------- fleet actions
    def plant_off(self, mode: str = "freeze") -> None:
        """All nodes lose power at once (mill plug pulled). mode: freeze (broker times out) | cut (LWT at once)."""
        clients = [(n, n._detach()) for n in self.nodes]       # all silent at the same instant
        for n, c in clients:
            n.power_off(graceful=False, _client=c)

    def plant_on(self, stagger: float = 0.3) -> None:
        for n in self.nodes:
            n.power_on(rst=1)
            time.sleep(stagger)

    def enable_ctl(self) -> None:
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="gg-sim-ctl")

        def on_msg(cl, ud, msg):
            try:
                d = json.loads(msg.payload)
                self.apply(d)
            except Exception as e:
                print("ctl error:", e)
        c.on_message = on_msg
        c.on_connect = lambda cl, *a: cl.subscribe("gg-sim/ctl")
        c.connect_async(self.host, self.port)
        c.loop_start()
        self.ctl = c

    def apply(self, d: dict) -> None:
        do = d.pop("do")
        if do == "plant_off":
            return self.plant_off()
        if do == "plant_on":
            return self.plant_on()
        node = d.pop("node")
        if do == "power_off":
            return self.nodes[node - 1].power_off()
        if do == "power_on":
            return self.nodes[node - 1].power_on()
        self.nodes[node - 1].inject(do, **d)


DEMO = [  # (seconds from start, action)
    (5, {"do": "set_state", "node": 1, "state": "RUN"}), (5, {"do": "set_state", "node": 2, "state": "RUN"}),
    (5, {"do": "set_state", "node": 3, "state": "RUN"}), (5, {"do": "set_state", "node": 5, "state": "RUN"}),
    (40, {"do": "alarm", "node": 3, "dur": 25}),
    (90, {"do": "flatline", "node": 2, "dur": 120}),
    (120, {"do": "saturation", "node": 4, "dur": 60}),
    (200, {"do": "vin_sag", "node": 5, "dur": 90}),
    (260, {"do": "power_off", "node": 6}),
    (330, {"do": "plant_off"}),
    (420, {"do": "plant_on"}),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--nodes", type=int, default=6)
    ap.add_argument("--user", help="MQTT username (default: node id)")
    ap.add_argument("--password", help="MQTT password (single shared test password)")
    ap.add_argument("--demo", action="store_true", help="run a scripted tour of faults")
    ap.add_argument("--run", action="store_true", help="start all nodes in RUN")
    a = ap.parse_args()
    up = (lambda m: (a.user or m, a.password)) if a.password is not None else None
    fleet = Fleet(a.host, a.port, DEFAULT_MACS[: a.nodes], user_pass=up)
    fleet.start()
    fleet.enable_ctl()
    if a.run or a.demo:
        for n in fleet.nodes:
            n.inject("set_state", state="RUN")
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *x: stop.set())
    signal.signal(signal.SIGTERM, lambda *x: stop.set())
    print("sim: %d nodes publishing to %s:%d" % (len(fleet.nodes), a.host, a.port))
    t0 = time.time()
    script = list(DEMO) if a.demo else []
    while not stop.is_set():
        while script and time.time() - t0 >= script[0][0]:
            _, act = script.pop(0)
            print("demo step:", act)
            fleet.apply(dict(act))
        stop.wait(0.5)
    fleet.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
