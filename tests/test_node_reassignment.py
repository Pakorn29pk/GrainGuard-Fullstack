"""Registry moves use isolated SQLite fixtures, never a real Pi or Node."""
from concurrent.futures import ThreadPoolExecutor
import sqlite3
import threading

import pytest

from conftest import MACS
from grainguard_hub.engine import Engine
from test_dashboard_native import native, TOKEN


def test_move_requires_fresh_telemetry_and_preserves_old_history(H):
    h = H(assign=1, boot_grace_s=0, sat_count=1, sat_clear_count=0)
    mac = MACS[0]
    h.run(2, sat=1)
    assert "E102" in h.node(1)["codes"]
    h.store.flush_tele()
    old_rows = h.store.q("SELECT ts,n,ratio FROM tele_1s WHERE mac=?", (mac,))
    h.eng.assign(2, mac, "Moved receiver")
    assert h.eng.slot_mac(1) is None and h.eng.slot_mac(2) == mac
    pending = h.node(2)
    assert pending["cls"] == "unknown" and pending["state"] == "WAITING"
    assert pending["last_seen_s"] is None and pending["ratio"] is None
    assert pending["codes"] == [] and not h.eng.states[mac].sat_samples
    assert not h.eng.states[mac].spark
    assert h.store.q("SELECT ts,n,ratio FROM tele_1s WHERE mac=?", (mac,)) == old_rows
    errors = h.store.q("SELECT n,ts_clear FROM error_log WHERE key=? AND code='E102'", (mac,))
    assert errors and all(r["n"] == 1 and r["ts_clear"] is not None for r in errors)
    h.tele(mac, sat=1)
    h.eng.tick(h.now)
    h.store.flush_tele()
    assert h.node(2)["last_seen_s"] == 0 and h.node(2)["state"] == "RUN"
    assert "E102" in h.node(2)["codes"]
    active = h.eng.errors.all_active()
    assert all(e["n"] == 2 for e in active if e["key"] == mac)
    assert h.store.q("SELECT n FROM tele_1s WHERE mac=? ORDER BY ts", (mac,))[-1]["n"] == 2


def test_move_failure_does_not_mutate_memory_or_destination(H, monkeypatch):
    h = H(assign=2)
    a, b = MACS[:2]
    before = {mac:(st.machine,st.label) for mac,st in h.eng.states.items()}
    def fail(*_args, **_kw):
        raise sqlite3.OperationalError("test registry failure")
    monkeypatch.setattr(h.store, "assign", fail)
    with pytest.raises(sqlite3.OperationalError):
        h.eng.assign(2, a, "Must not apply")
    assert {mac:(st.machine,st.label) for mac,st in h.eng.states.items()} == before
    assert h.eng.slot_mac(2) == b
    with pytest.raises(sqlite3.OperationalError):
        h.eng.assign(3, "aaaaaaaaaaaa", "New failure")
    assert "aaaaaaaaaaaa" not in h.eng.states


def test_replacement_clears_displaced_label_in_db_and_after_restart(H):
    h = H(assign=2)
    a, b = MACS[:2]
    h.eng.assign(2, b, "Old destination")
    h.tele(b)
    h.eng.assign(2, a, "New destination")
    displaced = h.eng.states[b]
    assert displaced.machine is None and displaced.label is None and displaced.last_rx is None
    row = next(r for r in h.store.list_nodes() if r["mac"] == b)
    assert row["machine"] is None and row["label"] is None
    restarted = Engine(h.cfg, h.store, clock=lambda:h.now)
    assert restarted.states[b].label is None and restarted.label_of(restarted.states[b]) == "โหนดใหม่"
    assert restarted.slot_mac(2) == a and restarted.slot_mac(1) is None


def test_unassign_and_readd_do_not_relabel_unassigned_history(H):
    h = H(assign=1)
    mac = MACS[0]
    h.run(1)
    h.eng.assign(None, mac)
    assert h.eng.states[mac].label is None and h.eng.slot_mac(1) is None
    h.tele(mac, ratio=1.7)
    h.now += 1
    h.eng.assign(3, mac, "New location")
    rows = h.store.q("SELECT ts,n FROM tele_1s WHERE mac=? ORDER BY ts", (mac,))
    assert [r["n"] for r in rows] == [1,0]
    h.tele(mac)
    h.store.flush_tele()
    assert h.node(3)["mac"] == mac and h.node(3)["label"] == "New location"
    assert [r["n"] for r in h.store.q("SELECT n FROM tele_1s WHERE mac=? ORDER BY ts", (mac,))] == [1,0,3]


def test_move_preserves_open_physical_alarm_without_fabricating_clear(H):
    h = H(assign=1)
    mac = MACS[0]
    h.eng.on_evt(mac, {"type":"ALARM_ON", "seq":1, "mode":"ALARM_ON"}, h.now)
    before = h.store.meta_get("alarm:" + mac)
    assert h.eng.states[mac].alarm_active
    h.eng.assign(2, mac)
    assert h.eng.states[mac].alarm_active and h.store.meta_get("alarm:" + mac) == before
    assert not h.events("ALARM_OFF")
    assert h.node(2)["state"] == "WAITING"


