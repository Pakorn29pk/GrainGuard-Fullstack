"""Error catalogue (data/errors.yaml = single source of truth) + the book of currently active errors.

Principle: the HUB is the only component that diagnoses.  Nodes only report numbers; this module turns the
hub's conditions (health flags, offline, plant power off, hub self-checks) into catalogue codes.

    python -m grainguard_hub.errors --md > docs/ERRORS.md      # regenerate the Thai table
"""
from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

log = logging.getLogger("gg.errors")

SEV_RANK = {"critical": 0, "fault": 1, "warn": 2, "info": 3}
SEV_TH = {"critical": "วิกฤต", "fault": "ขัดข้อง", "warn": "เตือน", "info": "แจ้งทราบ"}
SCOPE_TH = {"node": "เครื่อง/ก้อนเคส", "fleet": "ทั้งโรงสี", "hub": "ฮับ", "cloud": "คลาวด์"}

# health flag (engine) -> catalogue code
FLAG_CODE = {
    "flatline": "E101", "saturation": "E102", "drift": "E103", "noisy": "E104", "cal_stuck": "E105",
    "vin_low": "E201", "vin_high": "E202", "temp_high": "E203", "reboot_loop": "E204",
    "link_loss": "E302", "fw_mismatch": "E303", "ack_stuck": "E401", "unacked_alarm": "E402",
    "fault": "E199",
    "flatline_b": "E111", "saturation_b": "E112",
}
# hub / fleet conditions -> (code, short flag name used in events)
HUB_FLAG = {
    "E310": "plant_power_off", "E501": "disk_high", "E502": "db_error", "E503": "uplink_down", "E504": "cloud_auth",
    "E505": "clock", "E506": "service_restart", "E507": "cpu_hot", "E508": "nic_a_down",
}
OFFLINE_CODE = "E301"
HUB_KEY = "hub"


def catalog_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "errors.yaml")


_CAT: Optional[Dict[str, Dict[str, Any]]] = None


