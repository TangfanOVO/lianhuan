"""公开页面与本机服务的安全边界：供应链、属性注入、CSRF、回环票。"""
import asyncio
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class _OneTag(HTMLParser):
    attrs = []

    def handle_starttag(self, _tag, attrs):
        self.attrs = attrs


def _request(method="GET", path="/", *, headers=(), body=b"", client="127.0.0.1"):
    from core.server import app

    out = {}

    async def go():
        raw_headers = [(b"host", b"lianhuan.test")]
        raw_headers += [(k.lower().encode(), v.encode()) for k, v in headers]
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                 "method": method, "scheme": "http", "path": path,
                 "raw_path": path.encode(), "query_string": b"", "root_path": "",
                 "headers": raw_headers, "client": (client, 1), "server": ("lianhuan.test", 80)}
        got = [{"type": "http.request", "body": body, "more_body": False}]

        async def receive():
            return got.pop(0) if got else {"type": "http.disconnect"}

        async def send(message):
            if message["type"] == "http.response.start":
                out["status"] = message["status"]
                out["headers"] = [(k.decode().lower(), v.decode()) for k, v in message["headers"]]
            elif message["type"] == "http.response.body":
                out["body"] = out.get("body", b"") + message.get("body", b"")

        await app(scope, receive, send)

    asyncio.run(go())
    return out


class TestPageSupplyChainAndEscaping(unittest.TestCase):
    def test_p5_is_vendored_and_pinned(self):
        expected = "00a532c56e785c68d7c7bb6f9a084e2c856b71527f22c3260aff4a2f582d80c9"
        p5 = ROOT / "core" / "web" / "vendor" / "p5-1.9.4.min.js"
        self.assertEqual(expected, hashlib.sha256(p5.read_bytes()).hexdigest())
        pages = [
            page
            for page in (ROOT / "app" / "index.html", ROOT / "core" / "web" / "index.html")
            if page.exists()
        ]
        self.assertTrue(pages)
        for page in pages:
            text = page.read_text(encoding="utf-8")
            self.assertIn("/vendor/p5-1.9.4.min.js", text)
            self.assertNotIn("cdnjs.cloudflare.com", text)

    @unittest.skipUnless(shutil.which("node"), "需要 node 执行页面自己的转义函数")
    def test_quote_payload_does_not_create_an_event_attribute(self):
        source_page = ROOT / "app" / "index.html"
        if not source_page.exists():
            source_page = ROOT / "core" / "web" / "index.html"
        page = source_page.read_text(encoding="utf-8")
        match = re.search(r"const W = \(function\(\)\{\n(.*?)\n  const WK", page, re.S)
        self.assertIsNotNone(match)
        payload = 'x" onerror="window.__x=1'
        single = "x' autofocus='autofocus"
        script = match.group(1) + "\nconsole.log(JSON.stringify({" \
            + f'double:`<img src="${{esc({json.dumps(payload)})}}">`,' \
            + f"single:`<input value='${{esc({json.dumps(single)})}}'>`," \
            + "bad:url('javascript:alert(1)'), good:url('/files/picture.png')}));"
        value = json.loads(subprocess.check_output(["node", "-e", script], text=True))
        for key, forbidden in (("double", "onerror"), ("single", "autofocus")):
            parser = _OneTag(); parser.feed(value[key])
            attrs = dict(parser.attrs)
            self.assertNotIn(forbidden, attrs)
            self.assertEqual(1, len(attrs))
        self.assertEqual("", value["bad"])
        self.assertEqual("/files/picture.png", value["good"])


class TestHttpBoundary(unittest.TestCase):
    def setUp(self):
        from core import gate
        self.gate = gate
        self.old_env = {k: os.environ.get(k) for k in (
            "LIANHUAN_DB", "LIANHUAN_ANDROID_TOKEN", "LIANHUAN_COOKIE_SECURE",
            "LIANHUAN_TRUSTED_PROXIES", "LIANHUAN_ALLOW_LOCAL_COMMANDS")}
        os.environ["LIANHUAN_DB"] = str(pathlib.Path(tempfile.mkdtemp()) / "gate.db")
        for key in self.old_env:
            if key != "LIANHUAN_DB":
                os.environ.pop(key, None)
        gate._state.update(on=False, token="")
        gate._fails.clear()

    def tearDown(self):
        self.gate._state.update(on=False, token="")
        self.gate._fails.clear()
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_security_headers_cover_the_normal_page(self):
        out = _request()
        headers = dict(out["headers"])
        self.assertEqual(200, out["status"])
        self.assertIn("script-src-attr 'none'", headers["content-security-policy"])
        self.assertEqual("nosniff", headers["x-content-type-options"])
        self.assertEqual("DENY", headers["x-frame-options"])
        self.assertEqual("no-referrer", headers["referrer-policy"])

    def test_cross_site_and_text_plain_writes_are_rejected(self):
        body = json.dumps({"content": "should-not-land"}).encode()
        cross = _request("POST", "/api/memories", body=body, headers=(
            ("content-type", "application/json"), ("origin", "https://evil.invalid")))
        self.assertEqual(403, cross["status"])
        plain = _request("POST", "/api/memories", body=body, headers=(
            ("content-type", "text/plain"), ("origin", "http://lianhuan.test")))
        self.assertEqual(415, plain["status"])

    def test_armed_gate_never_bypasses_loopback_and_secure_cookie_is_set(self):
        self.gate.arm("a-long-enough-passphrase")
        self.assertEqual(401, _request(path="/api/memories")["status"])
        os.environ["LIANHUAN_COOKIE_SECURE"] = "1"
        login = _request("POST", "/api/login", body=json.dumps(
            {"password": "a-long-enough-passphrase"}).encode(),
            headers=(("content-type", "application/json"),))
        self.assertEqual(200, login["status"])
        cookie = next(v for k, v in login["headers"] if k == "set-cookie")
        self.assertIn("HttpOnly", cookie)
        self.assertIn("Secure", cookie)

    def test_trusted_proxy_ignores_a_client_forged_leftmost_forward(self):
        os.environ["LIANHUAN_TRUSTED_PROXIES"] = "127.0.0.1"
        self.assertEqual(
            "203.0.113.9",
            self.gate.client_addr("127.0.0.1", "127.0.0.1, 203.0.113.9"),
        )

    def test_android_random_cookie_guards_static_and_api_routes(self):
        token = "android-test-token-with-enough-entropy"
        os.environ["LIANHUAN_ANDROID_TOKEN"] = token
        for path in ("/manifest.json", "/api/export"):
            self.assertEqual(401, _request(path=path)["status"])
            allowed = _request(path=path, headers=(("cookie", "lh_android=" + token),))
            self.assertEqual(200, allowed["status"])


if __name__ == "__main__":
    unittest.main()
