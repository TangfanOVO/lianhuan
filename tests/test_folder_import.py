"""手机文件夹导入的回归测试：先待审，不直写记忆库。"""
from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import distill  # noqa: E402
from core.store.sqlite import SqliteStore  # noqa: E402


class TestFolderMemoryImport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = SqliteStore(pathlib.Path(self.tmp.name) / "folder-import.db")
        distill.bind(self.store, None)

    def tearDown(self):
        self.tmp.cleanup()

    def test_import_stays_pending_and_exact_duplicate_is_skipped(self):
        first = distill.import_candidates([
            {"content": "这是一条从旧文件夹读来的记忆。", "why": "来自本机文件：旧记忆/a.md"}
        ])
        self.assertEqual(1, first["imported"])
        self.assertEqual(1, len(distill.pending("new")["items"]))
        self.assertEqual(0, len(self.store.all_memories()), "未经确认不许直接参与召回")

        again = distill.import_candidates([
            {"content": "这是一条从旧文件夹读来的记忆。", "why": "来自本机文件：备份/a.md"}
        ])
        self.assertEqual(0, again["imported"])
        self.assertEqual(1, again["skipped"])


class TestFolderImportWiring(unittest.TestCase):
    def test_chat_and_memory_pages_offer_folder_plus_multifile_fallbacks(self):
        page = (ROOT / "core" / "web" / "index.html").read_text(encoding="utf-8")
        server = (ROOT / "core" / "server.py").read_text(encoding="utf-8")
        self.assertIn('id="folderpick" webkitdirectory multiple', page)
        self.assertIn('data-pick="folder"', page)
        self.assertIn("window.pickFolder", page)
        self.assertIn('id="memfolderpick"', page)
        self.assertIn("/api/latent/import", page)
        self.assertIn('@app.post("/api/latent/import")', server)


if __name__ == "__main__":
    unittest.main()
