#!/usr/bin/env python3
"""Bring up broker + hub + mock cloud + 6 virtual nodes (with 14 days of seeded history), drive the plant
through normal / alarm / offline+warning / PLANT_POWER_OFF / new-node / hub-unreachable states and take
Chromium screenshots of the real dashboard into ../screens/.

    python sim/screens.py [outdir]
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "hub-core"))

from playwright.sync_api import sync_playwright  # noqa: E402

from grainguard_hub.app import Hub  # noqa: E402
from grainguard_hub.config import Config  # noqa: E402
from grainguard_hub.store import Store  # noqa: E402
from mock_cloud import MockCloud  # noqa: E402
from node_sim import DEFAULT_MACS, Fleet, VirtualNode  # noqa: E402
from seed_history import LEVELS, seed  # noqa: E402
from stack import FAST, free_port, start_broker  # noqa: E402


def get(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return json.loads(r.read())


def wait(cond, timeout=30, msg=""):
    end = time.time() + timeout
    while time.time() < end:
        try:
            v = cond()
            if v:
                return v
        except Exception:
            pass
        time.sleep(0.3)
    raise RuntimeError("timeout: " + msg)


def shot(page, locator, path):
    """Element screenshot with the sticky top bar parked (otherwise it is painted over tall elements)."""
    page.evaluate("document.querySelector('.topbar').style.position='static'")
    try:
        locator.screenshot(path=path)
    finally:
        page.evaluate("document.querySelector('.topbar').style.position=''")


def main() -> int:
    out = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "screens"))
    os.makedirs(out, exist_ok=True)
    work = tempfile.mkdtemp(prefix="gg-screens-")
    broker = start_broker(work)
    cloud = MockCloud("screens-secret").start()
    data = os.path.join(work, "data")
    s = Store(os.path.join(data, "grainguard.db"))
    seed(s, time.time(), running_tail=(0, 1, 2, 4))
    s.close()
    port = free_port()
    cfg = Config(data_dir=data, mqtt_port=broker.port, cloud_url=cloud.url, cloud_secret="screens-secret",
                 http_host="127.0.0.1", http_port=port, expected_fw="1.0.0", admin_token_required=False, **FAST)
    hub = Hub(cfg)
    hub.start()
    fleet = Fleet("127.0.0.1", broker.port)
    for i, n in enumerate(fleet.nodes):
        n.level = LEVELS[i]
        n.base = LEVELS[i]
    fleet.start()
    for i, n in enumerate(fleet.nodes):
        n.inject("set_state", state="REST" if i in (3, 5) else "RUN")
    base = "http://127.0.0.1:%d" % port
    errors = []
    try:
        wait(lambda: all(n["cls"] == "ok" for n in get(base + "/api/nodes")["nodes"]), 25, "all nodes ok")
        time.sleep(4)
        with sync_playwright() as p:
            br = p.chromium.launch()
            ctx = br.new_context(viewport={"width": 1280, "height": 900}, locale="th-TH", timezone_id="Asia/Bangkok")
            pg = ctx.new_page()
            pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(base + "/")
            pg.wait_for_selector(".card[data-k=ok]")
            time.sleep(1.5)
            pg.screenshot(path=out + "/01-normal.png", full_page=True)
            print("01 normal")

            # --- one alarm
            fleet.nodes[2].inject("alarm", 120)
            wait(lambda: get(base + "/api/nodes")["nodes"][2]["cls"] == "alarm", 20, "alarm class")
            time.sleep(2.5)
            pg.screenshot(path=out + "/02-alarm.png", full_page=True)
            print("02 alarm")
            ctx2 = br.new_context(viewport={"width": 1280, "height": 900}, locale="th-TH", timezone_id="Asia/Bangkok", color_scheme="dark")
            pg2 = ctx2.new_page()
            pg2.on("pageerror", lambda e: errors.append(str(e)))
            pg2.goto(base + "/")
            pg2.wait_for_selector(".card[data-k=alarm]")
            time.sleep(1.5)
            pg2.screenshot(path=out + "/05-dark-alarm.png", full_page=True)
            ctx2.close()
            ctx3 = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, locale="th-TH", timezone_id="Asia/Bangkok")
            pg3 = ctx3.new_page()
            pg3.goto(base + "/")
            pg3.wait_for_selector(".card[data-k=alarm]")
            time.sleep(1.5)
            pg3.screenshot(path=out + "/06-mobile-alarm.png", full_page=True)
            ow = pg3.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            print("mobile horizontal overflow px:", ow)
            ctx3.close()
            # press the real ACK button
            pg.click(".card[data-n='3'] .ack")
            wait(lambda: fleet.nodes[2].ack == 1, 10, "node received ack")
            print("ACK button reached the node")
            time.sleep(2.5)
            pg.screenshot(path=out + "/02b-alarm-acked.png", full_page=True)
            fleet.nodes[2].inject("clear")

            # --- offline + health warning
            fleet.nodes[4].power_off()
            fleet.nodes[1].inject("flatline", 600)
            wait(lambda: get(base + "/api/nodes")["nodes"][4]["cls"] == "offline", 20, "node 5 offline")
            wait(lambda: get(base + "/api/nodes")["nodes"][1]["cls"] == "warn", 25, "node 2 warn")
            wait(lambda: get(base + "/api/nodes")["nodes"][2]["cls"] == "ok", 20, "alarm cleared")
            time.sleep(3.5)
            pg.screenshot(path=out + "/03-offline-and-warn.png", full_page=True)
            print("03 offline + warn")
            pg.locator("#sec-errors").scroll_into_view_if_needed()
            time.sleep(1.0)
            shot(pg, pg.locator("#sec-errors"), out + "/11-errors.png")
            er = get(base + "/api/errors")
            print("errors active:", [(x["code"], x["label"]) for x in er["active"]])
            print("diagnosis:", [d["text"] for d in er["diagnosis"] if d["codes"]])
            pg.evaluate('window.scrollTo(0,0)')

            # --- plant power off
            fleet.nodes[1].inject("clear")
            fleet.nodes[4].power_on()
            wait(lambda: get(base + "/api/nodes")["nodes"][4]["cls"] == "ok", 20, "node 5 back")
            time.sleep(2)
            fleet.plant_off()
            wait(lambda: get(base + "/api/nodes")["hub"]["plant_power_off"], 25, "plant off detected")
            time.sleep(2.5)
            pg.screenshot(path=out + "/04-plant-off.png", full_page=True)
            print("04 plant off")
            ev = [e["type"] for e in get(base + "/api/events?limit=30")["events"]]
            print("events during plant off:", ev[:8])
            fleet.plant_on(0.2)
            for i, n in enumerate(fleet.nodes):
                n.inject("set_state", state="REST" if i in (3, 5) else "RUN")
            wait(lambda: not get(base + "/api/nodes")["hub"]["plant_power_off"], 25, "plant back")
            wait(lambda: all(n["cls"] == "ok" for n in get(base + "/api/nodes")["nodes"]), 25, "all ok again")

            # --- new node + assign dialog
            nn = VirtualNode("a4cf12ab3499", "127.0.0.1", broker.port)
            nn.power_on()
            t = time.time()
            while time.time() - t < 12:
                nn.step()
                time.sleep(1)
                if get(base + "/api/nodes")["new"]:
                    break
            pg.reload()
            pg.wait_for_selector("#bn-new")
            pg.click("#bn-new button")
            pg.wait_for_selector("dialog[open]")
            time.sleep(0.6)
            pg.screenshot(path=out + "/07-assign-dialog.png", full_page=False)
            print("07 assign dialog")
            pg.keyboard.press("Escape")
            nn.power_off(graceful=True)

            # --- screen lifecycle panel (2 completed cycles seeded on machine 3)
            pg.wait_for_selector(".lcard .pct")
            for sel in (".lcard[data-n='3'] details.ld summary",):
                for i in range(pg.locator(sel).count()):
                    pg.locator(sel).nth(i).click()
            time.sleep(1.5)
            pg.locator("#sec-life").scroll_into_view_if_needed()
            shot(pg, pg.locator("#sec-life"), out + "/12-lifecycle.png")
            print("12 lifecycle")
            lc = get(base + "/api/lifecycle")
            print("lifecycle:", [(m["n"], m["state"]["stage"], round(m["state"]["used_pct"]), m["state"]["conf"], len(m["cycles"]))
                                 for m in lc["machines"] if m["state"]])
            pg.click(".lcard[data-n='2'] .lbig")
            pg.wait_for_selector("#dlg-chg[open]")
            time.sleep(0.5)
            pg.screenshot(path=out + "/13-change-dialog.png", full_page=False)
            pg.keyboard.press("Escape")

            # --- shadow mode: a candidate alarm is shown but is not a real alarm; owner labels the alarms
            fleet.nodes[0].inject("mode", mode="SHADOW")
            time.sleep(2)
            fleet.nodes[0].inject("alarm", 90)
            wait(lambda: get(base + "/api/nodes")["nodes"][0]["cls"] == "shadow", 20, "shadow class")
            time.sleep(6)
            pg.evaluate('window.scrollTo(0,0)')
            shot(pg, pg.locator(".card[data-n='1']"), out + "/14-shadow-card.png")
            pg.locator("#h-ev").locator("xpath=..").scroll_into_view_if_needed()
            pg.wait_for_selector("#events li .lblrow")
            pg.evaluate("document.querySelector('#events').scrollTop=0")
            pg.locator("#events li:has(.lblrow)").first.locator(".lbtn[data-l=false]").click()
            time.sleep(1.2)
            pg.locator("#events li:has(.lblrow)").nth(1).locator(".lbtn[data-l=real]").click()
            time.sleep(1.2)
            pg.evaluate("document.querySelector('#events').scrollTop=0")
            shot(pg, pg.locator("#h-ev").locator("xpath=.."), out + "/15-events-labels.png")
            print("14/15 shadow + labels; cloud events so far:", cloud.event_types())
            fleet.nodes[0].inject("clear")
            wait(lambda: get(base + "/api/nodes")["nodes"][0]["cls"] == "ok", 20, "shadow alarm over")
            fleet.nodes[0].inject("mode", mode="ALARM_ON")
            time.sleep(2)

            # --- history charts
            pg.click("#hist-range button:nth-child(4)")
            time.sleep(1.5)
            pg.locator("#h-hist").scroll_into_view_if_needed()
            pg.locator(".cols").screenshot(path=out + "/09-history-7d.png")
            pg.click("#hist-range button:nth-child(1)")
            time.sleep(1.2)
            pg.locator(".cols").screenshot(path=out + "/09b-history-1h.png")
            pg.locator("#h-day").scroll_into_view_if_needed()
            time.sleep(0.5)
            pg.locator("#h-day").locator("xpath=..").screenshot(path=out + "/10-daily.png")

            # --- mobile + dark views of the new sections
            ctx4 = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, locale="th-TH", timezone_id="Asia/Bangkok")
            pg4 = ctx4.new_page()
            pg4.on("pageerror", lambda e: errors.append(str(e)))
            pg4.goto(base + "/")
            pg4.wait_for_selector(".lcard .pct")
            time.sleep(1.5)
            pg4.locator(".lcard[data-n='3'] details.ld summary").nth(1).click()
            time.sleep(1.2)
            shot(pg4, pg4.locator("#sec-life"), out + "/16-mobile-lifecycle.png")
            shot(pg4, pg4.locator("#sec-errors"), out + "/17-mobile-errors.png")
            print("mobile horizontal overflow px (full page):", pg4.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth"))
            ctx4.close()
            ctx5 = br.new_context(viewport={"width": 1280, "height": 900}, locale="th-TH", timezone_id="Asia/Bangkok", color_scheme="dark")
            pg5 = ctx5.new_page()
            pg5.on("pageerror", lambda e: errors.append(str(e)))
            pg5.goto(base + "/")
            pg5.wait_for_selector(".lcard .pct")
            pg5.locator(".lcard[data-n='3'] details.ld summary").nth(1).click()
            time.sleep(1.5)
            shot(pg5, pg5.locator("#sec-life"), out + "/18-dark-lifecycle.png")
            ctx5.close()

            # --- hub unreachable (stop the HTTP server only)
            errors.clear()
            pg.evaluate('window.scrollTo(0,0)')
            hub._server.should_exit = True
            hub._http_thread.join(5)
            time.sleep(7)
            pg.screenshot(path=out + "/08-hub-unreachable.png", full_page=False)
            print("08 hub unreachable")
            br.close()
    finally:
        fleet.stop()
        hub.stop()
        cloud.stop()
        broker.stop()
    print("console/page errors:", errors if errors else "none")
    print("cloud: heartbeats=%d events=%s bad_sig=%d" % (len(cloud.heartbeats), cloud.event_types(), cloud.bad_sig))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
