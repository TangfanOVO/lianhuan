"""安卓完整体的起点模块：不靠 Chaquopy 也能在电脑上验它真能把后端起在 127.0.0.1。"""
import http.client
import pathlib
import socket
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "android-full" / "app" / "src" / "main" / "python"))


class TestAndroidBoot(unittest.TestCase):
    def test_start_serves_the_app_on_loopback(self):
        import android_boot
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
        files_dir = tempfile.mkdtemp(prefix="lh-android-")
        url = android_boot.start(files_dir, port)
        self.assertEqual(url, f"http://127.0.0.1:{port}/")
        self.assertEqual(android_boot.start(files_dir, port), url, "重复调用只该返回同一个地址")
        code = None
        for _ in range(50):
            try:
                c = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
                c.request("GET", "/manifest.json"); code = c.getresponse().status; c.close()
                break
            except OSError:
                time.sleep(0.1)
        self.assertEqual(code, 200, "后端没在 loopback 上应答")

    def test_requirements_pin_pydantic_v1(self):
        r = (ROOT / "android-full" / "app" / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("pydantic<2", r, "pydantic-core 没有安卓轮子，必须钉 1.x")
        self.assertNotIn("pywebpush", r)


if __name__ == "__main__":
    unittest.main()
