"""Real local-account cookie client for existing isolated HTTP regression tests."""
import http.cookiejar
import json
import urllib.error
import urllib.request


class LocalAccountClient:
    def __init__(self, base):
        self.base = base
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.csrf = "1"
        status, account = self.request("/auth/signup", {
            "channel":"local", "username":"regression", "phone":"0812345678",
            "full_name":"Regression Tester", "role":"entrepreneur",
            "password":"synthetic-regression-password", "confirm_password":"synthetic-regression-password"}, "POST")
        assert status == 200, (status, account)
        self.csrf = account["csrf_token"]

    def request(self, path, body=None, method="GET", headers=None, authenticated=True):
        request = urllib.request.Request(self.base+path, method=method,
            data=json.dumps(body or {}).encode() if method != "GET" else None,
            headers={"Content-Type":"application/json", "Origin":self.base,
                     "X-GG-CSRF":self.csrf if authenticated else "1", **(headers or {})})
        opener = self.opener if authenticated else urllib.request.build_opener()
        try:
            response = opener.open(request, timeout=5)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            return response.status, json.loads(response.read() or b"null")
