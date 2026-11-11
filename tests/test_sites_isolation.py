"""Two-site security/integration regression: synthetic fixtures, no Pi or MQTT."""
import gc
import hashlib
import json
import secrets
import sqlite3
import threading
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from grainguard_hub.app import Hub
from grainguard_hub import sdnotify
from grainguard_hub.auth import AuthStore,OnlineOnlyApp,ITERATIONS,install_auth
from grainguard_hub.config import Config
from grainguard_hub.sites import SiteRuntime,REAL_SITE,MOCK_SITE,MOCK_MACS


PASSWORD="synthetic-test-owner-password"
REAL_MAC="a4cf12bbccdd"


def post(client,path,body=None,csrf="1",headers=None):
    return client.post(path,json=body or {},headers={"Origin":str(client.base_url).rstrip("/"),"X-GG-CSRF":csrf,**(headers or {})})


def login(client,username,channel):
    response=post(client,"/auth/login",{"identifier":username,"password":PASSWORD,"channel":channel})
    assert response.status_code==200,response.text
    return response.json()


@pytest.fixture
def sites(tmp_path):
    cfg=Config(data_dir=str(tmp_path/"real"),mqtt_enabled=False,admin_token=secrets.token_urlsafe(32),cloud_url="")
    real=Hub(cfg,mqtt_enabled=False,http_enabled=False)
    real.engine.assign(2,REAL_MAC,"REAL demo slot 2")
    (tmp_path/"real"/"dashboard-config.json").write_text(json.dumps({"visible_slots":[2],"discovery":"review","offline":"keep"}))
    now=time.time()
    for age in (60,30,0):
        real.engine.on_tele(REAL_MAC,{"v":1,"seq":int(now-age),"up":int(now-age),"st":"RUN","mode":"SHADOW","env":150.,"base":150.,"ratio":1.,"act":90,"sat":0,"flat":0,"vin":24.,"tc":38.},now-age)
    real.store.flush_tele()
    real.engine._event(now,2,REAL_MAC,"HEALTH","REAL private history",{"real":True})
    runtime=SiteRuntime(real)
    runtime.feed_once()
    store=runtime.auth_store
    real_id=store.provision_site_owner("pumpkintec",PASSWORD,"PumpkinTec",REAL_SITE)
    mock_id=store.provision_site_owner("uengliangseng",PASSWORD,"โรงสีไฟอึ้งเลี่ยงเส็ง",MOCK_SITE)
    clients=[]
    def client(online=False):
        result=TestClient(OnlineOnlyApp(runtime.app) if online else runtime.app,base_url="http://localhost",client=("127.0.0.1",123))
        clients.append(result)
        return result
    yield runtime,client,real_id,mock_id
    for c in clients:c.close()
    runtime.stop()
    clients.clear()
    gc.collect()


def test_no_phone_owners_dual_channels_and_session_coexistence(sites):
    runtime,make,_,_=sites
    for username,sid,name,count in (("pumpkintec",REAL_SITE,"PumpkinTec",1),("uengliangseng",MOCK_SITE,"โรงสีไฟอึ้งเลี่ยงเส็ง",6)):
        local,online=make(),make(True)
        a=login(local,username,"local")
        b=login(online,username,"online")
        assert a["user"]["phone"] is None and b["user"]["id"]==a["user"]["id"]
        assert a["access"]=="admin" and b["access"]=="approved"
        assert a["site"]=={"id":sid,"name":name,"mode":"live" if sid==REAL_SITE else "mock","machine_count":count}
        assert local.get("/auth/session").json()["authenticated"]
        assert online.get("/api/nodes").status_code==200
        assert post(online,"/local-api/config",{"visible_slots":[]},b["csrf_token"]).status_code==403
        assert local.get("/auth/session").json()["access"]=="admin"
        tampered=make()
        tampered.cookies.set("gg_local_session",online.cookies.get("gg_online_session"))
        assert tampered.get("/api/nodes").status_code==401


