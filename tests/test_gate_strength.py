"""那道门本身：口令够不够硬，猜错了会不会被拦。

★ 这几条钉的是**部署事故**，不是功能：门开在公网上，短口令和不限次数的猜，
  任何一样单独都够让一整个家被人推开。
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import gate


class TestPasswordStrength(unittest.TestCase):
    def test_short_and_placeholder_are_refused(self):
        for bad in ("", "   ", "short", "hunter2", "改成你的口令", "changeme", "PASSWORD"):
            self.assertTrue(gate.weak(bad), f"{bad!r} 应该被拒")
        self.assertFalse(gate.weak("a-long-enough-passphrase"))

    def test_arm_raises_instead_of_warning(self):
        """★ 不合格就抛，不是打个警告继续跑 —— 「先开着回头再改」那个回头永远不会来。"""
        with self.assertRaises(ValueError):
            gate.arm("short")
        self.assertFalse(gate.on(), "被拒之后门不该是开着的")

    def test_min_len_is_at_least_16(self):
        self.assertGreaterEqual(gate.MIN_LEN, 16)


class TestLoginRateLimit(unittest.TestCase):
    def setUp(self):
        gate._fails.clear()

    tearDown = setUp

    def test_locks_after_five_failures(self):
        for i in range(gate.FAIL_MAX - 1):
            self.assertEqual(0, gate.note_fail("1.2.3.4"), f"第 {i + 1} 次不该锁")
        wait = gate.note_fail("1.2.3.4")
        self.assertGreater(wait, 0, "第 5 次该锁上了")
        self.assertGreaterEqual(wait, gate.LOCK_SEC - 5)

    def test_lock_is_per_address(self):
        for _ in range(gate.FAIL_MAX):
            gate.note_fail("1.2.3.4")
        self.assertGreater(gate.locked("1.2.3.4"), 0)
        self.assertEqual(0, gate.locked("5.6.7.8"), "别人的地址不该被连坐")

    def test_success_clears_the_count(self):
        for _ in range(gate.FAIL_MAX - 1):
            gate.note_fail("1.2.3.4")
        gate.note_ok("1.2.3.4")
        self.assertEqual(0, gate.note_fail("1.2.3.4"), "进对过一次，计数该从头数")

    def test_tracking_table_cannot_grow_without_bound(self):
        """★ 换着 IP 敲不该变成往内存里灌东西。"""
        for i in range(gate.MAX_TRACKED + 50):
            gate.note_fail(f"10.0.{i // 256}.{i % 256}")
        self.assertLessEqual(len(gate._fails), gate.MAX_TRACKED + 1)

    def test_lock_expires(self):
        gate._fails["1.2.3.4"] = [0, gate._now() - 1]
        self.assertEqual(0, gate.locked("1.2.3.4"), "过期了就该放行")
        self.assertNotIn("1.2.3.4", gate._fails, "过期记录该被清掉，别攒着")


if __name__ == "__main__":
    unittest.main()


class TestLoginEndpointIsRateLimited(unittest.TestCase):
    """★ 上面几条只验了计数器本身。这条验**它真的接在 /api/login 上** ——
    限流函数写对了但没人调，跟没有限流是一回事。"""

    def setUp(self):
        import os
        import tempfile
        self.old_db = os.environ.get("LIANHUAN_DB")
        os.environ["LIANHUAN_DB"] = str(pathlib.Path(tempfile.mkdtemp()) / "x.db")
        gate._fails.clear()
        gate.arm("a-long-enough-passphrase")

    def tearDown(self):
        import os
        gate._state["on"] = False
        gate._state["token"] = ""
        gate._fails.clear()
        if self.old_db is None:
            os.environ.pop("LIANHUAN_DB", None)
        else:
            os.environ["LIANHUAN_DB"] = self.old_db

    def _login(self, pw, addr="9.9.9.9"):
        import asyncio
        import json as _json
        from core.server import app

        out = {}

        async def go():
            scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                     "method": "POST", "scheme": "http", "path": "/api/login",
                     "raw_path": b"/api/login", "query_string": b"", "root_path": "",
                     "headers": [(b"host", b"x"), (b"content-type", b"application/json")],
                     "client": (addr, 1), "server": ("x", 80)}
            body = _json.dumps({"password": pw}).encode()
            got = [{"type": "http.request", "body": body, "more_body": False}]

            async def receive():
                return got.pop(0) if got else {"type": "http.disconnect"}

            async def send(m):
                if m["type"] == "http.response.start":
                    out["status"] = m["status"]
                elif m["type"] == "http.response.body":
                    out["body"] = out.get("body", b"") + m.get("body", b"")

            await app(scope, receive, send)

        asyncio.run(go())
        return out

    def test_wrong_password_eventually_gets_429(self):
        for _ in range(gate.FAIL_MAX - 1):
            self.assertEqual(401, self._login("nope-nope-nope-nope")["status"])
        self.assertEqual(429, self._login("nope-nope-nope-nope")["status"], "错满 5 次该被拦住")
        # ★ 锁上之后，连**正确**的口令也得等 —— 不然攻击者拿它当探测器
        self.assertEqual(429, self._login("a-long-enough-passphrase")["status"])

    def test_other_address_is_not_punished(self):
        for _ in range(gate.FAIL_MAX + 1):
            self._login("nope-nope-nope-nope", addr="9.9.9.9")
        self.assertEqual(200, self._login("a-long-enough-passphrase", addr="8.8.8.8")["status"])
