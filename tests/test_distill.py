"""蒸馏流水线的测试。

★ 一条都不碰网络：提取那一步的模型回答是喂进去的假回答（`fake_say`）。
  真模型只在人工验收时跑一次 —— 单元测试要能在没有 key 的机器上跑完。
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import distill                                   # noqa: E402
from core.store.base import Memory                         # noqa: E402
from core.store.sqlite import SqliteStore                  # noqa: E402
from core.store.base import Turn                           # noqa: E402


def fake_say(reply: str):
    async def say(_prompt: str) -> str:
        return reply
    return say


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.store = SqliteStore(Path(self.dir) / "t.db")
        distill.bind(self.store, fake_say('{"items":[]}'))

    def talk(self, *pairs):
        for who, what in pairs:
            self.store.add_turn(Turn(role=who, content=what, ts=1.0))

    def run_distill(self, reply, force=True):
        distill._say = fake_say(reply)
        return asyncio.run(distill.run(force=force))


class TestExtract(Base):
    def test_picks_go_to_latent_not_into_the_library(self):
        """★ 这条是整件事的地基：提出来的东西**不许直接进记忆库**。"""
        self.talk(("user", "我不吃香菜"), ("assistant", "记下了"))
        r = self.run_distill('{"items":[{"content":"他不吃香菜","layer":"L2","why":"忌口"}]}')
        self.assertEqual(1, r["picked"])
        self.assertEqual(1, len(distill.pending("new")["items"]))
        self.assertEqual(0, len(self.store.all_memories()), "还没人点头，库里不该有东西")

    def test_survives_a_model_that_wraps_json_in_chatter(self):
        """模型爱在 JSON 外面裹一层话，还爱套 ```json —— 都要认。"""
        self.talk(("user", "猫叫豆子"), ("assistant", "嗯"))
        r = self.run_distill('好的，我挑出这些：\n```json\n{"items":[{"content":"他的猫叫豆子"}]}\n```\n就这些。')
        self.assertEqual(1, r["picked"])

    def test_garbage_reply_picks_nothing_and_does_not_crash(self):
        self.talk(("user", "嗨"), ("assistant", "嗨"))
        self.assertEqual(0, self.run_distill("我不知道该说什么")["picked"])

    def test_cursor_moves_so_the_same_turns_are_not_mined_twice(self):
        self.talk(("user", "一"), ("assistant", "二"))
        self.run_distill('{"items":[{"content":"甲"}]}')
        again = self.run_distill('{"items":[{"content":"乙"}]}', force=False)
        self.assertEqual(0, again["picked"], "游标没走，同一段话被提了第二遍")

    def test_respects_max_per_run(self):
        distill.set_cfg({"max_per_run": 2})
        self.talk(("user", "很多事"), ("assistant", "嗯"))
        r = self.run_distill(json.dumps({"items": [{"content": "第%d条" % i} for i in range(5)]},
                                        ensure_ascii=False))
        self.assertEqual(2, r["picked"], "一次提太多，人就懒得审了")


class TestDedupe(Base):
    def test_flags_a_near_duplicate_but_never_merges(self):
        """★ 0827 那一跤的护栏：**只标出来，绝不自动合并**。"""
        self.store.add_memory(Memory(content="他的猫叫豆子，橘色，六岁", layer="L2"))
        self.talk(("user", "豆子今天又踩键盘"), ("assistant", "嗯"))
        self.run_distill('{"items":[{"content":"他的猫叫豆子"}]}')
        it = distill.pending("new")["items"][0]
        self.assertIsNotNone(it["dup_of"], "跟老记忆重了却没标出来")
        self.assertIn("豆子", it["dup_content"])
        self.assertEqual(1, len(self.store.all_memories()), "老记忆被动过了")

    def test_unrelated_content_is_not_flagged(self):
        """反例：语义上都跟生活有关，但字面不重 —— 不许标成重复。
        （向量那条路就是在这里翻的车：一条「熬通宵」吃掉十二条不相干的事实。）"""
        self.store.add_memory(Memory(content="他不吃香菜，点外卖每次都要备注", layer="L2"))
        self.talk(("user", "我昨天熬通宵了"), ("assistant", "嗯"))
        self.run_distill('{"items":[{"content":"他昨晚熬了通宵"}]}')
        self.assertIsNone(distill.pending("new")["items"][0]["dup_of"])

    def test_similarity_uses_the_shorter_side_as_denominator(self):
        self.store.add_memory(Memory(content="他的猫叫豆子，橘色，六岁，怕吸尘器，半夜会踩键盘"))
        _, score = distill.similar("他的猫叫豆子")
        self.assertGreater(score, 0.7, "短句被长句包着，应该算作很像")


class TestApprove(Base):
    def setUp(self):
        super().setUp()
        self.talk(("user", "我不吃香菜"), ("assistant", "嗯"))
        self.run_distill('{"items":[{"content":"他不吃香菜","layer":"L2"}]}')
        self.lid = distill.pending("new")["items"][0]["id"]

    def test_keep_puts_it_in_with_the_right_layer(self):
        r = distill.keep(self.lid)
        self.assertTrue(r["ok"])
        mems = self.store.all_memories()
        self.assertEqual(1, len(mems))
        self.assertEqual("L2", mems[0].layer)
        self.assertEqual(0, distill.pending("new")["counts"]["new"])

    def test_drop_keeps_the_library_empty(self):
        self.assertTrue(distill.drop(self.lid)["ok"])
        self.assertEqual(0, len(self.store.all_memories()))
        self.assertEqual(1, distill.pending("dropped")["counts"]["dropped"])

    def test_cannot_double_keep(self):
        distill.keep(self.lid)
        self.assertFalse(distill.keep(self.lid)["ok"], "点两下头不该进两条")
        self.assertEqual(1, len(self.store.all_memories()))

    def test_auto_keep_is_off_by_default(self):
        self.assertFalse(distill.DEFAULTS["auto_keep"])

    def test_auto_keep_when_turned_on(self):
        distill.set_cfg({"auto_keep": True})
        self.talk(("user", "我猫叫豆子"), ("assistant", "嗯"))
        r = self.run_distill('{"items":[{"content":"他的猫叫豆子"}]}')
        self.assertEqual(1, len(r["auto_kept"]))
        self.assertEqual(1, len(self.store.all_memories()))


class TestPromote(Base):
    def test_climbs_only_after_enough_recalls(self):
        mid = self.store.add_memory(Memory(content="他不吃香菜", layer="L1"))
        distill.set_cfg({"to_l2": 3, "to_l3": 5})
        for _ in range(2):
            distill.note_recall([mid])
        self.assertEqual([], distill.promote(), "还不够就升，那这个门槛等于没有")
        distill.note_recall([mid])
        up = distill.promote()
        self.assertEqual("L2", up[0]["to"])
        for _ in range(2):
            distill.note_recall([mid])
        self.assertEqual("L3", distill.promote()[0]["to"])

    def test_content_is_never_touched_by_promotion(self):
        mid = self.store.add_memory(Memory(content="原话一个字都不许变", layer="L1"))
        distill.set_cfg({"to_l2": 1})
        for _ in range(2):
            distill.note_recall([mid])
        distill.promote()
        self.assertEqual("原话一个字都不许变", self.store.all_memories()[0].content)

    def test_recall_hook_is_wired_onto_the_store(self):
        """召回时记一笔 —— 这个钩子是 recall.build_injection 找的那个名字。"""
        self.assertTrue(callable(getattr(self.store, "note_recall", None)))


class TestOffSwitch(Base):
    def test_every_turns_zero_means_never(self):
        """它自己也要花模型的钱。关得掉，才敢默认开着。"""
        distill.set_cfg({"every_turns": 0})
        self.assertEqual(0, distill.cfg()["every_turns"])

    def test_status_reports_how_far_behind_it_is(self):
        self.talk(("user", "一"), ("assistant", "二"), ("user", "三"))
        st = distill.status()
        self.assertEqual(3, st["turns"])
        self.assertEqual(3, st["behind"])
        self.run_distill('{"items":[]}')
        self.assertEqual(0, distill.status()["behind"])


if __name__ == "__main__":
    unittest.main()
