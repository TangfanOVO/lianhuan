"""设置里的搬家入口必须真的接到现有导入导出接口。"""
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parent.parent


class TestMoveUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.web = (ROOT / "core" / "web" / "index.html").read_text(encoding="utf-8")
        app = ROOT / "app" / "index.html"
        cls.app = app.read_text(encoding="utf-8") if app.exists() else None

    def test_both_pages_are_identical(self):
        if self.app is None:
            self.skipTest("发行产物只带运行页面，不带开发镜像")
        self.assertEqual(self.app, self.web)

    def test_settings_has_one_real_move_page(self):
        self.assertEqual(self.web.count('data-open="movepage"'), 1)
        self.assertEqual(self.web.count('id="movepage"'), 1)
        for element_id in ("moveExport", "moveFile", "movePick", "moveMerge", "moveReplace"):
            self.assertEqual(self.web.count(f'id="{element_id}"'), 1)

    def test_export_import_and_replace_confirmation_are_wired(self):
        self.assertIn("fetch('/api/export'", self.web)
        self.assertIn("fetch('/api/import'", self.web)
        self.assertIn("bringBack('merge')", self.web)
        self.assertIn("bringBack('replace')", self.web)
        self.assertIn("body.confirm = true", self.web)
        self.assertIn("mode === 'replace' && !confirm(", self.web)
        self.assertIn("window.__lianhuanLocal.flush", self.web)
        self.assertIn("#moveActions[hidden]{display:none!important}", self.web)


if __name__ == "__main__":
    unittest.main()


#: 完整体那份 Java。★ create.py 的产物不带 android-full/，所以下面那组要能整组跳过 ——
#  0903 就是没想到这一层，CI 的 clean copy 那步当场红了。
SHELL_JAVA = (ROOT / "android-full" / "app" / "src" / "main" / "java"
              / "app" / "lianhuan" / "full" / "MainActivity.java")


@unittest.skipUnless(SHELL_JAVA.exists(), "发行产物不带 android-full/，这组只在源码仓库里跑")
class TestShellDownloadPath(unittest.TestCase):
    """安卓壳里不能走 blob 下载 —— 0903 真机上验的：什么都不会发生，页面却说「下载好了」。"""

    @classmethod
    def setUpClass(cls):
        cls.web = (ROOT / "core" / "web" / "index.html").read_text(encoding="utf-8")
        cls.java = SHELL_JAVA.read_text(encoding="utf-8")

    def test_page_takes_the_direct_route_inside_the_shell(self):
        self.assertIn("/LianhuanShell/.test(navigator.userAgent", self.web)
        self.assertIn("if (inShell){ location.href = 'api/export'; return; }", self.web)
        # 别处照旧走 blob，别为了安卓把桌面改坏
        self.assertIn("URL.createObjectURL", self.web)

    def test_shell_marks_its_user_agent_without_dropping_android(self):
        self.assertIn('setUserAgentString(s.getUserAgentString() + " LianhuanShell/1")', self.java)
        # 页面里那句 /Android/i 的判断靠 UA 里还留着 Android —— 只许追加，不许覆盖
        self.assertNotIn('setUserAgentString("', self.java)

    def test_shell_catches_downloads_and_carries_the_token(self):
        self.assertIn("setDownloadListener", self.java)
        self.assertIn("DIRECTORY_DOWNLOADS", self.java)
        # 下载管理器是独立进程，不带 WebView 的 Cookie；不自己带票就会存下一句 401
        self.assertIn('req.addRequestHeader("Cookie", "lh_android=" + androidToken)', self.java)
        # 失败要吵出来，不许再来一次假成功
        self.assertIn("没存下来：", self.java)
