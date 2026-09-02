"""一键部署那几份文件的形状 —— 改了 Dockerfile / render.yaml 别把口令那道门弄丢。"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


class TestDeployFiles(unittest.TestCase):
    def test_dockerfile_starts_with_the_gate_on(self):
        d = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("core.server", d)
        self.assertIn("--lan", d, "容器必须按「开到网络上」起，进门要口令")
        self.assertIn("/app/data", d, "数据得在 /app/data，持久盘才有地方挂")

    def test_render_blueprint_asks_for_password(self):
        y = (ROOT / "render.yaml").read_text(encoding="utf-8")
        self.assertRegex(y, r"runtime:\s*docker")
        self.assertRegex(y, r"key:\s*LIANHUAN_PASSWORD\s*\n\s*sync:\s*false", "口令要让用户自己填，不能写死")
        self.assertNotRegex(y, r"(?m)^\s*disks:", "免费档不能带 disks，那段留注释")

    def test_dockerignore_keeps_secrets_out(self):
        i = (ROOT / ".dockerignore").read_text(encoding="utf-8").split()
        for must in ("data", ".env", "secrets.json", ".git"):
            self.assertIn(must, i, must + " 不该进镜像")

    def test_readme_button_points_at_this_repo(self):
        r = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("render.com/deploy?repo=https://github.com/TangfanOVO/lianhuan", r)
        self.assertIn("app.koyeb.com/deploy?type=git&repository=github.com/TangfanOVO/lianhuan", r)

    def test_clean_copy_brings_the_deploy_files(self):
        c = (ROOT / "create.py").read_text(encoding="utf-8")
        for f in ("Dockerfile", "render.yaml", "docker-compose.yml", ".dockerignore"):
            self.assertIn(f'"{f}"', c, f + " 要跟着 create.py 的产物走")


if __name__ == "__main__":
    unittest.main()
