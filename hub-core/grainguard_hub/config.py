"""Hub configuration: defaults < YAML file < environment variables.

Every field can be overridden by an environment variable that is simply the
upper-cased field name (HUB_ID, CLOUD_URL, CLOUD_SECRET, EXPECTED_FW,
FLATLINE_S ...).  A YAML file (path in $HUB_CONFIG, or ./config.yaml) may use
the same names in lower case, flat or under a ``thresholds:`` key.
"""
from __future__ import annotations

import dataclasses
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

log = logging.getLogger("gg.config")

try:  # PyYAML is optional at runtime
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


@dataclass
class Config:
    # --- identity / cloud -------------------------------------------------
    hub_id: str = "mill-1"
    cloud_url: str = ""          # e.g. https://grainguard.example.workers.dev  (empty = offline mode)
    cloud_secret: str = ""
    expected_fw: str = ""        # empty = do not check firmware
    cloud_timeout_s: float = 10.0
    heartbeat_s: float = 30.0
    queue_max: int = 20000       # max events kept in the store-and-forward queue

    # --- broker -----------------------------------------------------------
    mqtt_enabled: bool = True
    mqtt_host: str = "127.0.0.1"
    mqtt_port: int = 1883
    mqtt_user: str = ""
    mqtt_pass: str = ""

    # --- http / storage ---------------------------------------------------
    http_host: str = "0.0.0.0"   # DF-42: install.sh sets HTTP_HOST to the node-LAN address; never expose to the internet
    http_port: int = 8080
    http_extra_hosts: str = ""   # additional addresses to listen on (e.g. the mill-LAN address of the UE300), comma separated
    data_dir: str = "./data"
    db_path: str = ""            # default: <data_dir>/grainguard.db
    dashboard_path: str = ""     # default: search ../dashboard/index.html
    admin_token: str = ""        # POST endpoints need header X-Admin-Token. MANDATORY (DF-42): the hub refuses to start without one
    admin_token_required: bool = True   # tests / bench only: False lets the hub run without a token
    admin_token_min_len: int = 12
    tz: str = "Asia/Bangkok"
    nic_a: str = ""              # NIC-A interface name for carrier detection (empty = disabled)
    nic_b: str = ""
    tele_retention_days: int = 7
    daily_times: str = "18:00,00:00"

    # --- health thresholds (contract defaults) ---------------------------
    stale_s: float = 5.0               # no tele for > stale_s  => offline
    offline_event_s: float = 15.0      # NODE_OFFLINE event after this much silence
    boot_grace_s: float = 120.0        # no NODE_OFFLINE alerts this long after hub boot / power restore
    flatline_s: float = 60.0           # flat==1 for this long (RUN/REST)
    flatline_clear_s: float = 5.0
    sat_window_s: float = 60.0
    sat_count: int = 20                # sat>0 in >= this many samples of the window
    sat_clear_count: int = 5
    drift_window_s: float = 600.0
    drift_lo: float = 0.5
    drift_hi: float = 2.0
    drift_min_samples: int = 300       # need this many base samples in the window
    drift_min_ref_minutes: int = 360   # need this much 7-day history to judge drift
    drift_ref_days: int = 7
    vin_low: float = 19.5              # DF-53 (P2): node shows steady yellow at the same level
    vin_high: float = 28.0
    vin_s: float = 30.0
    vin_clear_s: float = 10.0
    temp_high: float = 70.0
    temp_s: float = 10.0
    temp_clear_s: float = 30.0
    temp_clear_margin: float = 3.0
    reboot_count: int = 3
    reboot_window_s: float = 600.0
    seqgap_window_s: float = 300.0
    seqgap_pct: float = 10.0
    seqgap_clear_pct: float = 5.0
    seqgap_min_samples: int = 60
    fw_s: float = 5.0
    noisy_ratio: float = 0.0           # 0 = rule disabled (optional rule in contract)
    noisy_act_max: float = 0.0
    noisy_s: float = 60.0
    plant_window_s: float = 5.0        # all nodes silent within this window => PLANT_POWER_OFF
    plant_min_nodes: int = 2
    alarm_confirm_samples: int = 2     # tele-derived ALARM_ON needs this many ALARM samples
    alarm_clear_s: float = 600.0       # DF-54: a hub-side alarm is closed by the NODE'S ALARM_OFF event. Only if that event never
                                       # arrives, tele showing no ALARM for this long (never across a node reboot) closes it (+ HEALTH note)
    new_node_visible_s: float = 600.0  # unassigned MACs shown as "NEW" while seen within this time
    cal_stuck_s: float = 600.0         # E105: st==CAL longer than this
    ack_stuck_s: float = 30.0          # E401: ACK button held down (tele ackms) this long
    unacked_alarm_s: float = 1800.0    # E402: real alarm nobody acknowledged for this long

    # --- hub self-checks (E5xx) ------------------------------------------
    selfcheck_s: float = 5.0           # how often the cheap checks run
    disk_warn_pct: float = 85.0        # E501
    disk_clear_pct: float = 80.0
    cpu_hot_c: float = 80.0            # E507
    cpu_clear_c: float = 75.0
    uplink_fail_s: float = 300.0       # E503: no successful cloud delivery for this long
    auth_fail_count: int = 2           # E504: consecutive HTTP 401/403 answers
    ntp_cmd: str = "chronyc tracking"  # E505 (empty = do not look; a missing binary is tolerated)
    ntp_unsync_s: float = 3600.0       # E505: not synchronised for this long
    clock_jump_s: float = 30.0         # E505: wall clock moved against the monotonic clock by more than this
    restart_sticky_s: float = 3600.0   # E506: how long a service restart stays visible
    nic_a_down_s: float = 30.0         # E508: NIC-A carrier down this long ...
    power_hours: str = "06:00-17:00"   # ... while the mill is expected to have power (local time; empty = always)
    integrity_time: str = "03:30"      # E502: PRAGMA quick_check once a day (and right after a database error)
    integrity_first_s: float = 120.0   # first check this long after start-up (0 = disabled at start)

    # --- screen (ตะแกรง) lifecycle ---------------------------------------
    screen_prior_days: float = 30.0    # stage 1: a screen lasts about one month
    screen_k0: float = 2.0             # stage 2: shrinkage strength  w = n / (n + k0)
    screen_prior_cv: float = 0.35      # spread assumed when there is too little data to measure it
    screen_clip_pts_day: float = 10.0  # shown "used %" never moves more than this many points per day
    screen_advisory_pct: float = 90.0  # advisory event "ใกล้ถึงอายุตะแกรง" once per cycle
    screen_recent_days: float = 14.0   # window for "recent RUN-hours per day"
    screen_default_run_h_day: float = 10.0
    screen_min_life_h: float = 10.0    # a cycle shorter than this many RUN-hours is ignored as a typing mistake
    screen_alarm_window_days: float = 3.0   # a 'real' alarm this close before the change confirms the break
    screen_stage3_min_cycles: int = 3
    screen_refit_time: str = "00:10"
    screen_jobs: bool = True           # run the hourly / nightly jobs (tests switch this off to call them by hand)

    def db(self) -> str:
        return self.db_path or os.path.join(self.data_dir, "grainguard.db")


