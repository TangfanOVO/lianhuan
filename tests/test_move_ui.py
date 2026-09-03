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
