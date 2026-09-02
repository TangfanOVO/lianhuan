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


class TestAndroidBoot(unittest.TestCase):
    def test_start_serves_the_app_on_loopback(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
        files_dir = tempfile.mkdtemp(prefix="lh-android-")
        code = (f"import sys, time; sys.path.insert(0, {str(BOOT_DIR)!r}); sys.path.insert(0, {str(ROOT)!r}); "
                f"import android_boot; u = android_boot.start({files_dir!r}, {port}); "
                f"assert u == android_boot.start({files_dir!r}, {port}), '重复调用要回同一个地址'; "
                f"print(u, flush=True); time.sleep(30)")
        env = {k: v for k, v in os.environ.items() if not k.startswith("LIANHUAN_")}
        p = subprocess.Popen([sys.executable, "-c", code], cwd=files_dir, env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
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
            self.assertEqual(status, 200, "后端没在 loopback 上应答：" + (p.stderr.read()[-800:] if p.poll() is not None else ""))
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
