"""安卓完整体的起点模块：不靠 Chaquopy 也能在电脑上验它真能把后端起在 127.0.0.1。
★ 在子进程里跑：它会 import core.server、设 LIANHUAN_DB，不能污染这个测试进程。"""
import http.client
import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
BOOT_DIR = ROOT / "android-full" / "app" / "src" / "main" / "python"


@unittest.skipUnless(BOOT_DIR.exists(), "create.py 的产物不带 android-full/，这条只在源码仓库里跑")
class TestAndroidBoot(unittest.TestCase):
    def test_start_serves_the_app_on_loopback(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
        files_dir = tempfile.mkdtemp(prefix="lh-android-")
        code = (f"import sys, time; sys.path.insert(0, {str(BOOT_DIR)!r}); sys.path.insert(0, {str(ROOT)!r}); "
                f"import android_boot; u = android_boot.start({files_dir!r}, {port}); "
                f"assert u == android_boot.start({files_dir!r}, {port}), '重复调用要回同一个地址'; "
                f"print(u, android_boot.token(), flush=True); time.sleep(30)")
        env = {k: v for k, v in os.environ.items() if not k.startswith("LIANHUAN_")}
        p = subprocess.Popen([sys.executable, "-c", code], cwd=files_dir, env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            line = p.stdout.readline().strip().split()
            self.assertEqual(2, len(line), "启动端没有交出 URL 和随机票")
            token = line[1]
            self.assertGreaterEqual(len(token), 32)
            status = None
            for _ in range(100):
                if p.poll() is not None:
                    break
                try:
                    c = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
                    c.request("GET", "/manifest.json"); status = c.getresponse().status; c.close()
                    break
                except OSError:
                    time.sleep(0.1)
            self.assertEqual(status, 401, "没有完整体随机票也不该进得去：" + (p.stderr.read()[-800:] if p.poll() is not None else ""))
            headers = {"Cookie": "lh_android=" + token}
            for path in ("/manifest.json", "/api/export"):
                c = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
                c.request("GET", path, headers=headers)
                self.assertEqual(200, c.getresponse().status, path + " 带随机票仍进不去")
                c.close()
            self.assertTrue(os.path.exists(os.path.join(files_dir, "data", "lianhuan.db")), "数据该落在 files_dir/data")
        finally:
            p.kill(); p.wait()

    def test_requirements_pin_pydantic_v1(self):
        lines = [l.strip() for l in (ROOT / "android-full" / "app" / "requirements.txt").read_text(encoding="utf-8").splitlines()
                 if l.strip() and not l.strip().startswith("#")]
        self.assertIn("pydantic<2", lines, "pydantic-core 没有安卓轮子，必须钉 1.x")
        self.assertFalse(any(l.startswith("pywebpush") for l in lines))


if __name__ == "__main__":
    unittest.main()
