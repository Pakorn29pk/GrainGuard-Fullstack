"""SQLite storage (WAL, synchronous=FULL).

* ``tele_1s``  one row per node per second, kept ``tele_retention_days`` (7)
* ``tele_1m``  one-minute aggregates, kept forever (rolled up every minute)
* ``events``   everything noteworthy (node events + hub-derived events)
* ``cloud_queue``  store-and-forward queue for /api/event (ordered by seq)
* ``daily_summary``  per day / per machine
* ``nodes``    registry: mac -> machine 1..6 + label

Writes go through one connection guarded by a lock.  Per-second telemetry is
buffered in memory and committed once per second (one fsync per second instead
of six).  Events and the cloud queue are committed immediately and atomically
(event row + queue row in one transaction) so nothing is lost on power cut.
Readers (REST API) use their own per-thread read connections (WAL).
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import sqlite3
import statistics
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

log = logging.getLogger("gg.store")

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS nodes(
  mac TEXT PRIMARY KEY, machine INTEGER UNIQUE, label TEXT,
  first_seen REAL, last_seen REAL, fw TEXT);
CREATE TABLE IF NOT EXISTS tele_1s(
  ts INTEGER NOT NULL, mac TEXT NOT NULL, n INTEGER NOT NULL DEFAULT 0, st TEXT,
  env REAL, base REAL, ratio REAL, act REAL, sat INTEGER, flat INTEGER, vin REAL, tc REAL,
  env_b REAL, base_b REAL, ratio_b REAL, act_b REAL, sat_b INTEGER, flat_b INTEGER,
  PRIMARY KEY(ts, mac)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS tele_1m(
  ts INTEGER NOT NULL, mac TEXT NOT NULL, n INTEGER NOT NULL DEFAULT 0, cnt INTEGER,
  env_avg REAL, env_max REAL, ratio_avg REAL, ratio_max REAL, act_avg REAL, base_avg REAL,
  vin_avg REAL, tc_avg REAL, tc_max REAL, sat_sum INTEGER, flat_sum INTEGER,
  run_s INTEGER, rest_s INTEGER, alarm_s INTEGER, other_s INTEGER,
  env_b_avg REAL, env_b_max REAL, ratio_b_avg REAL, ratio_b_max REAL, act_b_avg REAL, base_b_avg REAL,
  sat_b_sum INTEGER, flat_b_sum INTEGER,
  PRIMARY KEY(ts, mac)) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS tele_1m_n ON tele_1m(n, ts);
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, n INTEGER NOT NULL DEFAULT 0,
  mac TEXT, type TEXT NOT NULL, text TEXT, data TEXT, src TEXT, code TEXT);
CREATE INDEX IF NOT EXISTS events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS events_type ON events(type, ts);
CREATE TABLE IF NOT EXISTS cloud_queue(
  seq INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, n INTEGER NOT NULL DEFAULT 0,
  type TEXT NOT NULL, text TEXT, data TEXT,
  attempts INTEGER NOT NULL DEFAULT 0, next_try REAL NOT NULL DEFAULT 0,
  dead INTEGER NOT NULL DEFAULT 0, last_err TEXT, code TEXT);
CREATE TABLE IF NOT EXISTS daily_summary(
  date TEXT NOT NULL, node INTEGER NOT NULL, run_min REAL, rest_min REAL,
  alarm_count INTEGER, alarm_min REAL, max_ratio REAL, offline_min REAL, uptime_pct REAL,
  health_incidents INTEGER, notes TEXT, final INTEGER DEFAULT 0, computed_at REAL,
  PRIMARY KEY(date, node));
CREATE TABLE IF NOT EXISTS error_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL, key TEXT NOT NULL, n INTEGER NOT NULL DEFAULT 0,
  ts_set REAL NOT NULL, ts_clear REAL, detail TEXT);
CREATE INDEX IF NOT EXISTS error_log_ts ON error_log(ts_set);
CREATE INDEX IF NOT EXISTS error_log_open ON error_log(ts_clear);
CREATE TABLE IF NOT EXISTS screen_changes(
  id INTEGER PRIMARY KEY AUTOINCREMENT, node INTEGER NOT NULL, ts_change REAL NOT NULL,
  reason TEXT NOT NULL DEFAULT 'other', note TEXT, created_ts REAL NOT NULL);
CREATE INDEX IF NOT EXISTS screen_changes_node ON screen_changes(node, ts_change);
CREATE TABLE IF NOT EXISTS alarm_labels(
  event_id INTEGER PRIMARY KEY, label TEXT NOT NULL, note TEXT, ts REAL NOT NULL);
CREATE TABLE IF NOT EXISTS screen_features(
  node INTEGER NOT NULL, cycle_ts REAL NOT NULL, cycle_end REAL, k INTEGER NOT NULL, ts REAL NOT NULL, run_h REAL,
  med_ratio REAL, p95_ratio REAL, burst_rate REAL, base_drift REAL, act_frac REAL, run_min REAL,
  PRIMARY KEY(node, cycle_ts, k)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS screen_state(
  node INTEGER PRIMARY KEY, cycle_ts REAL, ts REAL, stage INTEGER, used_pct REAL, used_raw REAL, run_h REAL, days REAL,
  life_h REAL, sigma_h REAL, remain_h REAL, remain_days REAL, remain_lo REAL, remain_hi REAL, conf TEXT,
  n_own INTEGER, n_pool INTEGER, detail TEXT);
CREATE TABLE IF NOT EXISTS screen_state_log(
  node INTEGER NOT NULL, ts REAL NOT NULL, cycle_ts REAL, stage INTEGER, used_pct REAL, used_raw REAL, run_h REAL,
  remain_h REAL, PRIMARY KEY(node, ts)) WITHOUT ROWID;
"""

