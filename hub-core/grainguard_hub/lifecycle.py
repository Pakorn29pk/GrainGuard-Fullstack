"""Screen (ตะแกรง) lifecycle: how much of the current screen's life is used up, and when to expect the next change.

Everything is automatic and runs inside the hub (hourly update + nightly refit at 00:10).  The owner only tells the
hub *when a screen was changed* (table ``screen_changes``) and may label alarms (``alarm_labels``).

Three stages (plain-Thai explanation in docs/LIFECYCLE.md):
  1  no completed cycle with a real break : used% = days since change / 30
  2  >= 1 such cycle (own machine)        : life measured in RUN-hours, shrunk towards the pool of all machines and
                                            blended with the 30-day prior
  3  >= 3 such cycles pooled              : + wear trend (ridge regression on wear features, monotone), used only
                                            while its cross-validated error beats stage 2

Data of machine 1..6 is never mixed up; only the shrinkage prior and the trend model are fitted on the pool.
No numpy: the model is tiny (6 features) and the hub should stay light.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import math
import statistics
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from .config import Config
from .store import Store

log = logging.getLogger("gg.lifecycle")

REASONS = {"broke": "ขาดจริง", "scheduled": "เปลี่ยนตามกำหนด", "other": "อื่น ๆ"}
LABELS = {"real": "ตะแกรงขาดจริง", "false": "เตือนผิด", "unsure": "ไม่แน่ใจ"}
STAGE_TH = {1: "ตามเวลา 30 วัน", 2: "เรียนรู้จากรอบจริง", 3: "รวมแนวโน้มเสียง"}
CONF_TH = {"low": "ต่ำ", "mid": "กลาง", "high": "สูง"}
FEATURES = ("med_ratio", "p95_ratio", "burst_rate", "base_drift", "act_frac")
FEATURE_TH = {"med_ratio": "ค่ากลางของอัตราส่วนเสียง", "p95_ratio": "จุดสูงของอัตราส่วนเสียง (p95)",
              "burst_rate": "ครั้งที่เสียงพุ่ง (นาที/ชม.)", "base_drift": "ค่าฐานเปลี่ยนจากช่วงตะแกรงใหม่",
              "act_frac": "สัดส่วนเสียงเคลื่อนไหว"}
DAY = 86400.0
WINDOW_DAYS = 3.0           # features look at the last 3 days of the cycle (smoother than a single day)
MIN_RUN_MIN = 60.0          # a feature row needs at least this many RUN minutes in the window
RIDGE = 0.1                 # ridge strength relative to the number of samples
TREND_RAMP_FROM_H = 12.0    # RUN-hours into a cycle where the wear trend starts to count
TREND_RAMP_TO_H = 72.0      # ... and where it counts fully


# ---------------------------------------------------------------- tiny maths
def percentile(xs: List[float], p: float) -> float:
    s = sorted(xs)
    if not s:
        return 0.0
    k = (len(s) - 1) * p / 100.0
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def solve(A: List[List[float]], b: List[float]) -> List[float]:
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[piv][c]) < 1e-12:
            raise ValueError("singular")
        M[c], M[piv] = M[piv], M[c]
        for r in range(n):
            if r != c:
                f = M[r][c] / M[c][c]
                if f:
                    for k in range(c, n + 1):
                        M[r][k] -= f * M[c][k]
    return [M[i][n] / M[i][i] for i in range(n)]


def isotonic(ys: List[float]) -> List[float]:
    """Pool-adjacent-violators: closest non-decreasing sequence."""
    blocks: List[List[float]] = []          # [sum, count]
    for y in ys:
        blocks.append([y, 1])
        while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1]:
            s, c = blocks.pop()
            blocks[-1][0] += s
            blocks[-1][1] += c
    out: List[float] = []
    for s, c in blocks:
        out += [s / c] * int(c)
    return out


def ridge_fit(X: List[List[float]], y: List[float], lam_rel: float = RIDGE) -> Dict[str, Any]:
    n, d = len(X), len(X[0])
    mean = [sum(r[j] for r in X) / n for j in range(d)]
    std = [math.sqrt(sum((r[j] - mean[j]) ** 2 for r in X) / n) or 1.0 for j in range(d)]
    Z = [[(r[j] - mean[j]) / std[j] for j in range(d)] for r in X]
    ym = sum(y) / n
    A = [[sum(Z[i][a] * Z[i][b] for i in range(n)) + (lam_rel * n if a == b else 0.0) for b in range(d)] for a in range(d)]
    rhs = [sum(Z[i][a] * (y[i] - ym) for i in range(n)) for a in range(d)]
    beta = solve(A, rhs)
    return {"mean": mean, "std": std, "beta": beta, "intercept": ym}


def ridge_predict(m: Dict[str, Any], x: List[float]) -> float:
    return m["intercept"] + sum(m["beta"][j] * (x[j] - m["mean"][j]) / m["std"][j] for j in range(len(x)))


def stage2_life(own: List[float], pool: List[float], p_run: float, k0: float) -> Tuple[float, Dict[str, float]]:
    """Expected life in RUN-hours: shrink own mean towards the pooled mean, then blend with the time prior."""
    n = len(own)
    mu = sum(pool) / len(pool) if pool else p_run
    xbar = sum(own) / n if n else mu
    w = n / (n + k0)
    shrunk = w * xbar + (1 - w) * mu
    omega = n / (n + 1.0)
    life = omega * shrunk + (1 - omega) * p_run
    return life, {"w": w, "omega": omega, "own_mean": xbar, "pool_mean": mu, "shrunk": shrunk, "p_run": p_run}


def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# ------------------------------------------------------------------- module
class Lifecycle:
    def __init__(self, store: Store, cfg: Config, clock: Callable[[], float] = time.time,
                 emit: Optional[Callable[[float, int, str, str, dict], None]] = None):
        self.store, self.cfg, self.clock = store, cfg, clock
        self.emit = emit
        self._lock = threading.RLock()
        self._busy = False
        self._cyc_cache: Dict[Tuple, List[Dict[str, Any]]] = {}   # completed cycles per machine (immutable history)
        self._memo: Dict[Tuple, Any] = {}                          # early-cycle reference, first data, daily run rate
        self._model: Optional[Dict[str, Any]] = None
        self._model_loaded = False
        self._hour_key = self.store.meta_get("lc_hour")
        self._night_key = self.store.meta_get("lc_night")

    # ============================================================ owner input
    def entries(self, n: int) -> List[Dict[str, Any]]:
        return self.store.q("SELECT id,node,ts_change,reason,note,created_ts FROM screen_changes WHERE node=? "
                            "ORDER BY ts_change,id", (n,))

    def _check_n(self, n: int) -> None:
        if not 1 <= int(n) <= 6:
            raise ValueError("เครื่องต้องเป็นหมายเลข 1-6")

    def add_change(self, n: int, ts: float, reason: str = "other", note: str = "", now: Optional[float] = None
                   ) -> Dict[str, Any]:
        self._check_n(n)
        now = self.clock() if now is None else now
        if reason not in REASONS:
            raise ValueError("สาเหตุต้องเป็น ขาดจริง / เปลี่ยนตามกำหนด / อื่น ๆ")
        if ts > now + 300:
            raise ValueError("วันที่เปลี่ยนตะแกรงอยู่ในอนาคตไม่ได้")
        with self._lock:
            es = self.entries(n)
            if es and ts <= es[-1]["ts_change"]:
                raise ValueError("วันที่ต้องอยู่หลังการเปลี่ยนครั้งล่าสุดที่บันทึกไว้ (%s) — ถ้าบันทึกผิด ให้แก้ไขหรือยกเลิกครั้งล่าสุดก่อน"
                                 % self.fmt_date(es[-1]["ts_change"]))
            with self.store._tx() as c:
                cur = c.execute("INSERT INTO screen_changes(node,ts_change,reason,note,created_ts) VALUES(?,?,?,?,?)",
                                (n, ts, reason, (note or "").strip()[:200] or None, now))
                rid = cur.lastrowid
            self._after_change(n, now)
            return self.entries_by_id(rid)

    def entries_by_id(self, rid: int) -> Dict[str, Any]:
        return self.store.q1("SELECT id,node,ts_change,reason,note,created_ts FROM screen_changes WHERE id=?", (rid,)) or {}

    def edit_last(self, n: int, ts: Optional[float] = None, reason: Optional[str] = None, note: Optional[str] = None,
                  now: Optional[float] = None) -> Dict[str, Any]:
        self._check_n(n)
        now = self.clock() if now is None else now
        with self._lock:
            es = self.entries(n)
            if not es:
                raise LookupError("ยังไม่มีรายการให้แก้ไข")
            last = es[-1]
            new_ts = last["ts_change"] if ts is None else ts
            if new_ts > now + 300:
                raise ValueError("วันที่เปลี่ยนตะแกรงอยู่ในอนาคตไม่ได้")
            if len(es) > 1 and new_ts <= es[-2]["ts_change"]:
                raise ValueError("วันที่ต้องอยู่หลังการเปลี่ยนครั้งก่อนหน้า (%s)" % self.fmt_date(es[-2]["ts_change"]))
            if reason is not None and reason not in REASONS:
                raise ValueError("สาเหตุไม่ถูกต้อง")
            with self.store._tx() as c:
                c.execute("UPDATE screen_changes SET ts_change=?, reason=?, note=? WHERE id=?",
                          (new_ts, reason if reason is not None else last["reason"],
                           ((note or "").strip()[:200] or None) if note is not None else last["note"], last["id"]))
            self._after_change(n, now)
            return self.entries_by_id(last["id"])

    def undo_last(self, n: int, now: Optional[float] = None) -> Dict[str, Any]:
        self._check_n(n)
        now = self.clock() if now is None else now
        with self._lock:
            es = self.entries(n)
            if not es:
                raise LookupError("ยังไม่มีรายการให้ยกเลิก")
            last = es[-1]
            with self.store._tx() as c:
                c.execute("DELETE FROM screen_changes WHERE id=?", (last["id"],))
            self._after_change(n, now)
            return last

    def set_label(self, event_id: int, label: Optional[str], note: str = "", now: Optional[float] = None) -> Dict[str, Any]:
        now = self.clock() if now is None else now
        ev = self.store.get_event(event_id)
        if not ev or ev["type"] not in ("ALARM_ON", "SHADOW_ALARM"):
            raise LookupError("ติดป้ายได้เฉพาะเหตุการณ์ ALARM")
        if label is not None and label not in LABELS:
            raise ValueError("ป้ายต้องเป็น ตะแกรงขาดจริง / เตือนผิด / ไม่แน่ใจ")
        with self._lock:
            with self.store._tx() as c:
                if label is None:
                    c.execute("DELETE FROM alarm_labels WHERE event_id=?", (event_id,))
                else:
                    c.execute("INSERT OR REPLACE INTO alarm_labels(event_id,label,note,ts) VALUES(?,?,?,?)",
                              (event_id, label, (note or "").strip()[:200] or None, now))
            if ev["n"]:
                self._after_change(ev["n"], now)
        return {"event_id": event_id, "label": label}

    def _after_change(self, n: int, now: float) -> None:
        """An owner edit changes cycles: drop the clip state (the correction is deliberate), refit, recompute."""
        with self.store._tx() as c:
            c.execute("DELETE FROM screen_state WHERE node=?", (n,))
        self._cyc_cache.clear()
        self._memo.clear()
        try:
            self.ensure_all_features(now)
            self.fit_model(now)
            self.update_all(now)
        except Exception:
            log.exception("lifecycle recompute after change failed")

    # ============================================================== helpers
    def fmt_date(self, ts: float) -> str:
        d = self.store.local_dt(ts)
        return "%02d/%02d/%d" % (d.day, d.month, d.year + 543)

    def run_hours(self, n: int, t0: float, t1: float) -> float:
        if t1 <= t0:
            return 0.0
        r = self.store.q1("SELECT SUM(run_s) AS s FROM tele_1m WHERE n=? AND ts>=? AND ts<?", (n, int(t0), int(t1)))
        tot = float((r or {}).get("s") or 0.0)
        rt = self.store.rolled_to() or 0
        if t1 > rt:
            r = self.store.q1("SELECT SUM(st='RUN') AS s FROM tele_1s WHERE n=? AND ts>=? AND ts<?",
                              (n, int(max(t0, rt)), int(t1)))
            tot += float((r or {}).get("s") or 0.0)
        return tot / 3600.0

    def first_data_ts(self, n: int) -> Optional[float]:
        key = ("first", n)
        v = self._memo.get(key)
        if v is None:
            v = self._first_data_ts(n)
            if v is not None:
                self._memo[key] = v
        return v

    def _first_data_ts(self, n: int) -> Optional[float]:
        r = self.store.q1("SELECT MIN(ts) AS t FROM tele_1m WHERE n=?", (n,))
        t = (r or {}).get("t")
        r2 = self.store.q1("SELECT MIN(first_seen) AS t FROM nodes WHERE machine=?", (n,))
        t2 = (r2 or {}).get("t")
        cands = [x for x in (t, t2) if x]
        return float(min(cands)) if cands else None

    def run_rate(self, n: int, now: float) -> float:
        """Recent RUN-hours per calendar day (all days count, idle Sundays included). Re-measured once a day."""
        key = ("rate", n, int(now // DAY))
        v = self._memo.get(key)
        if v is None:
            v = self._run_rate(n, now)
            for k in [k for k in self._memo if k[0] == "rate" and k[1] == n]:
                del self._memo[k]
            self._memo[key] = v
        return v

    def _run_rate(self, n: int, now: float) -> float:
        cfg = self.cfg
        first = self.first_data_ts(n)
        if first is None:
            return cfg.screen_default_run_h_day
        t0 = max(now - cfg.screen_recent_days * DAY, first)
        days = (now - t0) / DAY
        if days < 1.0:
            return cfg.screen_default_run_h_day
        return max(0.0, self.run_hours(n, t0, now) / days)

    # =============================================================== cycles
    def cycles(self, n: int, now: float) -> List[Dict[str, Any]]:
        es = self.entries(n)
        cfg = self.cfg
        if not es:
            first = self.first_data_ts(n)
            if first is None:
                return []
            return [{"i": 0, "start": first, "end": None, "end_eff": now, "completed": False, "outcome": None,
                     "reason_end": None, "implicit": True, "run_h": self.run_hours(n, first, now),
                     "days": (now - first) / DAY, "by_alarm": False, "entry_id": None}]
        key = (n, tuple((e["id"], e["ts_change"], e["reason"]) for e in es))
        done = self._cyc_cache.get(key)
        if done is None:
            done = []
            for i in range(len(es) - 1):
                e, nxt = es[i], es[i + 1]
                start, end = e["ts_change"], nxt["ts_change"]
                c: Dict[str, Any] = {"i": i, "start": start, "end": end, "implicit": False, "entry_id": e["id"],
                                     "reason_end": nxt["reason"], "completed": True, "outcome": None, "by_alarm": False}
                real = self.store.q1(
                    "SELECT MIN(e.ts) AS t FROM events e JOIN alarm_labels l ON l.event_id=e.id "
                    "WHERE e.n=? AND l.label='real' AND e.type IN ('ALARM_ON','SHADOW_ALARM') AND e.ts>? AND e.ts>=? "
                    "AND e.ts<=?", (n, start, end - cfg.screen_alarm_window_days * DAY, end))
                rts = (real or {}).get("t")
                if nxt["reason"] == "broke" or rts:
                    c["outcome"] = "broke"
                    c["by_alarm"] = bool(rts) and nxt["reason"] != "broke"
                    c["end_eff"] = min(end, rts) if rts else end
                else:
                    c["outcome"], c["end_eff"] = nxt["reason"], end
                c["run_h"] = self.run_hours(n, start, c["end_eff"])
                c["days"] = (c["end_eff"] - start) / DAY
                done.append(c)
            for k in [k for k in self._cyc_cache if k[0] == n]:
                del self._cyc_cache[k]
            self._cyc_cache[key] = done
        last = es[-1]
        cur = {"i": len(es) - 1, "start": last["ts_change"], "end": None, "end_eff": now, "completed": False,
               "outcome": None, "reason_end": None, "implicit": False, "by_alarm": False, "entry_id": last["id"],
               "run_h": self.run_hours(n, last["ts_change"], now), "days": (now - last["ts_change"]) / DAY}
        return [dict(c) for c in done] + [cur]

    def lives(self, now: float, cyc: Optional[Dict[int, List[Dict[str, Any]]]] = None) -> Dict[int, List[float]]:
        """RUN-hour life of every completed cycle that ended with a real break, per machine."""
        out: Dict[int, List[float]] = {}
        for n in range(1, 7):
            cl = cyc[n] if cyc is not None else self.cycles(n, now)
            out[n] = [c["run_h"] for c in cl
                      if c["completed"] and c["outcome"] == "broke" and c["run_h"] >= self.cfg.screen_min_life_h]
        return out

    # ============================================================ features
    def _run_rows(self, n: int, t0: float, t1: float) -> List[Tuple]:
        rows = self.store.q("SELECT ts,cnt,run_s,ratio_avg,ratio_max,base_avg,act_avg FROM tele_1m "
                            "WHERE n=? AND ts>=? AND ts<? AND run_s>0", (n, int(t0), int(t1)))
        return [(r["ts"], r["run_s"], r["ratio_avg"], r["ratio_max"] if r["ratio_max"] is not None else r["ratio_avg"],
                 r["base_avg"], r["act_avg"]) for r in rows
                if r["cnt"] and r["run_s"] >= 0.5 * r["cnt"] and r["ratio_avg"] is not None]

    def _early_ref(self, n: int, start: float, until: float) -> Optional[Tuple[float, float]]:
        """median base and median act of the first three days of the cycle on which the machine really ran."""
        key = ("early", n, start)
        if key in self._memo:
            return self._memo[key]
        ref, stable = self._early_ref_calc(n, start, until)
        if stable:
            self._memo[key] = ref
        return ref

    def _early_ref_calc(self, n: int, start: float, until: float) -> Tuple[Optional[Tuple[float, float]], bool]:
        rows = self._run_rows(n, start, min(until, start + 20 * DAY))
        if not rows:
            return None, False
        days: Dict[int, List[Tuple]] = {}
        for r in rows:
            days.setdefault(int((r[0] - start) // DAY), []).append(r)
        good = [k for k in sorted(days) if sum(x[1] for x in days[k]) >= 3600][:3]
        if not good:
            return None, False
        sel = [x for k in good for x in days[k]]
        bases = [x[4] for x in sel if x[4]]
        acts = [x[5] for x in sel if x[5] is not None]
        if not bases:
            return None, False
        return (statistics.median(bases), (statistics.median(acts) if acts else 0.0)), len(good) == 3

    def window_features(self, n: int, start: float, t_end: float) -> Optional[Dict[str, float]]:
        t0 = max(start, t_end - WINDOW_DAYS * DAY)
        rows = self._run_rows(n, t0, t_end)
        if not rows:
            return None
        run_s = sum(r[1] for r in rows)
        if run_s / 60.0 < MIN_RUN_MIN:
            return None
        ref = self._early_ref(n, start, t_end)
        med = statistics.median(r[2] for r in rows)
        p95 = percentile([r[3] for r in rows], 95)
        burst = 60.0 * sum(r[1] for r in rows if r[3] > 1.5) / run_s
        drift = 0.0
        frac = 0.5
        if ref:
            bases = [r[4] for r in rows if r[4]]
            if bases and ref[0]:
                drift = statistics.median(bases) / ref[0] - 1.0
            acts = [(r[1], r[5]) for r in rows if r[5] is not None]
            if acts:
                frac = sum(w for w, a in acts if a > ref[1]) / sum(w for w, _ in acts)
        return {"med_ratio": med, "p95_ratio": p95, "burst_rate": burst, "base_drift": drift, "act_frac": frac,
                "run_min": run_s / 60.0}

    def ensure_features(self, n: int, now: float, cyc: Optional[List[Dict[str, Any]]] = None,
                        cleanup: bool = False) -> int:
        """Daily feature rows for every cycle of machine n (incremental; completed cycles are final)."""
        made = 0
        starts = []
        for c in (cyc if cyc is not None else self.cycles(n, now)):
            if c["implicit"]:
                continue
            starts.append(c["start"])
            start, end_eff = c["start"], c["end_eff"]
            end_key = float(round(end_eff, 1)) if c["completed"] else None
            have = self.store.q1("SELECT MAX(k) AS k, MAX(cycle_end) AS e FROM screen_features WHERE node=? AND cycle_ts=?",
                                 (n, start)) or {}
            has_rows = have.get("k") is not None
            stored_end = have.get("e")
            if has_rows:
                if c["completed"] and stored_end is not None and abs(stored_end - end_key) < 0.5:
                    continue                                           # final already
                if (stored_end is None) != (end_key is None) or c["completed"]:
                    with self.store._tx() as cx:                       # completed just now / edited / un-done: redo
                        cx.execute("DELETE FROM screen_features WHERE node=? AND cycle_ts=?", (n, start))
                    has_rows = False
            k = (have.get("k") or 0) + 1 if has_rows else 1
            marks: List[Tuple[int, float]] = []
            while start + k * DAY <= end_eff:
                marks.append((k, start + k * DAY))
                k += 1
            if c["completed"] and (end_eff - (start + (k - 1) * DAY)) > 3600:
                marks.append((k, end_eff))
            rows = []
            for k, t in marks:
                f = self.window_features(n, start, t)
                if f is None:
                    continue
                rows.append((n, start, end_key, k, t, self.run_hours(n, start, t), f["med_ratio"], f["p95_ratio"],
                             f["burst_rate"], f["base_drift"], f["act_frac"], f["run_min"]))
            if rows:
                with self.store._tx() as cx:
                    cx.executemany("INSERT OR REPLACE INTO screen_features(node,cycle_ts,cycle_end,k,ts,run_h,med_ratio,"
                                   "p95_ratio,burst_rate,base_drift,act_frac,run_min) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", rows)
                made += len(rows)
        if cleanup:                                                     # rows of cycles that no longer exist (edited start)
            with self.store._tx() as cx:
                if starts:
                    cx.execute("DELETE FROM screen_features WHERE node=? AND cycle_ts NOT IN (%s)" % ",".join("?" * len(starts)),
                               (n, *starts))
                else:
                    cx.execute("DELETE FROM screen_features WHERE node=?", (n,))
        return made

    def ensure_all_features(self, now: float) -> None:
        for n in range(1, 7):
            self.ensure_features(n, now, cleanup=True)


    def feature_rows(self, n: int, cycle_ts: float) -> List[Dict[str, Any]]:
        return self.store.q("SELECT k,ts,run_h,med_ratio,p95_ratio,burst_rate,base_drift,act_frac FROM screen_features "
                            "WHERE node=? AND cycle_ts=? ORDER BY k", (n, cycle_ts))

    @staticmethod
    def xvec(run_h: float, row: Dict[str, Any], mu: float) -> List[float]:
        return [run_h / mu if mu else 0.0, row["med_ratio"], row["p95_ratio"], row["burst_rate"], row["base_drift"],
                row["act_frac"]]

    # =============================================================== model
    def _training(self, now: float, cyc: Optional[Dict[int, List[Dict[str, Any]]]] = None) -> List[Dict[str, Any]]:
        """One record per completed real-break cycle (all machines): life + its daily feature rows."""
        recs = []
        for n in range(1, 7):
            for c in (cyc[n] if cyc is not None else self.cycles(n, now)):
                if not (c["completed"] and c["outcome"] == "broke" and c["run_h"] >= self.cfg.screen_min_life_h):
                    continue
                rows = [r for r in self.feature_rows(n, c["start"]) if r["ts"] <= c["end_eff"] + 1]
                recs.append({"n": n, "start": c["start"], "life": c["run_h"], "days": c["days"], "rows": rows})
        return recs

    def _fit_on(self, recs: List[Dict[str, Any]], mu: float) -> Optional[Dict[str, Any]]:
        X, y = [], []
        for r in recs:
            for row in r["rows"]:
                X.append(self.xvec(row["run_h"], row, mu))
                y.append(min(1.5, row["run_h"] / r["life"]))
        if len(X) < 12:
            return None
        try:
            m = ridge_fit(X, y)
        except ValueError:
            return None
        m["mu"] = mu
        return m

    def _predict_series(self, m: Dict[str, Any], rows: List[Dict[str, Any]]) -> List[float]:
        preds = [_clip(ridge_predict(m, self.xvec(r["run_h"], r, m["mu"])), 0.0, 1.5) for r in rows]
        return isotonic(preds)

    def fit_model(self, now: float, cyc: Optional[Dict[int, List[Dict[str, Any]]]] = None) -> Dict[str, Any]:
        """Nightly refit + leave-one-cycle-out cross-validation against stage 2."""
        cfg = self.cfg
        recs = self._training(now, cyc)
        info: Dict[str, Any] = {"fitted": now, "n_cycles": len(recs), "ok": False, "c3": 0.0}
        if len(recs) >= cfg.screen_stage3_min_cycles:
            lives = [r["life"] for r in recs]
            mu = sum(lives) / len(lives)
            full = self._fit_on(recs, mu)
            se_t = se_2 = 0.0
            cnt = 0
            for i, held in enumerate(recs):
                rest = [r for j, r in enumerate(recs) if j != i]
                mu_i = sum(r["life"] for r in rest) / len(rest)
                m = self._fit_on(rest, mu_i)
                if m is None or not held["rows"]:
                    continue
                pred_t = self._predict_series(m, held["rows"])
                own = [r["life"] for r in rest if r["n"] == held["n"]]
                p_run = cfg.screen_prior_days * held["life"] / max(held["days"], 1e-6)   # that cycle's own RUN-h/day
                L2, _ = stage2_life(own, [r["life"] for r in rest], p_run, cfg.screen_k0)
                for row, pt in zip(held["rows"], pred_t):
                    truth = row["run_h"] / held["life"]
                    se_t += (pt - truth) ** 2
                    se_2 += (row["run_h"] / L2 - truth) ** 2
                    cnt += 1
            if full is not None and cnt:
                rt, r2 = math.sqrt(se_t / cnt), math.sqrt(se_2 / cnt)
                info.update({"rmse_trend": rt, "rmse_stage2": r2, "rows": cnt})
                if rt < r2:
                    info["ok"] = True
                    info["c3"] = _clip(1.0 - rt / r2, 0.0, 0.8)
                info["model"] = full
        self._model, self._model_loaded = info, True
        try:
            self.store.meta_set("lc_model", json.dumps(info, separators=(",", ":")))
        except Exception:
            log.exception("could not store lifecycle model")
        return info

    def model(self, now: float) -> Dict[str, Any]:
        if not self._model_loaded:
            raw = self.store.meta_get("lc_model")
            self._model = json.loads(raw) if raw else None
            self._model_loaded = True
        if self._model is None:
            self.fit_model(now)
        return self._model or {"ok": False, "c3": 0.0, "n_cycles": 0}

    # ================================================================ state
    def update_node(self, n: int, now: float, ctx: Optional[Dict[int, List[Dict[str, Any]]]] = None
                    ) -> Optional[Dict[str, Any]]:
        cfg = self.cfg
        cyc = ctx[n] if ctx is not None else self.cycles(n, now)
        if not cyc:
            if self.store.q1("SELECT 1 AS x FROM screen_state WHERE node=?", (n,)):
                with self.store._tx() as c:
                    c.execute("DELETE FROM screen_state WHERE node=?", (n,))
            return None
        cur = cyc[-1]
        start = cur["start"]
        self.ensure_features(n, now, cyc)
        lives = self.lives(now, ctx)
        own = lives[n]
        pool = [x for v in lives.values() for x in v]
        days = max(0.0, (now - start) / DAY)
        run_h = self.run_hours(n, start, now)
        rate = self.run_rate(n, now)
        p_run = cfg.screen_prior_days * rate
        detail: Dict[str, Any] = {"rate_h_day": round(rate, 2), "p_run": round(p_run, 1), "implicit": cur["implicit"]}
        mdl = self.model(now) if len(pool) >= cfg.screen_stage3_min_cycles else {"ok": False, "c3": 0.0}
        c3 = 0.0
        if not own:
            stage = 1
            life = p_run
            sigma = cfg.screen_prior_cv * life
            used_raw = 100.0 * days / cfg.screen_prior_days
        else:
            life, parts = stage2_life(own, pool, p_run, cfg.screen_k0)
            detail.update({k: round(v, 3) for k, v in parts.items()})
            stage = 2
            if len(own) >= 3:
                sigma = statistics.stdev(own)
            elif len(pool) >= 3:
                sigma = statistics.stdev(pool)
            else:
                sigma = cfg.screen_prior_cv * life
            sigma = max(sigma, 0.1 * life)
            used_raw = 100.0 * run_h / life if life else 0.0
            if len(pool) >= cfg.screen_stage3_min_cycles and mdl.get("ok") and mdl.get("model"):
                rows = self.feature_rows(n, start)
                live = self.window_features(n, start, now)
                if live is not None:
                    rows = rows + [dict(live, run_h=run_h, k=10 ** 6)]
                if rows:
                    m = mdl["model"]
                    u_t = self._predict_series(m, rows)[-1] * 100.0
                    # the first days of a new screen carry too little wear information: ramp the trend in (0 at 12 h, full at 72 h)
                    c3 = float(mdl.get("c3", 0.0)) * _clip((run_h - TREND_RAMP_FROM_H) / (TREND_RAMP_TO_H - TREND_RAMP_FROM_H),
                                                           0.0, 1.0)
                    if c3 > 0:
                        stage = 3
                        used_raw = c3 * u_t + (1 - c3) * used_raw
                        sigma = (1 - c3) * sigma + c3 * mdl.get("rmse_trend", 0.1) * life
                        detail.update({"trend_used_pct": round(u_t, 1), "c3": round(c3, 3)})
        used_raw = _clip(used_raw, 0.0, 300.0)
        prev = self.store.q1("SELECT cycle_ts,ts,used_pct FROM screen_state WHERE node=?", (n,))
        used = used_raw
        if prev and abs(prev["cycle_ts"] - start) < 1e-6:
            lim = cfg.screen_clip_pts_day * max(0.0, now - prev["ts"]) / DAY     # same instant => no movement at all
            used = _clip(used_raw, prev["used_pct"] - lim, prev["used_pct"] + lim)
            if abs(used - used_raw) > 1e-9:
                detail["clipped"] = True
        used = _clip(used, 0.0, 300.0)
        if stage == 1:
            remain_days = max(0.0, (1 - used / 100.0) * cfg.screen_prior_days)
            remain_h = remain_days * rate
            lo_d = max(0.0, remain_days - sigma / max(rate, 1e-6)) if rate > 0.1 else None
            hi_d = remain_days + sigma / max(rate, 1e-6) if rate > 0.1 else None
        else:
            remain_h = max(0.0, (1 - used / 100.0) * life)
            if rate > 0.1:
                remain_days = remain_h / rate
                lo_d = max(0.0, (remain_h - sigma) / rate)
                hi_d = (remain_h + sigma) / rate
            else:
                remain_days = lo_d = hi_d = None
        band = sigma / life if life else 1.0
        if stage == 1:
            conf = "low"
        else:
            conf = "low" if len(own) < 2 or band > 0.25 else ("high" if len(own) >= 3 and band <= 0.15 else "mid")
            if stage == 3 and c3 >= 0.3:
                conf = {"low": "mid", "mid": "high", "high": "high"}[conf]
        st = {"node": n, "cycle_ts": start, "ts": now, "stage": stage, "used_pct": used, "used_raw": used_raw,
              "run_h": run_h, "days": days, "life_h": life, "sigma_h": sigma, "remain_h": remain_h,
              "remain_days": remain_days, "remain_lo": lo_d, "remain_hi": hi_d, "conf": conf, "n_own": len(own),
              "n_pool": len(pool), "detail": json.dumps(detail, separators=(",", ":"))}
        with self.store._tx() as c:
            c.execute("INSERT OR REPLACE INTO screen_state(node,cycle_ts,ts,stage,used_pct,used_raw,run_h,days,life_h,sigma_h,"
                      "remain_h,remain_days,remain_lo,remain_hi,conf,n_own,n_pool,detail) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      tuple(st[k] for k in ("node", "cycle_ts", "ts", "stage", "used_pct", "used_raw", "run_h", "days",
                                            "life_h", "sigma_h", "remain_h", "remain_days", "remain_lo", "remain_hi", "conf",
                                            "n_own", "n_pool", "detail")))
            c.execute("INSERT OR REPLACE INTO screen_state_log(node,ts,cycle_ts,stage,used_pct,used_raw,run_h,remain_h) "
                      "VALUES(?,?,?,?,?,?,?,?)", (n, int(now), start, stage, used, used_raw, run_h, remain_h))
        if not cur["implicit"] and used >= cfg.screen_advisory_pct:
            self._advisory(n, start, used, remain_days, now)
        return st

    def _advisory(self, n: int, cycle_ts: float, used: float, remain_days: Optional[float], now: float) -> None:
        key = "lc_adv:%d:%d" % (n, int(cycle_ts))
        if self.store.meta_get(key) is not None or self.emit is None:
            return
        self.store.meta_set(key, str(int(now)))
        rem = ("คาดว่าเหลือราว %d วัน" % round(remain_days)) if remain_days is not None and remain_days >= 0.5 else "ใกล้ถึงเวลาเปลี่ยนแล้ว"
        text = "ใกล้ถึงอายุตะแกรง: ใช้ไปแล้ว %d%% (%s) — แจ้งเพื่อทราบ ไม่แทนเสียงเตือนของเครื่อง" % (round(used), rem)
        data = {"flag": "screen_life_90", "state": "set", "advisory": True, "sev": "info", "used_pct": round(used, 1),
                "remain_days": None if remain_days is None else round(remain_days, 1), "cycle_start": int(cycle_ts)}
        try:
            self.emit(now, n, "HEALTH", text, data)
        except Exception:
            log.exception("advisory event failed")

    def update_all(self, now: float) -> None:
        ctx = {n: self.cycles(n, now) for n in range(1, 7)}
        for n in range(1, 7):
            try:
                self.update_node(n, now, ctx)
            except Exception:
                log.exception("lifecycle update of machine %d failed", n)

    # ================================================================= jobs
    def tick(self, now: Optional[float] = None, sync: bool = False) -> bool:
        """Cheap to call every second. Starts the hourly update / nightly refit when due. True when a job ran."""
        if not self.cfg.screen_jobs:
            return False
        now = self.clock() if now is None else now
        hour_key = str(int(now // 3600))
        ld = self.store.local_dt(now)
        try:
            hh, mm = (int(x) for x in self.cfg.screen_refit_time.split(":"))
        except ValueError:
            hh, mm = 0, 10
        slot = ld.replace(hour=hh, minute=mm, second=0, microsecond=0).timestamp()
        day = ld.date().isoformat()
        night = now >= slot and self._night_key != day
        hourly = self._hour_key != hour_key
        if not (night or hourly) or self._busy:
            return False
        self._busy = True
        self._hour_key = hour_key
        if night:
            self._night_key = day
        if sync:
            self._run(now, night, hour_key, day)
        else:
            threading.Thread(target=self._run, args=(now, night, hour_key, day), name="gg-lifecycle", daemon=True).start()
        return True

    def _run(self, now: float, night: bool, hour_key: str, day: str) -> None:
        t0 = time.monotonic()
        try:
            with self._lock:
                if night:
                    self._cyc_cache.clear()
                    self._memo.clear()
                    self.ensure_all_features(now)
                    self.fit_model(now)
                self.update_all(now)
            self.store.meta_set("lc_hour", hour_key)
            if night:
                self.store.meta_set("lc_night", day)
            log.info("lifecycle %s job done in %.1fs", "nightly" if night else "hourly", time.monotonic() - t0)
        except Exception:
            log.exception("lifecycle job failed")
        finally:
            self._busy = False

    # ============================================================== views
    def _state_row(self, n: int, now: float) -> Optional[Dict[str, Any]]:
        r = self.store.q1("SELECT * FROM screen_state WHERE node=?", (n,))
        if r is None:
            try:
                self.update_node(n, now)
            except Exception:
                log.exception("lifecycle on-demand update failed")
            r = self.store.q1("SELECT * FROM screen_state WHERE node=?", (n,))
        return r

    def overview(self, now: Optional[float] = None) -> Dict[str, Any]:
        now = self.clock() if now is None else now
        machines = []
        mdl = self.model(now) if self.store.meta_get("lc_model") else {"ok": False, "c3": 0.0, "n_cycles": 0}
        for n in range(1, 7):
            es = self.entries(n)
            cyc = self.cycles(n, now)
            st = self._state_row(n, now)
            m: Dict[str, Any] = {"n": n, "entries": [], "cycles": [], "state": None, "has_start": bool(cyc)}
            for e in es:
                m["entries"].append({"id": e["id"], "ts": e["ts_change"], "date": self.fmt_date(e["ts_change"]),
                                     "reason": e["reason"], "reason_th": REASONS.get(e["reason"], e["reason"]),
                                     "note": e["note"] or ""})
            for c in cyc:
                if c["completed"]:
                    m["cycles"].append({
                        "start": c["start"], "end": c["end_eff"], "start_date": self.fmt_date(c["start"]),
                        "end_date": self.fmt_date(c["end"]), "days": round(c["days"], 1), "run_h": round(c["run_h"], 1),
                        "outcome": c["outcome"], "outcome_th": REASONS.get(c["outcome"], c["outcome"]),
                        "by_alarm": c["by_alarm"]})
            if cyc:
                cur = cyc[-1]
                m["implicit_start"] = cur["implicit"]
                m["start_ts"] = cur["start"]
                m["start_date"] = self.fmt_date(cur["start"])
            if st:
                d = json.loads(st.pop("detail") or "{}")
                st["detail"] = d
                st["stage_th"] = STAGE_TH.get(st["stage"], "")
                if st["stage"] == 2:
                    st["stage_th"] = "เรียนรู้จากรอบจริง %d รอบ" % st["n_own"]
                st["conf_th"] = CONF_TH.get(st["conf"], "")
                st["over"] = st["used_pct"] >= 100.0
                st["advisory"] = st["used_pct"] >= self.cfg.screen_advisory_pct
                m["state"] = st
            machines.append(m)
        return {"now": now, "machines": machines, "prior_days": self.cfg.screen_prior_days,
                "model": {"cycles": mdl.get("n_cycles", 0), "ok": bool(mdl.get("ok")), "c3": mdl.get("c3", 0.0),
                          "rmse_trend": mdl.get("rmse_trend"), "rmse_stage2": mdl.get("rmse_stage2"),
                          "fitted": mdl.get("fitted")},
                "reasons": REASONS, "labels": LABELS}

    def trend(self, n: int, now: Optional[float] = None) -> Dict[str, Any]:
        now = self.clock() if now is None else now
        cyc = self.cycles(n, now)
        out: Dict[str, Any] = {"n": n, "features": [{"key": k, "th": FEATURE_TH[k]} for k in FEATURES], "current": None,
                               "previous": []}
        for c in cyc:
            if c["implicit"]:
                continue
            pts = [{"run_h": r["run_h"], **{k: r[k] for k in FEATURES}} for r in self.feature_rows(n, c["start"])]
            item = {"start": c["start"], "start_date": self.fmt_date(c["start"]), "points": pts}
            if c["completed"]:
                item.update({"end": c["end_eff"], "life_h": round(c["run_h"], 1), "outcome": c["outcome"],
                             "outcome_th": REASONS.get(c["outcome"], c["outcome"])})
                out["previous"].append(item)
            else:
                live = self.window_features(n, c["start"], now)
                if live:
                    pts.append({"run_h": c["run_h"], **{k: live[k] for k in FEATURES}})
                item["run_h"] = round(c["run_h"], 1)
                out["current"] = item
        return out
