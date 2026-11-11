"""Fill a hub Store with realistic history (14 days of minute aggregates + 2 h of per-second telemetry
+ events), so history charts / daily table / 7-day drift reference have something to show.
Used by the tests and by screens.py; not part of the production hub."""
from __future__ import annotations

import datetime as dt
import json
import random
from typing import List, Optional

from node_sim import DEFAULT_MACS
from wear_model import wear_values

LEVELS = [150.0, 180.0, 120.0, 200.0, 165.0, 140.0]

# Demo screen-change history (days before "now", reason of replacing the OLD screen, note). Compressed on purpose: the real
# life is ~30 days, but the demo database only holds 14 days, so machine 3 shows two completed (~5-day) cycles.
DEMO_CHANGES = {
    3: [(13.2, "other", "เริ่มบันทึกในระบบ"), (8.1, "broke", "ขาดตรงขอบ"), (3.2, "broke", "")],
    1: [(10.6, "scheduled", "")],
    5: [(9.4, "other", "")],
    4: [(5.3, "scheduled", "")],
}
DEMO_NOMINAL_DAYS = {3: 5.2}      # how long the demo's current cycle is assumed to run for the wear curve


def _blocks(rng: random.Random, start: int, end: int, working: bool):
    """list of (t0, t1, 'RUN'|'REST') covering [start, end)"""
    out, t = [], start
    state = "REST"
    while t < end:
        if not working:
            out.append((t, end, "REST"))
            break
        d = rng.randint(15, 60) * 60 if state == "RUN" else rng.randint(3, 15) * 60
        out.append((t, min(end, t + d), state))
        t += d
        state = "RUN" if state == "REST" else "REST"
    return out


def _wear_u(plan: dict, n: int, t: float, t_first: float, now: float) -> float:
    """Wear 0..1 of machine n's screen at time t, from the demo change plan (calendar-time fraction of its cycle)."""
    pts = [now - d * 86400 for d, _, _ in plan.get(n, [])]
    start, end = t_first, None
    for i, p in enumerate(pts):
        if p <= t:
            start = p
            end = pts[i + 1] if i + 1 < len(pts) else None
    if end is None:
        span = DEMO_NOMINAL_DAYS.get(n, 30.0) * 86400
    else:
        span = end - start
    return max(0.0, (t - start) / span)


