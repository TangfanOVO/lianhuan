"""core/browser.py 在电脑上就能验的那部分：handle() 把一条请求喂给 ASGI、把回答流进 sink。"""
import asyncio
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


class _Sink:
    def __init__(self):
        self.status = None; self.headers = None; self.chunks = []; self.ended = False
    def start(self, status, hjson): self.status, self.headers = status, json.loads(hjson)
    def chunk(self, b): self.chunks.append(bytes(b))
    def end(self): self.ended = True


class TestBrowserGlue(unittest.TestCase):
    def test_transport_is_none_on_desktop(self):
        from core import browser
        self.assertFalse(browser.IN_BROWSER)
        self.assertIsNone(browser.transport())

    def test_handle_feeds_the_real_app(self):
        from core import browser
        from core.server import app
        browser._app = app
        sink = _Sink()
        asyncio.run(browser.handle("GET", "/api/distill", "", [["host", "local"]], None, sink))
        self.assertEqual(sink.status, 200)
        self.assertTrue(sink.ended)
        body = json.loads(b"".join(sink.chunks))
        self.assertIn("config", body)
        ctype = dict(sink.headers).get("content-type", "")
        self.assertIn("json", ctype)

    def test_handle_reports_errors_instead_of_hanging(self):
        from core import browser
        async def boom(scope, receive, send):
            raise RuntimeError("炸了")
        old = browser._app; browser._app = boom
        try:
            sink = _Sink()
            asyncio.run(browser.handle("GET", "/x", "", [], None, sink))
            self.assertEqual(sink.status, 500)
            self.assertTrue(sink.ended)
            self.assertIn("炸了", b"".join(sink.chunks).decode())
        finally:
            browser._app = old

    def test_engine_hook_is_a_noop_on_desktop(self):
        from core.engines import openai_compat
        self.assertIsNone(openai_compat._browser_transport())


if __name__ == "__main__":
    unittest.main()