def test_all_data_families_are_routed_and_mock_edits_never_touch_real(sites):
    runtime,make,_,_=sites
    real,mock=make(),make()
    r=login(real,"pumpkintec","local")
    m=login(mock,"uengliangseng","local")
    realnodes=real.get("/api/nodes").json()
    mocknodes=mock.get("/api/nodes").json()
    assert sum(bool(n["mac"]) for n in realnodes["nodes"])==1
    assert sum(bool(n["mac"]) for n in mocknodes["nodes"])==6
    assert {n["mac"] for n in mocknodes["nodes"]}==set(MOCK_MACS)
    mock_by_slot={n["n"]:n for n in mocknodes["nodes"]}
    assert [mock_by_slot[n]["state"] for n in range(1,6)]==["RUN","ALARM","REST","CAL","FAULT"]
    assert [mock_by_slot[n]["cls"] for n in (2,4,5,6)]==["alarm","cal","warn","offline"]
    assert real.get("/local-api/config").json()["visible_slots"]==[2]
    assert mock.get("/local-api/config").json()["visible_slots"]==list(range(1,7))
    for family in ("/api/events","/api/errors","/api/lifecycle","/api/node/2/history","/api/daily"):
        rtext=real.get(family).text
        mtext=mock.get(family).text
        assert "MOCK" not in rtext,family
        assert "REAL private history" not in mtext and REAL_MAC not in mtext,family
    assert "REAL private history" in real.get("/api/events").text
    assert "MOCK:" in mock.get("/api/events").text
    before=list(runtime.real_hub.store.list_nodes())
    before_config=real.get("/local-api/config").json()
    assert post(mock,"/local-api/config",{"visible_slots":[1,3]},m["csrf_token"]).status_code==200
    assert post(mock,"/api/node/1/assign",{"mac":MOCK_MACS[0],"label":"MOCK edited"},m["csrf_token"]).status_code==200
    assert post(mock,"/api/lifecycle/1/change",{"reason":"scheduled","note":"MOCK replacement"},m["csrf_token"]).status_code==200
    assert "MOCK replacement" not in real.get("/api/lifecycle").text
    assert list(runtime.real_hub.store.list_nodes())==before
    assert real.get("/local-api/config").json()==before_config
    assert runtime.mock_hub.cfg.data_dir!=runtime.real_hub.cfg.data_dir
    assert not runtime.mock_hub.cfg.mqtt_enabled and not runtime.mock_hub.cfg.cloud_url
    assert runtime.mock_hub.mqtt is None and not runtime.mock_hub.send_cmd(REAL_MAC,{"cmd":"ack"})


def test_cross_site_ids_codes_scope_headers_and_cookie_tamper(sites):
    runtime,make,_,_=sites
    real,mock,viewer=make(),make(),make(True)
    a=login(real,"pumpkintec","local")
    b=login(mock,"uengliangseng","local")
    real_code=real.get("/auth/access").json()["code"]
    mock_code=mock.get("/auth/access").json()["code"]
    assert real_code!=mock_code
    signed=post(viewer,"/auth/signup",{"channel":"online","username":"viewer","phone":"0812345678","full_name":"Remote Viewer","role":"employee","password":PASSWORD,"confirm_password":PASSWORD,"site_id":REAL_SITE})
    assert signed.status_code==200 and signed.json()["site"] is None
    v=signed.json()
    joined=post(viewer,"/auth/join",{"code":mock_code,"site_id":REAL_SITE},v["csrf_token"])
    assert joined.json()["site"]["id"]==MOCK_SITE and joined.json()["access"]=="pending"
    uid=v["user"]["id"]
    assert real.get("/auth/access").json()["users"]==[]
    assert post(real,f"/auth/access/{uid}/approve",csrf=a["csrf_token"]).status_code==404
    assert post(mock,f"/auth/access/{uid}/approve",csrf=b["csrf_token"]).status_code==200
    assert {n["mac"] for n in viewer.get("/api/nodes?site=pumpkintec",headers={"X-Site-ID":REAL_SITE}).json()["nodes"]}==set(MOCK_MACS)
    assert post(viewer,"/auth/join",{"code":real_code},v["csrf_token"]).status_code==409
    assert post(real,"/auth/code/rotate",csrf=a["csrf_token"]).status_code==200
    assert viewer.get("/api/nodes").status_code==200
    assert post(mock,f"/auth/access/{uid}/revoke",csrf=b["csrf_token"]).status_code==200
    assert viewer.get("/api/events").status_code==403
    viewer.cookies.set("gg_online_session","forged-site-pumpkintec")
    assert viewer.get("/api/nodes").status_code==401
    # Even accidental dispatch directly to the wrong API app fails closed.
    direct=TestClient(runtime.apps[REAL_SITE],base_url="http://localhost",client=("127.0.0.1",123))
    direct.cookies.update(mock.cookies)
    assert direct.get("/api/nodes").status_code==403
    direct.close()