_TRUE = {"1", "true", "yes", "on", "y"}


def _cast(default: Any, value: Any) -> Any:
    if isinstance(default, bool):
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in _TRUE
    if isinstance(default, int):
        return int(float(value))
    if isinstance(default, float):
        return float(value)
    return str(value)


PLACEHOLDER_TOKENS = ("", "change_me", "changeme", "change-me", "admin", "password", "token", "your-token-here")


def check_admin_token(cfg: "Config") -> Optional[str]:
    """DF-42: returns a Thai error text if the admin token is missing / too weak / a placeholder, else None."""
    if not cfg.admin_token_required:
        return None
    t = (cfg.admin_token or "").strip()
    if t.lower() in PLACEHOLDER_TOKENS or t.upper().startswith("CHANGE"):
        return "ยังไม่ได้ตั้งรหัสผู้ดูแล (ADMIN_TOKEN) หรือยังเป็นค่าตัวอย่าง — ฮับจะไม่เริ่มทำงาน (DF-42)"
    if len(t) < cfg.admin_token_min_len:
        return "รหัสผู้ดูแลสั้นเกินไป (ต้องยาวอย่างน้อย %d ตัวอักษร) — ฮับจะไม่เริ่มทำงาน" % cfg.admin_token_min_len
    return None


def load_config(path: Optional[str] = None, env: Optional[Dict[str, str]] = None, **overrides: Any) -> Config:
    env = os.environ if env is None else env
    cfg = Config()
    defaults = {f.name: getattr(cfg, f.name) for f in dataclasses.fields(Config)}

    path = path or env.get("HUB_CONFIG") or ("config.yaml" if os.path.exists("config.yaml") else None)
    data: Dict[str, Any] = {}
    if path and os.path.exists(path):
        if yaml is None:
            raise RuntimeError("PyYAML is required to read " + path)
        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
        nested = raw.pop("thresholds", {}) or {}
        data.update({str(k).lower(): v for k, v in raw.items()})
        data.update({str(k).lower(): v for k, v in nested.items()})
        unknown = sorted(k for k in data if k not in defaults)
        if unknown:                                   # a typo would silently run on the default - say so loudly
            log.warning("config file %s: unknown key(s) ignored: %s", path, ", ".join(unknown))
    for name, default in defaults.items():
        if name in data and data[name] is not None:
            setattr(cfg, name, _cast(default, data[name]))
        ev = env.get(name.upper())
        if ev is not None and ev != "":
            setattr(cfg, name, _cast(default, ev))
    for k, v in overrides.items():
        if k not in defaults:
            raise KeyError(k)
        setattr(cfg, k, _cast(defaults[k], v))
    return cfg