def catalog() -> Dict[str, Dict[str, Any]]:
    global _CAT
    if _CAT is None:
        if yaml is None:
            raise RuntimeError("PyYAML is required to load the error catalogue")
        with open(catalog_path(), "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
        cat = {}
        for code, d in (raw.get("codes") or {}).items():
            d = dict(d)
            d["code"] = str(code)
            d.setdefault("causes", [])
            cat[str(code)] = d
        _CAT = cat
    return _CAT


def info(code: str) -> Dict[str, Any]:
    return catalog().get(code) or {"code": code, "sev": "warn", "scope": "node", "th": code, "causes": [], "where": ""}


def title(code: str) -> str:
    return info(code).get("th", code)


def sev_key(code: str) -> Tuple[int, str]:
    return (SEV_RANK.get(info(code).get("sev", "warn"), 9), code)


def catalog_list() -> List[Dict[str, Any]]:
    return [dict(v) for _, v in sorted(catalog().items())]


def diagnosis_line(label: str, codes: List[str]) -> str:
    """'ขัด 3: E301 ก้อนเคสไม่ตอบสนอง (offline) — ลองเช็ค ไฟ 24 V ของเครื่อง (ดูไฟ LED บอร์ด) → ไฟพอร์ตสวิตช์ → สาย Cat6 LAN → บอร์ด'"""
    if not codes:
        return "%s: ปกติ — ไม่มีรหัสข้อผิดพลาด" % label
    codes = sorted(codes, key=sev_key)
    c0 = info(codes[0])
    where = (c0.get("where") or "").replace("ตามลำดับ: ", "")
    s = "%s: %s %s — ลองเช็ค %s" % (label, c0["code"], c0.get("th", ""), where)
    if len(codes) > 1:
        s += "  (ยังมี: %s)" % ", ".join(codes[1:])
    return s


def render_markdown() -> str:
    cat = catalog()
    L = ["# รหัสข้อผิดพลาด GrainGuard (ฉบับสร้างอัตโนมัติ)", "",
         "ไฟล์นี้สร้างจาก `hub-core/grainguard_hub/data/errors.yaml` — **อย่าแก้ในไฟล์นี้โดยตรง** "
         "(รันใหม่: `python -m grainguard_hub.errors --md > docs/ERRORS.md`).", "",
         "หลักการ: **ฮับเป็นผู้วินิจฉัยเพียงตัวเดียว** ก้อนเคสแต่ละตัวส่งแค่ตัวเลขดิบ ฮับเอามาเทียบกฎแล้วออกรหัส. "
         "ข้อผิดพลาดเดียวที่ฮับรายงานเองไม่ได้คือ \"ฮับตาย\" — คลาวด์เป็นผู้ตรวจพบและออกรหัส E900 "
         "(ไฟหอสัญญาณและเสียงเตือนที่ก้อนเคสยังทำงานเองได้).", "",
         "ระดับความรุนแรง: **วิกฤต** (critical) · **ขัดข้อง** (fault) · **เตือน** (warn) · **แจ้งทราบ** (info)", ""]
    groups = [("เซนเซอร์/สัญญาณ (E1xx)", "E1"), ("ไฟเลี้ยงและบอร์ด (E2xx)", "E2"),
              ("การเชื่อมต่อ (E3xx)", "E3"), ("ปุ่มและการรับทราบ (E4xx)", "E4"),
              ("ฮับ (E5xx)", "E5"), ("คลาวด์ (E9xx)", "E9")]
    for gname, pre in groups:
        rows = [v for k, v in sorted(cat.items()) if k.startswith(pre)]
        if not rows:
            continue
        L += ["## " + gname, "",
              "| รหัส | ระดับ | ความหมาย | ที่มา (กฎที่ฮับใช้ตรวจ) | สาเหตุที่เป็นไปได้ | ตรวจที่ไหนก่อน |",
              "|---|---|---|---|---|---|"]
        for v in rows:
            causes = "<br>".join("%d. %s" % (i + 1, c) for i, c in enumerate(v.get("causes", [])))
            L.append("| **%s** | %s | %s | %s | %s | %s |" % (
                v["code"], SEV_TH.get(v.get("sev"), v.get("sev")), _md(v.get("th", "")), _md(v.get("rule", "")),
                _md(causes, keep_br=True), _md(v.get("where", ""))))
        L.append("")
    L += ["## หมายเหตุ", "",
          "- รหัส **E199** เป็นส่วนเพิ่มฝั่งฮับ (สัญญาณ `st=FAULT` จากบอร์ดไม่มีรหัสในสเปก v1) รอยืนยันกับผู้ออกแบบสเปก.",
          "- เหตุการณ์ \"ใกล้ถึงอายุตะแกรง\" (ใช้ไปแล้ว 90%) **ไม่ใช่ข้อผิดพลาด** จึงไม่มีรหัส E — ดู `LIFECYCLE.md`.", ""]
    return "\n".join(L)


def _md(s: str, keep_br: bool = False) -> str:
    s = str(s).replace("|", "\\|").replace("\n", " ")
    return s


class ErrorBook:
    """Active errors, persisted to ``error_log`` (open row = active, ts_clear NULL).

    key = node MAC for node errors, "hub" for fleet/hub errors.  Open rows left over from a previous run are closed
    at start-up (the hub re-detects whatever is still true).
    """

    def __init__(self, store, clock: Callable[[], float]):
        self.store = store
        self.clock = clock
        self.lock = threading.RLock()
        self.active: Dict[Tuple[str, str], Dict[str, Any]] = {}

    def start(self, now: float) -> None:
        try:
            self.store.err_close_all(now, "hub_restart")
        except Exception:
            log.exception("closing stale errors failed")

    def open(self, code: str, key: str, n: int, now: float, detail: Optional[dict] = None) -> bool:
        with self.lock:
            if (code, key) in self.active:
                if detail:
                    self.active[(code, key)]["detail"] = detail
                return False
            rid = None
            try:
                rid = self.store.err_open(code, key, n, now, detail or {})
            except Exception:
                log.exception("error_log insert failed")
            self.active[(code, key)] = {"code": code, "key": key, "n": n, "since": now, "detail": detail or {}, "id": rid}
            return True

    def close(self, code: str, key: str, now: float) -> bool:
        with self.lock:
            a = self.active.pop((code, key), None)
            if a is None:
                return False
            try:
                if a.get("id") is not None:
                    self.store.err_close(a["id"], now)
            except Exception:
                log.exception("error_log close failed")
            return True

    def close_key(self, key: str, now: float, codes: Optional[List[str]] = None) -> List[str]:
        with self.lock:
            gone = [c for (c, k) in list(self.active) if k == key and (codes is None or c in codes)]
            for c in gone:
                self.close(c, key, now)
            return gone

    def is_open(self, code: str, key: str) -> bool:
        return (code, key) in self.active

    def codes(self, key: str) -> List[str]:
        with self.lock:
            return sorted((c for (c, k) in self.active if k == key), key=sev_key)

    def entries(self, key: str) -> List[Dict[str, Any]]:
        with self.lock:
            rows = [a for (c, k), a in self.active.items() if k == key]
        rows.sort(key=lambda a: sev_key(a["code"]))
        return [{"code": a["code"], "since": int(a["since"]), "detail": a.get("detail") or {}} for a in rows]

    def all_active(self) -> List[Dict[str, Any]]:
        with self.lock:
            return [dict(a) for a in self.active.values()]


if __name__ == "__main__":  # pragma: no cover
    import sys
    if "--md" in sys.argv:
        sys.stdout.write(render_markdown())
    else:
        sys.stdout.write(json.dumps(catalog_list(), ensure_ascii=False, indent=1))
