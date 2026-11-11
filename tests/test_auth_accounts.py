"""Account authorization tests, synthetic ASGI requests; never contact Pi."""
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hub-core"))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from grainguard_hub.auth import OnlineOnlyApp, install_auth


class AccountsTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.app = FastAPI()
        install_auth(self.app, SimpleNamespace(data_dir=self.directory.name))
        self.app.get("/api/nodes")(lambda: {"nodes": []})
        self.app.get("/api/health")(lambda: {"ok": True})
        self.app.get("/local-api/config")(lambda: {"visible_slots": [1]})
        self.app.post("/api/command")(lambda: {"sent": True})
        self.local = TestClient(self.app, base_url="http://localhost", client=("127.0.0.1", 1234))
        self.online = TestClient(OnlineOnlyApp(self.app), base_url="http://localhost", client=("127.0.0.1", 1234))

    def tearDown(self):
        self.local.close()
        self.online.close()
        self.directory.cleanup()

    def post(self, client, path, data=None, token=None, **kwargs):
        return client.post(path, json=data or {}, headers={"Origin": "http://localhost", "X-GG-CSRF": token or "1", **kwargs})

    def signup(self, client, mode, username="owner", phone="0812345678"):
        response = self.post(client, "/auth/signup", {"channel": mode, "username": username, "phone": phone,
            "full_name": "Test Person", "role": "entrepreneur", "password": "strong-password-1", "confirm_password": "strong-password-1"})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_complete_approval_revoke_rotation(self):
        admin = self.signup(self.local, "local")
        code = self.local.get("/auth/access").json()["code"]
        online = self.signup(self.online, "online", "remote", "0812345679")
        csrf = online["csrf_token"]
        self.assertEqual(self.online.get("/api/nodes").status_code, 403)
        self.assertEqual(self.post(self.online,"/auth/join",{"code":code},csrf).json()["access"], "pending")
        uid = online["user"]["id"]
        self.assertEqual(self.online.get("/api/nodes").status_code, 403)
        self.assertEqual(self.post(self.local,f"/auth/access/{uid}/approve",token=admin["csrf_token"]).status_code,200)
        self.assertEqual(self.online.get("/api/nodes").status_code,200)
        self.assertTrue(self.local.get("/auth/access").json()["users"][0]["monitoring"])
        self.assertEqual(self.post(self.online,"/api/command",token=csrf).status_code,403)
        self.assertEqual(self.post(self.online,"/api/command",token=csrf,**{"X-Admin-Token":"ignored-legacy-token"}).status_code,403)
        self.assertEqual(self.online.get("/auth/access").status_code,403)
        self.assertEqual(self.post(self.local,f"/auth/access/{uid}/revoke",token=admin["csrf_token"]).status_code,200)
        for path in ("/api/nodes","/api/health","/local-api/config"):
            self.assertEqual(self.online.get(path).status_code,403)
        self.assertEqual(self.post(self.online,"/auth/join",{"code":code},csrf).status_code,403)
        rotated = self.post(self.local,"/auth/code/rotate",token=admin["csrf_token"])
        self.assertNotEqual(rotated.json()["code"],code)
        self.assertEqual(self.post(self.local,"/api/command",token=admin["csrf_token"]).status_code,200)

    def test_no_public_diagnostics_or_forged_local(self):
        for path in ("/api/nodes","/api/health","/local-api/config"):
            self.assertEqual(self.online.get(path).status_code,401)
        bad = self.post(self.online,"/auth/signup",{"channel":"local"},**{"X-Forwarded-For":"127.0.0.1"})
        self.assertEqual(bad.status_code,403)
        admin = self.signup(self.local,"local")
        self.online.cookies.update(self.local.cookies)
        self.assertEqual(self.online.get("/api/nodes").status_code,401)
        self.assertEqual(self.post(self.online,"/api/command",token=admin["csrf_token"]).status_code,403)

    def test_csrf_body_validation_and_logout(self):
        self.assertEqual(self.local.post("/auth/signup",json={}).status_code,403)
        self.assertEqual(self.local.post("/auth/signup",json={},headers={"Origin":"http://evil","X-GG-CSRF":"1"}).status_code,403)
        self.assertEqual(self.local.post("/auth/signup",content="x"*16385,headers={"Origin":"http://localhost","X-GG-CSRF":"1"}).status_code,413)
        self.assertEqual(self.post(self.local,"/auth/signup",{"channel":"local"}).status_code,422)
        admin = self.signup(self.local,"local")
        self.assertEqual(self.post(self.local,"/auth/logout").status_code,403)
        self.assertEqual(self.post(self.local,"/auth/logout",token=admin["csrf_token"]).status_code,200)
        self.assertFalse(self.local.get("/auth/session").json()["authenticated"])

    def test_login_phone_and_throttle(self):
        self.signup(self.local,"local")
        logged = self.post(self.local,"/auth/login",{"channel":"local","identifier":"+66812345678","password":"strong-password-1"})
        self.assertEqual(logged.status_code,200)
        for i in range(9):
            self.assertEqual(self.post(self.local,"/auth/login",{"channel":"local","identifier":"owner","password":"bad"}).status_code,401)
        self.assertEqual(self.post(self.local,"/auth/login",{"channel":"local","identifier":"owner","password":"bad"}).status_code,429)

    def test_bootstrap_gate_restart_and_pending_rotation(self):
        admin = self.signup(self.local,"local")
        online = self.signup(self.online,"online","reader","0812345679")
        code = self.local.get("/auth/access").json()["code"]
        self.post(self.online,"/auth/join",{"code":code},online["csrf_token"])
        self.post(self.local,"/auth/code/rotate",token=admin["csrf_token"])
        self.assertEqual(self.online.get("/auth/session").json()["access"],"unlinked")
        self.assertEqual(self.post(self.online,"/auth/join",{"code":"รหัสไม่ถูกต้อง"},online["csrf_token"]).status_code,400)
        self.assertEqual(self.post(self.local,"/auth/logout",token=admin["csrf_token"]).status_code,200)
        body = {"channel":"local","username":"other","phone":"0812345680","full_name":"Other Owner",
                "role":"employee","password":"another-password","confirm_password":"another-password"}
        self.assertEqual(self.post(self.local,"/auth/signup",body).status_code,401)
        from grainguard_hub.auth import AuthStore
        reopened = AuthStore(self.directory.name)
        with reopened.db() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM users").fetchone()[0],2)

    def test_dns_rebinding_and_wrong_listener(self):
        bad = TestClient(self.app,base_url="http://evil.example",client=("127.0.0.1",123))
        response = bad.post("/auth/signup",json={"channel":"local"},headers={"Origin":"http://evil.example","X-GG-CSRF":"1"})
        self.assertEqual(response.status_code,403)
        self.assertEqual(self.post(self.local,"/auth/signup",{"channel":"online"}).status_code,403)
        self.assertEqual(self.local.get("/",follow_redirects=False).headers["location"],"/login/local.html")
        self.assertEqual(self.online.get("/",follow_redirects=False).headers["location"],"/login/online.html")
        bad.close()


if __name__ == "__main__":
    unittest.main()
