"""Isolated trial: one real Hub backend, no MQTT or Pi connection, two channels."""
from __future__ import annotations
import argparse
import asyncio
import json
import math
from pathlib import Path
import secrets
import sys
import threading
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'hub-core'))
from grainguard_hub.app import Hub
from grainguard_hub.sites import SiteRuntime
from grainguard_hub.listeners import serve
from grainguard_hub.config import Config


def make_review(data_dir: Path):
    cfg = Config(data_dir=str(data_dir), mqtt_enabled=False, cloud_url='',
                 dashboard_path=str(ROOT / 'dashboard/index.html'),
                 hub_id='TEST — OFFLINE REVIEW', admin_token=secrets.token_urlsafe(32))
    hub = Hub(cfg, http_enabled=False)
    mac = '020000000001'
    if not hub.engine.slot_mac(1):
        hub.engine.assign(1, mac, label='TEST Node 1')
    def feed():
        seq = 0
        while not hub._stop.is_set():
            now = time.time()
            value = 1.04 + .07 * math.sin(now/9)
            frame = {'v':1,'seq':seq,'up':100+seq,'st':'RUN','mode':'SHADOW',
                     'env':150*value,'base':150.,'ratio':value,'act':90.,'sat':0,'flat':0,
                     'vin':24.1,'tc':37.2,'fw':'TEST-ONLY','ack':0,'tl':{'r':0,'y':0,'g':1,'b':1},
                     'rst':1,'link':100}
            hub.engine.on_tele(mac, frame, now)
            seq += 1
            hub._stop.wait(1)
    runtime=SiteRuntime(hub)
    runtime.start()
    threading.Thread(target=feed, name='synthetic-test-node', daemon=True).start()
    # Trial marker is injected only in the review launcher, never into production assets.
    from starlette.responses import HTMLResponse
    async def trial_index(request):
        html = (ROOT/'dashboard/index.html').read_text(encoding='utf-8')
        banner = '<div id="offline-fixture-banner" role="status" style="padding:5px 12px;background:#fff3d9;color:#68420d;text-align:center">ข้อมูลตัวอย่าง · TEST DATA · ไม่ได้เชื่อม Pi4</div>'
        return HTMLResponse(html.replace('<body>', '<body>'+banner))
    # Starlette route wraps this endpoint while middleware still gates the index.
    from starlette.routing import request_response
    for site_app in runtime.apps.values():
        original=next(r for r in site_app.routes if getattr(r,'path',None)=='/')
        original.app=request_response(trial_index)
    return runtime, runtime.app


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--local-port',type=int,default=8766)
    parser.add_argument('--online-port',type=int,default=8767)
    parser.add_argument('--data-dir',type=Path,default=ROOT/'user-trial-data')
    args=parser.parse_args()
    hub,app=make_review(args.data_dir)
    print(f'LOCAL: http://127.0.0.1:{args.local_port}/login/local.html',flush=True)
    print(f'ONLINE SIMULATION: http://127.0.0.1:{args.online_port}/login/online.html',flush=True)
    print('Synthetic isolated data. No network connection to the Pi or MQTT.',flush=True)
    try: asyncio.run(serve(app,args.local_port,args.online_port))
    finally: hub.stop()

if __name__=='__main__': main()
