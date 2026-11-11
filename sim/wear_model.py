"""Synthetic screen wear for demos and tests: what the hub's tele_1m rows would look like while a screen ages.

wear_values(u, ...) gives the one-minute (or one-hour) aggregates of a RUNNING machine at wear u in [0, 1]
(u = RUN-hours used / life).  The wear signature rises before the break: peaks (ratio_max) get higher and more
frequent, the baseline sags a little and the activity gets stronger.  Not part of the production hub.
"""
from __future__ import annotations

import random
from typing import List, Tuple


def wear_values(u: float, level: float, rng: random.Random, noise: float = 1.0) -> Tuple[float, float, float, float]:
    """-> (ratio_avg, ratio_max, base_avg, act_avg) for a RUN row at wear u."""
    u = max(0.0, u)
    ratio = 1.0 + 0.10 * u ** 2 + rng.gauss(0, 0.03 * noise)
    ratio_max = ratio * 1.2 + 0.9 * u ** 3 + abs(rng.gauss(0, 0.06 * noise))
    base = level * (1.0 - 0.12 * u ** 2) + rng.gauss(0, 0.5 * noise)
    act = level * 0.6 * (1.0 + 0.25 * u ** 2) * (1.0 + rng.gauss(0, 0.04 * noise))
    return ratio, ratio_max, base, act


def synth_machine(n: int, mac: str, rng: random.Random, t_start: int, n_cycles: int, life_mean: float, life_sd: float,
                  run_h_day: int, level: float = 150.0, row_s: int = 3600, tz_off_h: int = 7, hour0: int = 6,
                  noise: float = 1.0) -> Tuple[List[tuple], List[Tuple[int, float]]]:
    """Hourly tele_1m-style rows for one machine over n_cycles screens.
    Returns (rows for tele_1m, [(break_ts, true_life_run_h), ...]). A screen breaks when its RUN-hours reach its life."""
    rows: List[tuple] = []
    breaks: List[Tuple[int, float]] = []
    t = t_start
    life = max(200.0, rng.gauss(life_mean, life_sd))
    used = 0.0
    while len(breaks) < n_cycles:
        hour = ((t // 3600) + tz_off_h) % 24
        running = (hour - hour0) % 24 < run_h_day
        h = row_s / 3600.0
        if running:
            ratio, rmax, base, act = wear_values(used / life, level, rng, noise)
            used += h
            rows.append((t, mac, n, row_s, level * ratio, level * rmax, ratio, rmax, act, base, 24.1, 41.0, 42.5, 0, 0,
                         row_s, 0, 0, 0))
        else:
            rows.append((t, mac, n, row_s, level * 0.15, level * 0.18, 0.15, 0.18, level * 0.1, level, 24.1, 40.0, 41.0, 0, 0,
                         0, row_s, 0, 0))
        t += row_s
        if used >= life:
            breaks.append((t, life))
            life = max(200.0, rng.gauss(life_mean, life_sd))
            used = 0.0
    return rows, breaks


INSERT_1M = ("INSERT OR REPLACE INTO tele_1m(ts,mac,n,cnt,env_avg,env_max,ratio_avg,ratio_max,act_avg,base_avg,vin_avg,tc_avg,"
             "tc_max,sat_sum,flat_sum,run_s,rest_s,alarm_s,other_s) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)")
