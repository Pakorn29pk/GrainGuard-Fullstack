"""Authoritative per-session site routing and isolated six-machine simulation."""
from __future__ import annotations

import dataclasses
import json
import math
import os
import secrets
import threading
import time

from fastapi import Request

from .api import create_app
from .app import Hub
from .auth import AuthStore

REAL_SITE="pumpkintec"
MOCK_SITE="uengliangseng"
MOCK_MACS=tuple("0200aabb%04x" % n for n in range(1,7))


def mock_data_dir(real_cfg):
    """Reject accidental links that could send mock writes into real storage."""
    real_dir=os.path.realpath(real_cfg.data_dir)
    path=os.path.join(real_dir,"mock-mill")
    if os.path.islink(path):
        raise ValueError("Mock data directory must not be a symbolic link")
    pairs=((real_cfg.db(),"grainguard.db"),
           (os.path.join(real_dir,"dashboard-config.json"),"dashboard-config.json"))
    for live,filename in pairs:
        candidate=os.path.join(path,filename)
        if os.path.islink(candidate) or os.path.realpath(live)==os.path.realpath(candidate) or (
                os.path.exists(live) and os.path.exists(candidate) and os.path.samefile(live,candidate)):
            raise ValueError("Mock storage must be separate from live storage")
    return path


class SiteRouter:
    """HTTP parameters cannot choose a tenant; only a validated session can."""
    def __init__(self,auth_store,apps):
        self.auth_store,self.apps=auth_store,dict(apps)

    async def __call__(self,scope,receive,send):
        if scope["type"]!="http":
            return await self.apps[REAL_SITE](scope,receive,send)
        session=self.auth_store.session(Request(scope))
        site_id=session["site_id"] if session and session["site_id"] in self.apps else REAL_SITE
        # Scope is supplied by the server, never from tenant headers or paths.
        await self.apps[site_id](dict(scope,gg_site=site_id),receive,send)


def close_hub(hub):
    """Also clean resources when startup failed before Hub.started was set."""
    if hub.started:
        hub.stop()
        return
    hub.request_stop()
    if hub.mqtt:
        hub.mqtt.stop()
    hub.uplink.stop(flush_s=0)
    if hub._tick_thread and hub._tick_thread.is_alive():
        hub._tick_thread.join(timeout=5)
    hub.store.close()


class SiteRuntime:
    def __init__(self,real_hub):
        self.real_hub=real_hub
        self.mock_hub=None
        self._feed_thread=None
        self._closed=False
        self._mock_seq=0
        try:
            self.auth_store=AuthStore(real_hub.cfg.data_dir)
            cfg=dataclasses.replace(real_hub.cfg,
                data_dir=mock_data_dir(real_hub.cfg),db_path="",
                mqtt_enabled=False,mqtt_user="",mqtt_pass="",cloud_url="",cloud_secret="",
                hub_id="MOCK-uengliangseng",nic_a="",nic_b="",power_hours="",
                expected_fw="MOCK-SIMULATION",cal_stuck_s=31_536_000.0,
                admin_token=secrets.token_urlsafe(32))
            self.mock_hub=Hub(cfg,mqtt_enabled=False,http_enabled=False,notify_systemd=False)
            self.mock_hub.cpu_temp=lambda:37.0
            self.mock_hub.selfcheck.disk_fn=lambda:10.0
            self.mock_hub.selfcheck.ntp_fn=lambda:None
            self.mock_hub.selfcheck.cpu_fn=lambda:37.0
            # A simulation can never send commands to the real MQTT bridge.
            self.mock_hub.send_cmd=lambda *_args,**_kwargs:False
            self._seed_mock()
            self.apps={REAL_SITE:create_app(real_hub,self.auth_store,REAL_SITE),
                       MOCK_SITE:create_app(self.mock_hub,self.auth_store,MOCK_SITE)}
            self.app=SiteRouter(self.auth_store,self.apps)
        except BaseException:
            if self.mock_hub is not None:
                close_hub(self.mock_hub)
            raise

    def _seed_mock(self):
        hub=self.mock_hub
        if hub.store.meta_get("mock_seed_v1"):
            return
        for n,mac in enumerate(MOCK_MACS,1):
            hub.engine.assign(n,mac,"MOCK เครื่องขัด %d"%n)
        config={"visible_slots":list(range(1,7)),"discovery":"review","offline":"keep"}
        path=os.path.join(hub.cfg.data_dir,"dashboard-config.json")
        # Fresh simulation directory only; primary config is never opened here.
        with open(path,"w",encoding="utf-8") as fh:
            json.dump(config,fh)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(path,0o600)
        now=time.time()
        for age in (60,45,30,15):
            self.feed_once(now-age,include_offline=True)
        hub.store.flush_tele()
        for n,mac in enumerate(MOCK_MACS,1):
            hub.engine._event(now-10,n,mac,"HEALTH","MOCK: ข้อมูลจำลองเครื่อง %d"%n,{"mock":True},src="simulation")
        hub.store.meta_set("mock_seed_v1","1")

    def feed_once(self,now=None,include_offline=False):
        hub=self.mock_hub
        now=time.time() if now is None else now
        self._mock_seq+=1
        states=("RUN","ALARM","REST","CAL","FAULT","RUN")
        for n,mac in enumerate(MOCK_MACS,1):
            if n==6 and not include_offline:
                continue
            value=1.05+.06*math.sin(now/9+n)
            if n==2:value=2.1+.05*math.sin(now/5)
            timestamp=now-60 if n==6 else now
            frame={"v":1,"seq":self._mock_seq,"up":self._mock_seq*2,"st":states[n-1],"mode":"SHADOW" if n==4 else "ALARM_ON",
                "env":150*value,"base":150.,"ratio":value,"act":90.,"sat":0,"flat":0,
                "vin":24.1,"tc":37.2,"fw":"MOCK-SIMULATION","ack":0,"fa":int(n==5),
                "tl":{"r":int(n==2),"y":int(n in(4,5)),"g":int(n in(1,3)),"b":1},"rst":1,"link":100}
            hub.engine.on_tele(mac,frame,timestamp)
        hub.engine.tick(now)

    def start(self):
        try:
            self.real_hub.start()
            self.mock_hub.start()
            self.feed_once()
            def feed():
                while not self.mock_hub._stop.wait(2):
                    self.feed_once()
            self._feed_thread=threading.Thread(target=feed,name="mock-six-machines",daemon=True)
            self._feed_thread.start()
        except BaseException:
            self.stop()
            raise

    def stop(self):
        if self._closed:
            return
        self._closed=True
        # Stop synthetic feeder before closing its database.
        self.mock_hub.request_stop()
        if self._feed_thread and self._feed_thread.is_alive():
            self._feed_thread.join(timeout=5)
        close_hub(self.mock_hub)
        close_hub(self.real_hub)
