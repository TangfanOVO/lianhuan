"""没有 FTS5 的 SQLite 上也要能起来、能搜。

0903 真机抓的：安卓完整体用 Chaquopy 自带的 SQLite，它没编 FTS5，
`CREATE VIRTUAL TABLE … USING fts5` 抛 `no such module: fts5`，后端整个起不来 ——
完整体从第一版起就没起来过，只是没人在真机上开过。
"""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.store.sqlite import SqliteStore
from core.store.base import Memory


class TestWorksWithoutFts5(unittest.TestCase):
    def _store(self, fts: bool) -> SqliteStore:
        d = tempfile.mkdtemp(prefix="lh-fts-")
        with mock.patch("core.store.sqlite._fts5_works", return_value=fts):
            return SqliteStore(Path(d) / "x.db")

    def test_it_starts_and_searches_without_fts5(self):
        s = self._store(fts=False)
        self.assertFalse(s.fts, "探测说没有 FTS5，就不该建那张影子表")
        rows = {r[0] for r in s.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertNotIn("memories_fts", rows)
        trigs = {r[0] for r in s.db.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        self.assertFalse(trigs & {"memories_ai", "memories_ad"},
                         "表没建成，触发器也一个都不许留 —— 它们引用那张表，留着就写不进记忆")

        # 写、搜、删都要照常
        s.add_memory(Memory(content="他的猫叫豆子，橘色，六岁。", layer="L2"))
        s.add_memory(Memory(content="她咖啡过敏。", layer="L2"))
        hit = s.search_memories("豆子")
        self.assertEqual([m.content for m in hit], ["他的猫叫豆子，橘色，六岁。"])
        s.delete_memory(s.all_memories()[0].id)
        self.assertEqual(len(s.all_memories()), 1)

    def test_with_fts5_nothing_changes(self):
        """有 FTS5 的机器上一切照旧 —— 这条盯的是「别为了安卓把桌面弄坏」。"""
        s = self._store(fts=True)
        self.assertTrue(s.fts)
        rows = {r[0] for r in s.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("memories_fts", rows)
        s.add_memory(Memory(content="他的猫叫豆子。", layer="L2"))
        self.assertEqual([m.content for m in s.search_memories("豆子")], ["他的猫叫豆子。"])

    def test_probe_says_no_on_a_build_without_fts5(self):
        """探测函数本身：模块缺失时要老实回 False，不能把异常放出去。
        （sqlite3.Connection 的方法改不了，所以拿一个只会抛这个错的假连接来试。）"""
        from core.store import sqlite as mod

        class NoFts:
            def execute(self, sql):
                raise sqlite3.OperationalError("no such module: fts5")

        self.assertFalse(mod._fts5_works(NoFts()))

    def test_probe_says_yes_on_this_machine(self):
        """反过来钉一下：本机是有 FTS5 的，探测别把好机器也判成没有。"""
        from core.store import sqlite as mod
        self.assertTrue(mod._fts5_works(sqlite3.connect(":memory:")))


if __name__ == "__main__":
    unittest.main()