def seed(store, now: float, days: int = 14, macs: Optional[List[str]] = None, rng_seed: int = 7,
         fine_hours: float = 2.0, assign: bool = True, outages: bool = True,
         running_tail: tuple = (), lifecycle: bool = True) -> None:
    macs = macs or DEFAULT_MACS
    rng = random.Random(rng_seed)
    plan = DEMO_CHANGES if lifecycle else {}
    fine_start = int(now - fine_hours * 3600) // 60 * 60
    t_first = int(now - days * 86400) // 60 * 60
    for i, mac in enumerate(macs):
        store.ensure_node(mac, t_first)
        if assign:
            store.assign(i + 1, mac, None, t_first)
    # state timeline per node
    tl = {}
    for i, mac in enumerate(macs):
        blocks = []
        d0 = store.local_dt(t_first).date()
        for k in range(days + 1):
            d = d0 + dt.timedelta(days=k)
            s, e = store.day_bounds(d.isoformat())
            work_s = s + int((5.5 + rng.random()) * 3600)
            work_e = s + int((17.5 + rng.random()) * 3600)
            sunday = d.weekday() == 6
            blocks += _blocks(rng, s, work_s, False)
            blocks += _blocks(rng, work_s, work_e, not sunday)
            blocks += _blocks(rng, work_e, e, False)
        tl[mac] = blocks
    rows_1m, rows_1s, events = [], [], []
    for i, mac in enumerate(macs):
        n = i + 1
        level = LEVELS[i % len(LEVELS)]
        off = set()
        if outages:
            for k in range(days):
                if rng.random() < 0.12:
                    s0 = t_first + k * 86400 + rng.randint(6, 17) * 3600
                    for m in range(rng.randint(5, 40)):
                        off.add(s0 + m * 60)
        alarm_min = {}
        for ts_blk0, ts_blk1, stt in tl[mac]:
            if stt != "RUN":
                continue
            if rng.random() < 0.05:
                am = rng.randrange(ts_blk0, ts_blk1) // 60 * 60
                alarm_min[am] = rng.randint(20, 90)
        for ts_blk0, ts_blk1, stt in tl[mac]:
            t = ts_blk0 // 60 * 60
            while t < min(ts_blk1, int(now) // 60 * 60):
                if t < t_first or t in off:
                    t += 60
                    continue
                run = 60 if stt == "RUN" else 0
                alarm = alarm_min.get(t, 0)
                if alarm:
                    run = 60 - alarm
                    events.append((t + 5, n, mac, "ALARM_ON", "ขัด %d: ALARM ตะแกรงมีปัญหา!" % n, {"ratio": 3.4, "via": "node"}))
                    events.append((t + 5 + alarm, n, mac, "ALARM_OFF", "ขัด %d: ALARM หยุดแล้ว" % n, {"duration_s": alarm}))
                rest = 60 - run - alarm
                if stt == "RUN":
                    ratio, rmax, base_v, act_v = wear_values(_wear_u(plan, n, t, t_first, now), level, rng)
                    env = level * ratio
                else:
                    ratio, rmax, base_v, act_v = 0.15 + rng.gauss(0, 0.01), 0.17, level + rng.gauss(0, 0.5), level * 0.09
                    env = level * 0.15
                if t < fine_start:
                    rows_1m.append((t, mac, n, 60, env, env * 1.08, ratio, rmax + (2.8 if alarm else 0), act_v,
                                    base_v, 24.1 + rng.gauss(0, 0.03), 41.0, 42.5, 0, 0,
                                    run, rest, alarm, 0))
                t += 60
    for n, items in plan.items():            # the alarm that preceded each real break (labelled below)
        for d, reason, _ in items[1:]:
            if reason == "broke":
                t = int(now - d * 86400 - 0.25 * 86400)
                events.append((t, n, macs[n - 1], "ALARM_ON", "ขัด %d: ALARM ตะแกรงมีปัญหา!" % n, {"ratio": 3.9, "via": "node"}))
                events.append((t + 600, n, macs[n - 1], "ALARM_OFF", "ขัด %d: ALARM หยุดแล้ว" % n, {"duration_s": 600}))
    with store._tx() as c:
        c.executemany("INSERT OR REPLACE INTO tele_1m(ts,mac,n,cnt,env_avg,env_max,ratio_avg,ratio_max,act_avg,base_avg,"
                      "vin_avg,tc_avg,tc_max,sat_sum,flat_sum,run_s,rest_s,alarm_s,other_s) "
                      "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows_1m)
        c.executemany("INSERT INTO events(ts,n,mac,type,text,data,src) VALUES(?,?,?,?,?,?,?)",
                      [(e[0], e[1], e[2], e[3], e[4], json.dumps(e[5]), "node") for e in sorted(events)
                       if e[0] < now])
    if lifecycle:
        _seed_lifecycle(store, now, macs, plan, rng)
    # fine-grained last hours (per second) from the same timeline
    for i, mac in enumerate(macs):
        n = i + 1
        level = LEVELS[i % len(LEVELS)]
        for ts_blk0, ts_blk1, stt in tl[mac]:
            a, b = max(ts_blk0, fine_start), min(ts_blk1, int(now))
            for t in range(a, b):
                if i in running_tail and t > now - 2700:
                    stt = "RUN"
                ratio = (1.0 + rng.gauss(0, 0.05)) if stt == "RUN" else (0.15 + rng.gauss(0, 0.015))
                env = level * ratio if stt == "RUN" else level * ratio
                rows_1s.append((t, mac, n, stt, env, level, ratio, env * 0.6, 0, 0, 24.1 + rng.gauss(0, 0.05),
                                41 + rng.gauss(0, 0.1)))
    with store._tx() as c:
        c.executemany("INSERT OR REPLACE INTO tele_1s(ts,mac,n,st,env,base,ratio,act,sat,flat,vin,tc) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                      rows_1s)
    store.meta_set("rolled_to", str(fine_start))
    store.rollup(now)
    # daily summaries for the past days
    today = store.date_of(now)
    d = dt.date.fromisoformat(today)
    for k in range(1, days):
        store.compute_daily((d - dt.timedelta(days=k)).isoformat(), now, final=True, save=True)


def _seed_lifecycle(store, now: float, macs: List[str], plan: dict, rng: random.Random) -> None:
    """screen_changes for the demo plan, a 'real' alarm just before each break, and labels on some other alarms."""
    ts = int(now)
    with store._tx() as c:
        for n, items in plan.items():
            for d, reason, note in items:
                c.execute("INSERT INTO screen_changes(node,ts_change,reason,note,created_ts) VALUES(?,?,?,?,?)",
                          (n, now - d * 86400, reason, note or None, now - d * 86400 + 600))
        # the alarm just before each break is a confirmed real one
        for n, items in plan.items():
            for d, reason, _ in items[1:]:
                if reason != "broke":
                    continue
                t = int(now - d * 86400 - 0.25 * 86400)
                r = c.execute("SELECT id FROM events WHERE n=? AND type='ALARM_ON' AND ts=?", (n, t)).fetchone()
                if r:
                    c.execute("INSERT OR REPLACE INTO alarm_labels(event_id,label,note,ts) VALUES(?,?,?,?)",
                              (r[0], "real", "เจอรอยขาดจริง", t + 3600))
        # label about half of the random alarms: mostly false alarms, a few unsure
        rows = c.execute("SELECT e.id FROM events e LEFT JOIN alarm_labels l ON l.event_id=e.id "
                         "WHERE e.type='ALARM_ON' AND l.event_id IS NULL ORDER BY e.id").fetchall()
        for k, (eid,) in enumerate(rows):
            if k % 2 == 0:
                c.execute("INSERT INTO alarm_labels(event_id,label,note,ts) VALUES(?,?,?,?)",
                          (eid, "false" if k % 4 == 0 else "unsure", None, now))