def test_two_concurrent_moves_leave_one_unique_target_and_matching_db(H):
    h = H(assign=2)
    barrier = threading.Barrier(2)
    def move(mac):
        barrier.wait()
        h.eng.assign(3, mac, mac)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(move, MACS[:2]))
    memory = {mac:st.machine for mac,st in h.eng.states.items()}
    database = {row["mac"]:row["machine"] for row in h.store.list_nodes()}
    assert memory == database and list(memory.values()).count(3) == 1
    assert all(n is None or n == 3 for n in memory.values())


def test_api_move_updates_tracking_and_unassign_last_leaves_empty(native):
    a, b = MACS[:2]
    assert native.post("/api/node/1/assign", {"mac":a,"label":"Original"}, TOKEN)[0] == 200
    assert native.post("/api/node/2/assign", {"mac":b,"label":"Receiver"}, TOKEN)[0] == 200
    assert native.post("/local-api/config", {"visible_slots":[2]}, TOKEN)[0] == 200
    status, moved = native.post("/api/node/1/assign", {"mac":b,"label":"Moved","expected_source_machine":2,"expected_target_mac":a}, TOKEN)
    assert status == 200 and moved["config"]["visible_slots"] == [1]
    assert moved["assignment"]["previous_machine"] == 2 and moved["assignment"]["replaced_mac"] == a
    assert native.hub.engine.slot_mac(2) is None and native.hub.engine.slot_mac(1) == b
    assert native.get("/local-api/config")[1]["visible_slots"] == [1]
    status, removed = native.post("/api/node/1/assign", {"unassign":True,"expected_source_machine":1,"expected_target_mac":b}, TOKEN)
    assert status == 200 and removed["config"]["visible_slots"] == []
    assert native.get("/local-api/config")[1]["visible_slots"] == []


def test_api_stale_mapping_guards_reject_without_changing_bindings(native):
    a, b = MACS[:2]
    native.post("/api/node/1/assign", {"mac":a}, TOKEN)
    native.post("/api/node/2/assign", {"mac":b}, TOKEN)
    before = native.get("/local-api/config")[1]
    for payload in ({"mac":b,"expected_source_machine":None,"expected_target_mac":a},
                    {"mac":b,"expected_source_machine":2,"expected_target_mac":None},
                    {"unassign":True,"expected_source_machine":1,"expected_target_mac":b}):
        assert native.post("/api/node/1/assign", payload, TOKEN)[0] == 409
    assert native.hub.engine.slot_mac(1) == a and native.hub.engine.slot_mac(2) == b
    assert native.get("/local-api/config")[1] == before


def test_config_replace_failure_reports_applied_mapping_and_warning(native, monkeypatch):
    mac = MACS[0]
    native.post("/api/node/2/assign", {"mac":mac}, TOKEN)
    native.post("/local-api/config", {"visible_slots":[2]}, TOKEN)
    def fail(*_args):
        raise OSError("test final rename failure")
    monkeypatch.setattr("grainguard_hub.api.os.replace", fail)
    status, result = native.post("/api/node/1/assign", {"mac":mac}, TOKEN)
    assert status == 200 and result["ok"] is True and result["config_warning"]
    assert result["config"]["visible_slots"] == [2]
    assert native.hub.engine.slot_mac(1) == mac and native.hub.engine.slot_mac(2) is None
    assert not list(__import__('pathlib').Path(native.cfg.data_dir).glob("dashboard-config-*.tmp"))


def test_config_preflight_failure_keeps_assignment_unchanged(native, monkeypatch):
    mac = MACS[0]
    native.post("/api/node/2/assign", {"mac":mac}, TOKEN)
    native.post("/local-api/config", {"visible_slots":[2]}, TOKEN)
    def fail(*_args, **_kwargs):
        raise OSError("test temporary file failure")
    monkeypatch.setattr("grainguard_hub.api.tempfile.NamedTemporaryFile", fail)
    status, _ = native.post("/api/node/1/assign", {"mac":mac}, TOKEN)
    assert status == 503
    assert native.hub.engine.slot_mac(2) == mac and native.hub.engine.slot_mac(1) is None
    assert native.get("/local-api/config")[1]["visible_slots"] == [2]


def test_historical_events_keep_original_slot_after_receiver_move(native):
    mac = MACS[0]
    native.post("/api/node/2/assign", {"mac":mac,"label":"Original machine"}, TOKEN)
    native.hub.engine._event(native.hub.clock(), 2, mac, "HEALTH", "Original machine: historical diagnostic", {"test":True})
    original = native.get("/api/events?n=2")[1]["events"]
    event = next(e for e in original if e["type"] == "HEALTH")
    native.post("/api/node/1/assign", {"mac":mac,"label":"New machine"}, TOKEN)
    history = native.get("/api/events?n=2")[1]["events"]
    persisted = next(e for e in history if e["id"] == event["id"])
    assert persisted["n"] == 2 and persisted["text"] == event["text"]
    assert persisted["label"] != "New machine"