def test_legacy_migration_retains_phone_hash_data_and_real_code(tmp_path,monkeypatch):
    path=tmp_path/"accounts.sqlite3"
    salt="11"*16
    password_hash=hashlib.pbkdf2_hmac("sha256",PASSWORD.encode(),bytes.fromhex(salt),ITERATIONS).hex()
    with sqlite3.connect(path) as db:
        db.executescript("""
        CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT UNIQUE NOT NULL,phone TEXT UNIQUE NOT NULL,
          full_name TEXT NOT NULL,role TEXT NOT NULL,salt TEXT NOT NULL,password TEXT NOT NULL,
          account_channel TEXT NOT NULL,access TEXT NOT NULL,last_seen REAL NOT NULL DEFAULT 0,monitoring REAL NOT NULL DEFAULT 0);
        CREATE TABLE sessions(token TEXT PRIMARY KEY,user_id INTEGER NOT NULL,csrf TEXT NOT NULL,channel TEXT NOT NULL,expires REAL NOT NULL);
        CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        INSERT INTO users VALUES(7,'legacy','0811111111','Legacy Person','entrepreneur','saved-salt','saved-hash','local','admin',1,2);
        INSERT INTO users VALUES(8,'reader','0822222222','Reader Person','employee','reader-salt','reader-hash','online','pending',3,4);
        INSERT INTO sessions VALUES('oldglobal',7,'csrf','local',9999999999);
        INSERT INTO meta VALUES('invite_code','legacy-random-code-for-test');
        """)
        db.execute("UPDATE users SET salt=?,password=? WHERE id=7",(salt,password_hash))
    migrate=AuthStore._migrate_sites
    def fail_after_migration(self,db):
        migrate(self,db)
        raise RuntimeError("synthetic migration interruption")
    with monkeypatch.context() as patch:
        patch.setattr(AuthStore,"_migrate_sites",fail_after_migration)
        with pytest.raises(RuntimeError,match="synthetic migration interruption"):
            AuthStore(str(tmp_path))
    with sqlite3.connect(path) as db:
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='sites'").fetchone()
        assert db.execute("SELECT account_channel FROM users WHERE id=7").fetchone()[0]=="local"
        assert db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]==1
    store=AuthStore(str(tmp_path))
    with store.db() as db:
        user=db.execute("SELECT * FROM users WHERE id=7").fetchone()
        assert user["phone"]=="0811111111" and user["password"]==password_hash and user["salt"]==salt
        assert user["account_channel"]=="local"
        assert db.execute("SELECT online_access FROM memberships WHERE user_id=7 AND site_id=?",(REAL_SITE,)).fetchone()[0]=="unlinked"
        assert db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]==0
        assert db.execute("SELECT invite_code FROM sites WHERE id=?",(REAL_SITE,)).fetchone()[0]=="legacy-random-code-for-test"
        assert db.execute("SELECT online_access FROM memberships WHERE user_id=8 AND site_id=?",(REAL_SITE,)).fetchone()[0]=="pending"
        assert not db.execute("PRAGMA table_info(users)").fetchall()[2]["notnull"]
    app=FastAPI()
    install_auth(app,Config(data_dir=str(tmp_path)),auth_store=store)
    with TestClient(app,base_url="http://localhost",client=("127.0.0.1",123)) as local, TestClient(OnlineOnlyApp(app),base_url="http://localhost",client=("127.0.0.1",123)) as online:
        assert login(local,"legacy","local")["access"]=="admin"
        assert post(online,"/auth/login",{"identifier":"legacy","password":PASSWORD,"channel":"online"}).status_code==401
    uid=store.provision_site_owner("uengliangseng",PASSWORD,"โรงสีไฟอึ้งเลี่ยงเส็ง",MOCK_SITE)
    again=AuthStore(str(tmp_path))
    with again.db() as db:
        assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0]==3
        assert db.execute("SELECT phone FROM users WHERE id=?",(uid,)).fetchone()[0] is None
        assert db.execute("SELECT COUNT(*) FROM memberships WHERE user_id=? AND site_id=?",(uid,MOCK_SITE)).fetchone()[0]==1


def test_restart_persists_mock_edits_but_keeps_real_unchanged(sites):
    runtime,make,_,_=sites
    client=make()
    dto=login(client,"uengliangseng","local")
    assert post(client,"/local-api/config",{"visible_slots":[2,4]},dto["csrf_token"]).status_code==200
    cfg=runtime.real_hub.cfg
    runtime.stop()
    reopened=SiteRuntime(Hub(cfg,mqtt_enabled=False,http_enabled=False))
    try:
        reopened.start()
        with TestClient(reopened.app,base_url="http://localhost",client=("127.0.0.1",123)) as restored:
            restored.cookies.update(client.cookies)
            assert restored.get("/local-api/config").json()["visible_slots"]==[2,4]
            assert {n["mac"] for n in restored.get("/api/nodes").json()["nodes"]}==set(MOCK_MACS)
            login(restored,"pumpkintec","local")
            assert restored.get("/local-api/config").json()["visible_slots"]==[2]
            assert [n["mac"] for n in restored.get("/api/nodes").json()["nodes"] if n["mac"]]==[REAL_MAC]
    finally:
        reopened.stop()


def test_only_live_hub_notifies_systemd(sites,monkeypatch):
    runtime,_,_,_=sites
    notes=[]
    monkeypatch.setattr(sdnotify,"notify",lambda value:notes.append((value,threading.current_thread())))
    monkeypatch.setattr(sdnotify,"watchdog_interval",lambda:0.001)
    runtime.start()
    try:
        deadline=time.monotonic()+2
        while not any(value=="WATCHDOG=1" for value,_ in notes) and time.monotonic()<deadline:
            time.sleep(.01)
    finally:
        runtime.stop()
    assert [value for value,_ in notes].count("READY=1")==1
    assert [value for value,_ in notes].count("STOPPING=1")==1
    watchdog_threads=[thread for value,thread in notes if value=="WATCHDOG=1"]
    assert watchdog_threads and all(thread is runtime.real_hub._tick_thread for thread in watchdog_threads)