CLOUD_TYPES = {"ALARM_ON", "ALARM_OFF", "NODE_OFFLINE", "NODE_ONLINE", "HEALTH",
               "HUB_BOOT", "PLANT_POWER_OFF", "DAILY"}


def _row(cur: sqlite3.Cursor) -> List[Dict[str, Any]]:
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


class Store:
    def __init__(self, path: str, tz: str = "Asia/Bangkok", retention_days: int = 7):
        self.path = path
        self.db_errors = 0                # sqlite errors seen on the write path (hub self-check E502 watches this)
        self.last_db_error = ""
        self.retention_days = retention_days
        d = os.path.dirname(os.path.abspath(path))
        os.makedirs(d, exist_ok=True)
        self._tz = self._load_tz(tz)
        self._wl = threading.RLock()
        self._local = threading.local()
        self._buf: List[tuple] = []
        self._bl = threading.Lock()
        self._w = sqlite3.connect(path, check_same_thread=False, isolation_level=None, timeout=30)
        self._w.execute("PRAGMA journal_mode=WAL")
        self._w.execute("PRAGMA synchronous=FULL")
        self._w.execute("PRAGMA foreign_keys=ON")
        self._w.executescript(SCHEMA)
        self._migrate()
        self._closed = False

    def _migrate(self) -> None:
        """Add columns introduced after v1 to databases created by an older hub (CREATE IF NOT EXISTS keeps the old shape)."""
        # channel B (piezo) columns, DF-54: nullable, NULL = the node had no channel B at that time
        b1s = [("env_b", "REAL"), ("base_b", "REAL"), ("ratio_b", "REAL"), ("act_b", "REAL"), ("sat_b", "INTEGER"), ("flat_b", "INTEGER")]
        b1m = [("env_b_avg", "REAL"), ("env_b_max", "REAL"), ("ratio_b_avg", "REAL"), ("ratio_b_max", "REAL"),
               ("act_b_avg", "REAL"), ("base_b_avg", "REAL"), ("sat_b_sum", "INTEGER"), ("flat_b_sum", "INTEGER")]
        cols_to_add = [("events", "code", "TEXT"), ("cloud_queue", "code", "TEXT")]
        cols_to_add += [("tele_1s", c, d) for c, d in b1s] + [("tele_1m", c, d) for c, d in b1m]
        for table, col, decl in cols_to_add:
            cols = [r[1] for r in self._w.execute("PRAGMA table_info(%s)" % table).fetchall()]
            if col not in cols:
                self._w.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, col, decl))

    # ------------------------------------------------------------- helpers
    @staticmethod
    def _load_tz(name: str):
        if ZoneInfo is not None:
            try:
                return ZoneInfo(name)
            except Exception:
                log.warning("timezone %s not found, falling back to UTC+7", name)
        return dt.timezone(dt.timedelta(hours=7))

    @property
    def tz(self):
        return self._tz

    def local_dt(self, ts: float) -> dt.datetime:
        return dt.datetime.fromtimestamp(ts, self._tz)

    def day_bounds(self, date: str) -> Tuple[int, int]:
        d = dt.date.fromisoformat(date)
        s = dt.datetime(d.year, d.month, d.day, tzinfo=self._tz)
        e = dt.datetime.combine(d + dt.timedelta(days=1), dt.time(0), tzinfo=self._tz)
        return int(s.timestamp()), int(e.timestamp())

    def date_of(self, ts: float) -> str:
        return self.local_dt(ts).date().isoformat()

    def _rconn(self) -> sqlite3.Connection:
        c = getattr(self._local, "c", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=30)
            c.execute("PRAGMA query_only=ON")
            self._local.c = c
        return c

    @contextmanager
    def _tx(self):
        with self._wl:
            self._w.execute("BEGIN IMMEDIATE")
            try:
                yield self._w
            except BaseException as e:
                try:
                    self._w.execute("ROLLBACK")
                except Exception:
                    pass
                if isinstance(e, sqlite3.DatabaseError) and not isinstance(e, sqlite3.IntegrityError):
                    self.db_errors += 1
                    self.last_db_error = "%s: %s" % (type(e).__name__, e)
                raise
            else:
                self._w.execute("COMMIT")

    def q(self, sql: str, args: Iterable = ()) -> List[Dict[str, Any]]:
        cur = self._rconn().execute(sql, tuple(args))
        return _row(cur)

    def q1(self, sql: str, args: Iterable = ()) -> Optional[Dict[str, Any]]:
        r = self.q(sql, args)
        return r[0] if r else None

    # ---------------------------------------------------------------- meta
    def meta_get(self, k: str, default: Optional[str] = None) -> Optional[str]:
        r = self._rconn().execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
        return r[0] if r else default

    def meta_set(self, k: str, v: str) -> None:
        with self._tx() as c:
            c.execute("INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, str(v)))

    # --------------------------------------------------------------- nodes
    def list_nodes(self) -> List[Dict[str, Any]]:
        return self.q("SELECT * FROM nodes ORDER BY COALESCE(machine, 99), mac")

    def ensure_node(self, mac: str, now: float, fw: Optional[str] = None) -> None:
        with self._tx() as c:
            c.execute("INSERT OR IGNORE INTO nodes(mac, machine, label, first_seen, last_seen, fw) VALUES(?,?,?,?,?,?)",
                      (mac, None, None, now, now, fw))

    def touch_nodes(self, rows: List[Tuple[float, Optional[str], str]]) -> None:
        if not rows:
            return
        with self._tx() as c:
            c.executemany("UPDATE nodes SET last_seen=?, fw=COALESCE(?, fw) WHERE mac=?", rows)

    def assign(self, machine: Optional[int], mac: str, label: Optional[str], now: float) -> Dict[str, Any]:
        """Assign `mac` to slot `machine` (1..6). The previous occupant becomes unassigned.
        machine=None un-assigns the mac."""
        # Buffered rows already carry the machine identity at receipt time.
        # Commit those rows before considering first-assignment backfill.
        self.flush_tele()
        with self._tx() as c:
            previous = c.execute("SELECT machine, label FROM nodes WHERE mac=?", (mac,)).fetchone()
            previous_machine = previous[0] if previous else None
            previously_assigned = (previous_machine is not None or
                                   c.execute("SELECT 1 FROM meta WHERE k=?", ("assigned_once:" + mac,)).fetchone() is not None or
                                   c.execute("SELECT 1 FROM events WHERE mac=? AND type='ASSIGN' AND n>0 LIMIT 1", (mac,)).fetchone() is not None)
            replaced = c.execute("SELECT mac FROM nodes WHERE machine=? AND mac<>?", (machine, mac)).fetchone() if machine is not None else None
            if machine is not None:
                c.execute("UPDATE nodes SET machine=NULL, label=NULL WHERE machine=? AND mac<>?", (machine, mac))
            c.execute("INSERT OR IGNORE INTO nodes(mac, machine, label, first_seen, last_seen) VALUES(?,?,?,?,?)",
                      (mac, None, None, now, now))
            c.execute("UPDATE nodes SET machine=?, label=? WHERE mac=?", (machine, label, mac))
            if machine is not None and not previously_assigned:
                first = c.execute("SELECT first_seen FROM nodes WHERE mac=?", (mac,)).fetchone()[0] or 0
                lo = int(first) - 60
                c.execute("UPDATE tele_1s SET n=? WHERE mac=? AND n=0 AND ts>=?", (machine, mac, lo))
                c.execute("UPDATE tele_1m SET n=? WHERE mac=? AND n=0 AND ts>=?", (machine, mac, lo))
            if machine is not None:
                c.execute("INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                          ("assigned_once:" + mac, "1"))
            if previous_machine != machine and previously_assigned:
                for key in ("drift_ref_from:" + mac, "assignment_context_from:" + mac):
                    c.execute("INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (key, str(now)))
            if replaced:
                for key in ("assigned_once:" + replaced[0], "assignment_context_from:" + replaced[0]):
                    c.execute("INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                              (key, "1" if key.startswith("assigned_once:") else str(now)))
            return {"previous_machine": previous_machine, "replaced_mac": replaced[0] if replaced else None,
                    "previously_assigned": previously_assigned, "first_assignment": machine is not None and not previously_assigned}

    def set_label(self, mac: str, label: str) -> None:
        with self._tx() as c:
            c.execute("UPDATE nodes SET label=? WHERE mac=?", (label, mac))

    # ----------------------------------------------------------- telemetry
    def buffer_tele(self, ts: int, mac: str, n: int, st: str, env: float, base: float, ratio: float,
                    act: float, sat: int, flat: int, vin: float, tc: float, b: Optional[Dict[str, Any]] = None) -> None:
        """b = channel B numbers {env, base, ratio, act, sat, flat} or None when the node has no channel B."""
        bt = (None,) * 6 if not b else (b.get("env"), b.get("base"), b.get("ratio"), b.get("act"), b.get("sat"), b.get("flat"))
        with self._bl:
            self._buf.append((ts, mac, n, st, env, base, ratio, act, sat, flat, vin, tc) + bt)

    def flush_tele(self) -> int:
        with self._bl:
            rows, self._buf = self._buf, []
        if not rows:
            return 0
        with self._tx() as c:
            c.executemany("INSERT OR REPLACE INTO tele_1s(ts,mac,n,st,env,base,ratio,act,sat,flat,vin,tc,"
                          "env_b,base_b,ratio_b,act_b,sat_b,flat_b) "
                          "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        return len(rows)

    def rolled_to(self) -> Optional[int]:
        v = self.meta_get("rolled_to")
        return int(v) if v is not None else None

    def rollup(self, now: float, max_minutes: int = 1500) -> int:
        """Aggregate complete minutes of tele_1s into tele_1m. Returns minutes processed."""
        end = int(now) // 60 * 60
        start = self.rolled_to()
        if start is None:
            r = self._w_one("SELECT MIN(ts) FROM tele_1s")
            if r is None:
                return 0
            start = r // 60 * 60
        if start >= end:
            return 0
        end = min(end, start + max_minutes * 60)
        with self._tx() as c:
            c.execute(
                "INSERT OR REPLACE INTO tele_1m(ts,mac,n,cnt,env_avg,env_max,ratio_avg,ratio_max,act_avg,base_avg,"
                "vin_avg,tc_avg,tc_max,sat_sum,flat_sum,run_s,rest_s,alarm_s,other_s,"
                "env_b_avg,env_b_max,ratio_b_avg,ratio_b_max,act_b_avg,base_b_avg,sat_b_sum,flat_b_sum) "
                "SELECT ts/60*60, mac, MAX(n), COUNT(*), AVG(env), MAX(env), AVG(ratio), MAX(ratio), AVG(act), AVG(base),"
                " AVG(vin), AVG(tc), MAX(tc), SUM(sat), SUM(flat),"
                " SUM(st='RUN'), SUM(st='REST'), SUM(st='ALARM'), SUM(st NOT IN ('RUN','REST','ALARM')),"
                " AVG(env_b), MAX(env_b), AVG(ratio_b), MAX(ratio_b), AVG(act_b), AVG(base_b), SUM(sat_b), SUM(flat_b)"
                " FROM tele_1s WHERE ts>=? AND ts<? GROUP BY ts/60, mac", (start, end))
            c.execute("INSERT INTO meta(k,v) VALUES('rolled_to',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (str(end),))
        return (end - start) // 60

    def _w_one(self, sql: str, args: Iterable = ()):
        with self._wl:
            r = self._w.execute(sql, tuple(args)).fetchone()
        return r[0] if r else None

    def prune(self, now: float) -> int:
        """Delete tele_1s older than retention (only if already rolled up)."""
        cutoff = int(now) - self.retention_days * 86400
        rt = self.rolled_to()
        if rt is not None:
            cutoff = min(cutoff, rt)
        total = 0
        while True:
            lo = self._w_one("SELECT MIN(ts) FROM tele_1s")
            if lo is None or lo >= cutoff:
                break
            hi = min(cutoff, lo + 3600)
            with self._tx() as c:
                cur = c.execute("DELETE FROM tele_1s WHERE ts<?", (hi,))
                total += cur.rowcount
        return total

    def spark_seed(self, now: float, seconds: int = 1800, bucket: int = 30) -> Dict[str, Dict[int, List[float]]]:
        rows = self.q("SELECT mac, ts/? AS b, SUM(ratio) AS s, COUNT(*) AS c FROM tele_1s WHERE ts>=? GROUP BY mac, b",
                      (bucket, int(now) - seconds))
        out: Dict[str, Dict[int, List[float]]] = {}
        for r in rows:
            out.setdefault(r["mac"], {})[int(r["b"])] = [r["s"] or 0.0, r["c"]]
        return out

    def history(self, n: int, minutes: int, now: float) -> Dict[str, Any]:
        minutes = max(1, min(int(minutes), 7 * 1440))
        since = int(now) - minutes * 60
        pts: List[Dict[str, Any]] = []
        if minutes <= 180:
            bucket = max(1, minutes * 60 // 300)
            rows = self.q(
                "SELECT ts/?*? AS t, AVG(ratio) AS ratio, MAX(ratio) AS ratio_max, AVG(env) AS env, AVG(act) AS act,"
                " AVG(base) AS base, AVG(vin) AS vin, AVG(tc) AS tc, SUM(st='ALARM') AS alarm, SUM(st='RUN') AS run,"
                " COUNT(*) AS cnt, AVG(ratio_b) AS ratio_b, MAX(ratio_b) AS ratio_b_max, AVG(env_b) AS env_b,"
                " AVG(act_b) AS act_b, AVG(base_b) AS base_b FROM tele_1s WHERE ts>=? AND n=? GROUP BY ts/? ORDER BY t",
                (bucket, bucket, since, n, bucket))
            pts = rows
        else:
            bucket = max(60, (minutes * 60 // 400) // 60 * 60)
            rows = self.q(
                "SELECT ts/?*? AS t, SUM(ratio_avg*cnt)/SUM(cnt) AS ratio, MAX(ratio_max) AS ratio_max,"
                " SUM(env_avg*cnt)/SUM(cnt) AS env, SUM(act_avg*cnt)/SUM(cnt) AS act, SUM(base_avg*cnt)/SUM(cnt) AS base,"
                " SUM(vin_avg*cnt)/SUM(cnt) AS vin, SUM(tc_avg*cnt)/SUM(cnt) AS tc, SUM(alarm_s) AS alarm, SUM(run_s) AS run,"
                " SUM(cnt) AS cnt, SUM(ratio_b_avg*cnt)/SUM(CASE WHEN ratio_b_avg IS NULL THEN 0 ELSE cnt END) AS ratio_b,"
                " MAX(ratio_b_max) AS ratio_b_max, SUM(env_b_avg*cnt)/SUM(CASE WHEN env_b_avg IS NULL THEN 0 ELSE cnt END) AS env_b,"
                " SUM(act_b_avg*cnt)/SUM(CASE WHEN act_b_avg IS NULL THEN 0 ELSE cnt END) AS act_b,"
                " SUM(base_b_avg*cnt)/SUM(CASE WHEN base_b_avg IS NULL THEN 0 ELSE cnt END) AS base_b"
                " FROM tele_1m WHERE ts>=? AND n=? GROUP BY ts/? ORDER BY t",
                (bucket, bucket, since, n, bucket))
            pts = rows
        for p in pts:
            for k in ("ratio", "ratio_max", "env", "act", "base", "vin", "tc", "ratio_b", "ratio_b_max", "env_b", "act_b", "base_b"):
                if p[k] is not None:
                    p[k] = round(p[k], 4)
        return {"n": n, "minutes": minutes, "bucket_s": bucket, "t0": since, "t1": int(now), "points": pts}

    def base_reference(self, mac: str, now: float, days: int, exclude_recent_s: int, since: float = 0.0
                       ) -> Tuple[Optional[float], int]:
        lo = max(int(now) - days * 86400, int(since))
        hi = int(now) - exclude_recent_s
        rows = self._rconn().execute(
            "SELECT base_avg FROM tele_1m WHERE mac=? AND ts>=? AND ts<? AND base_avg>0", (mac, lo, hi)).fetchall()
        vals = [r[0] for r in rows]
        if not vals:
            return None, 0
        return statistics.median(vals), len(vals)

    # -------------------------------------------------------------- events
    def add_event(self, ts: float, n: int, mac: Optional[str], type_: str, text: str,
                  data: Optional[dict] = None, src: str = "hub", cloud_type: Optional[str] = None,
                  queue_max: int = 20000, code: Optional[str] = None) -> Tuple[int, Optional[int]]:
        """Insert an event (and, atomically, its cloud queue row). Returns (event_id, queue_seq|None)."""
        d = json.dumps(data or {}, ensure_ascii=False, separators=(",", ":"))
        with self._tx() as c:
            cur = c.execute("INSERT INTO events(ts,n,mac,type,text,data,src,code) VALUES(?,?,?,?,?,?,?,?)",
                            (ts, n, mac, type_, text, d, src, code))
            eid = cur.lastrowid
            seq = None
            if cloud_type:
                cur = c.execute("INSERT INTO cloud_queue(ts,n,type,text,data,code) VALUES(?,?,?,?,?,?)",
                                (ts, n, cloud_type, text, d, code))
                seq = cur.lastrowid
                over = c.execute("SELECT COUNT(*) FROM cloud_queue").fetchone()[0] - queue_max
                if over > 0:
                    c.execute("DELETE FROM cloud_queue WHERE seq IN (SELECT seq FROM cloud_queue ORDER BY seq LIMIT ?)", (over,))
                    log.warning("cloud queue over capacity, dropped %d oldest", over)
        return eid, seq

    def list_events(self, limit: int = 50, n: Optional[int] = None, before_id: Optional[int] = None,
                    types: Optional[List[str]] = None, since: Optional[float] = None,
                    codes: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        where, args = [], []
        if n is not None:
            where.append("e.n=?"); args.append(n)
        if before_id is not None:
            where.append("e.id<?"); args.append(before_id)
        if since is not None:
            where.append("e.ts>=?"); args.append(since)
        if types:
            where.append("e.type IN (%s)" % ",".join("?" * len(types))); args.extend(types)
        if codes:
            where.append("e.code IN (%s)" % ",".join("?" * len(codes))); args.extend(codes)
        sql = ("SELECT e.id,e.ts,e.n,e.mac,e.type,e.text,e.data,e.src,e.code,l.label AS alarm_label,l.note AS label_note "
               "FROM events e LEFT JOIN alarm_labels l ON l.event_id=e.id")
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY e.id DESC LIMIT ?"
        args.append(max(1, min(int(limit), 1000)))
        rows = self.q(sql, args)
        for r in rows:
            try:
                r["data"] = json.loads(r["data"]) if r["data"] else {}
            except Exception:
                r["data"] = {}
        return rows

    def get_event(self, eid: int) -> Optional[Dict[str, Any]]:
        return self.q1("SELECT id,ts,n,mac,type,text FROM events WHERE id=?", (eid,))

    # ----------------------------------------------------- error log (E-codes)
    def err_open(self, code: str, key: str, n: int, now: float, detail: dict) -> int:
        with self._tx() as c:
            cur = c.execute("INSERT INTO error_log(code,key,n,ts_set,detail) VALUES(?,?,?,?,?)",
                            (code, key, n, now, json.dumps(detail or {}, ensure_ascii=False, separators=(",", ":"))))
            return cur.lastrowid

    def err_close(self, rid: int, now: float) -> None:
        with self._tx() as c:
            c.execute("UPDATE error_log SET ts_clear=? WHERE id=? AND ts_clear IS NULL", (now, rid))

    def err_close_all(self, now: float, why: str = "") -> int:
        with self._tx() as c:
            cur = c.execute("UPDATE error_log SET ts_clear=? WHERE ts_clear IS NULL", (now,))
            return cur.rowcount

    def err_rows(self, since: float, limit: int = 500) -> List[Dict[str, Any]]:
        rows = self.q("SELECT id,code,key,n,ts_set,ts_clear,detail FROM error_log WHERE ts_set>=? OR ts_clear IS NULL "
                      "ORDER BY ts_set DESC LIMIT ?", (since, limit))
        for r in rows:
            try:
                r["detail"] = json.loads(r["detail"]) if r["detail"] else {}
            except Exception:
                r["detail"] = {}
        return rows

    def err_counts(self, since: float) -> Dict[Tuple[str, str], int]:
        return {(r["code"], r["key"]): r["c"] for r in self.q(
            "SELECT code, key, COUNT(*) AS c FROM error_log WHERE ts_set>=? GROUP BY code, key", (since,))}

    def err_prune(self, before: float) -> int:
        with self._tx() as c:
            return c.execute("DELETE FROM error_log WHERE ts_clear IS NOT NULL AND ts_clear<?", (before,)).rowcount

    def integrity_quick(self) -> str:
        """PRAGMA quick_check on a private connection (never blocks the writer). Returns 'ok' or the first problem."""
        c = sqlite3.connect(self.path, timeout=30)
        try:
            c.execute("PRAGMA query_only=ON")
            rows = c.execute("PRAGMA quick_check").fetchall()
            first = rows[0][0] if rows else "no result"
            return "ok" if first == "ok" else str(first)[:200]
        except sqlite3.DatabaseError as e:
            return "%s: %s" % (type(e).__name__, e)
        finally:
            c.close()

    # --------------------------------------------------------- cloud queue
    def queue_head(self) -> Optional[Dict[str, Any]]:
        return self.q1("SELECT * FROM cloud_queue WHERE dead=0 ORDER BY seq LIMIT 1")

    def queue_done(self, seq: int) -> None:
        with self._tx() as c:
            c.execute("DELETE FROM cloud_queue WHERE seq=?", (seq,))

    def queue_fail(self, seq: int, next_try: float, err: str, dead: bool = False) -> None:
        with self._tx() as c:
            c.execute("UPDATE cloud_queue SET attempts=attempts+1, next_try=?, last_err=?, dead=? WHERE seq=?",
                      (next_try, err[:200], 1 if dead else 0, seq))

    def queue_stats(self) -> Dict[str, Any]:
        r = self.q1("SELECT COUNT(*) AS n, MIN(ts) AS oldest FROM cloud_queue WHERE dead=0") or {}
        d = self.q1("SELECT COUNT(*) AS n FROM cloud_queue WHERE dead=1") or {}
        return {"pending": r.get("n", 0), "oldest_ts": r.get("oldest"), "dead": d.get("n", 0)}

    # ------------------------------------------------------- today / daily
    def today_stats(self, day_start: int, now: float) -> Dict[str, Dict[int, float]]:
        alarms = {r["n"]: r["c"] for r in self.q(
            "SELECT n, COUNT(*) AS c FROM events WHERE type='ALARM_ON' AND ts>=? AND n>0 GROUP BY n", (day_start,))}
        run = {r["n"]: float(r["s"] or 0) for r in self.q(
            "SELECT n, SUM(run_s) AS s FROM tele_1m WHERE ts>=? AND n>0 GROUP BY n", (day_start,))}
        rt = self.rolled_to() or day_start
        for r in self.q("SELECT n, SUM(st='RUN') AS s FROM tele_1s WHERE ts>=? AND n>0 GROUP BY n", (max(day_start, rt),)):
            run[r["n"]] = run.get(r["n"], 0.0) + float(r["s"] or 0)
        return {"alarms": alarms, "run_s": run}

    def compute_daily(self, date: str, now: float, final: bool = False, save: bool = True) -> List[Dict[str, Any]]:
        start, end = self.day_bounds(date)
        rt = self.rolled_to() or start
        stop = min(end, int(now), max(rt, start))   # data we can actually account for
        rows = {r["n"]: r for r in self.q(
            "SELECT n, SUM(cnt) AS cnt, SUM(run_s) AS run_s, SUM(rest_s) AS rest_s, SUM(alarm_s) AS alarm_s,"
            " MAX(ratio_max) AS mr FROM tele_1m WHERE ts>=? AND ts<? AND n>0 GROUP BY n", (start, end))}
        firsts = {r["n"]: r["f"] for r in self.q("SELECT n, MIN(ts) AS f FROM tele_1m WHERE n>0 GROUP BY n")}
        evs = self.q("SELECT n, type, data FROM events WHERE ts>=? AND ts<? AND n>0 AND type IN ('ALARM_ON','HEALTH','SHADOW_ALARM')",
                     (start, end))
        plant = self.q1("SELECT COUNT(*) AS c FROM events WHERE ts>=? AND ts<? AND type='PLANT_POWER_OFF'", (start, end))
        plant_n = (plant or {}).get("c", 0)
        alarm_c: Dict[int, int] = {}
        shadow_c: Dict[int, int] = {}
        health: Dict[int, Dict[str, int]] = {}
        for e in evs:
            if e["type"] == "ALARM_ON":
                alarm_c[e["n"]] = alarm_c.get(e["n"], 0) + 1
            elif e["type"] == "SHADOW_ALARM":
                shadow_c[e["n"]] = shadow_c.get(e["n"], 0) + 1
            else:
                try:
                    d = json.loads(e["data"] or "{}")
                except Exception:
                    d = {}
                if d.get("state") == "set" and not d.get("advisory"):
                    h = health.setdefault(e["n"], {})
                    h[d.get("flag", "?")] = h.get(d.get("flag", "?"), 0) + 1
        out = []
        for n in range(1, 7):
            r = rows.get(n)
            first = firsts.get(n)
            if r is None and n not in alarm_c and n not in health and n not in shadow_c:
                if first is None:
                    continue
            cnt = (r or {}).get("cnt") or 0
            p_start = max(start, first) if first is not None else start
            period = max(0, stop - p_start)
            offline_s = max(0, period - cnt) if first is not None else 0
            up = round(min(100.0, 100.0 * cnt / period), 1) if period > 0 else 0.0
            h = health.get(n, {})
            notes = []
            if h:
                notes.append("สุขภาพ: " + ", ".join("%s×%d" % (k, v) for k, v in sorted(h.items())))
            if shadow_c.get(n):
                notes.append("เงา: คล้าย ALARM %d ครั้ง (ไม่ได้แจ้งเตือน)" % shadow_c[n])
            if plant_n:
                notes.append("ไฟโรงสีดับ/ถอดปลั๊ก %d ครั้ง" % plant_n)
            out.append({
                "date": date, "node": n,
                "run_min": round(((r or {}).get("run_s") or 0) / 60.0, 1),
                "rest_min": round(((r or {}).get("rest_s") or 0) / 60.0, 1),
                "alarm_count": alarm_c.get(n, 0),
                "alarm_min": round(((r or {}).get("alarm_s") or 0) / 60.0, 1),
                "max_ratio": round((r or {}).get("mr") or 0.0, 2),
                "offline_min": round(offline_s / 60.0, 1),
                "uptime_pct": up,
                "health_incidents": sum(h.values()),
                "notes": "; ".join(notes),
                "final": 1 if final else 0,
            })
        if save:
            with self._tx() as c:
                c.execute("DELETE FROM daily_summary WHERE date=?", (date,))
                c.executemany(
                    "INSERT INTO daily_summary(date,node,run_min,rest_min,alarm_count,alarm_min,max_ratio,offline_min,"
                    "uptime_pct,health_incidents,notes,final,computed_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(o["date"], o["node"], o["run_min"], o["rest_min"], o["alarm_count"], o["alarm_min"],
                      o["max_ratio"], o["offline_min"], o["uptime_pct"], o["health_incidents"], o["notes"],
                      o["final"], now) for o in out])
        return out

    def get_daily(self, date: str) -> List[Dict[str, Any]]:
        return self.q("SELECT * FROM daily_summary WHERE date=? ORDER BY node", (date,))

    # ------------------------------------------------------------- backup
    def backup_to(self, dest: str) -> None:
        tmp = dest + ".tmp"
        if os.path.exists(tmp):
            os.remove(tmp)
        dst = sqlite3.connect(tmp)
        try:
            with self._wl:
                self._w.backup(dst)
        finally:
            dst.close()
        os.replace(tmp, dest)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.flush_tele()
        except Exception:
            log.exception("final flush failed")
        with self._wl:
            try:
                self._w.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except Exception:
                pass
            self._w.close()
