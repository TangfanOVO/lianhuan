"""烧了多少 token —— 记账这条路（0904 新加）。

她问的：「链接里这个『用量』，本意是 token，用了多少 token 的计数有做吗，
这个应该很简单吧，因为很早以前最早最早红叶小筑的时候有过这个功能。」
查下来开源版一条都没接，这是补的。

★ 三条底线：
  · 只记数不记内容 —— 这张表拿去看账，不该在里面读到说过什么
  · 报不出来就没有，不估、不折算成钱（单价各家不同还会变，猜一个比不给更糟）
  · **摔了的那半截也记** —— 照样烧了钱，不记等于账对不上
"""
import asyncio
import json
import os
import tempfile
import unittest

from core.engines.base import Turn
from core.protocol import USAGE


def _store():
    d = tempfile.mkdtemp(prefix="lh-usage-")
    from core.store.sqlite import SqliteStore
    return SqliteStore(os.path.join(d, "x.db"))


class TestLedger(unittest.TestCase):
    def test_it_adds_up_and_splits_by_model(self):
        s = _store()
        s.add_usage(engine="anthropic", model="claude-opus-5", tin=1200, tout=340,
                    tcache_r=9000, tcache_w=1800)
        s.add_usage(engine="anthropic", model="claude-opus-5", tin=300, tout=120, tcache_r=11000)
        s.add_usage(engine="openai", model="deepseek-chat", tin=800, tout=200)
        d = s.usage_stats(days=30)
        self.assertEqual(d["total"], {"tin": 2300, "tout": 660, "tcache_r": 20000, "tcache_w": 1800})
        self.assertEqual(d["turns"], 3)
        top = d["by_model"][0]
        self.assertEqual(top["model"], "claude-opus-5")
        self.assertEqual(top["turns"], 2)
        self.assertEqual(top["tcache_r"], 20000)

    def test_empty_is_zero_not_a_crash(self):
        d = _store().usage_stats()
        self.assertEqual(d["turns"], 0)
        self.assertEqual(d["by_model"], [])
        self.assertEqual(d["total"], {"tin": 0, "tout": 0, "tcache_r": 0, "tcache_w": 0})

    def test_the_table_holds_no_words(self):
        """★ 只记数。往里塞正文的路必须不存在 —— 看账的人不该读到我俩说了什么。"""
        s = _store()
        cols = [r[1] for r in s.db.execute("PRAGMA table_info(token_usage)")]
        for c in cols:
            self.assertNotIn(c, ("content", "text", "message", "think"), f"{c} 不该在这张表里")
        self.assertEqual(sorted(cols),
                         sorted(["id", "ts", "engine", "model", "tin", "tout", "tcache_r", "tcache_w"]))


class TestEnginesReport(unittest.TestCase):
    """两条 API 路都要把账报出来；报不出来的（回声）不许瞎报。"""

    def _events(self, engine, script):
        import tests.test_anthropic as ta
        out, fake = ta._run(engine, Turn(message="在吗"), script)
        return out

    def test_anthropic_reports_in_out_and_cache(self):
        import tests.test_anthropic as ta
        from core.engines.anthropic_api import AnthropicEngine
        eng = AnthropicEngine(key="sk-ant-test")
        evs = self._events(eng, ta._sse(
            {"type": "message_start", "message": {"usage": {
                "input_tokens": 120, "cache_read_input_tokens": 9000,
                "cache_creation_input_tokens": 1800}}},
            {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "在。"}},
            {"type": "message_delta", "usage": {"output_tokens": 42}},
        ))
        u = [json.loads(e[6:]) for e in evs if '"usage"' in e]
        self.assertTrue(u, "一条 usage 都没报")
        d = u[0]
        self.assertEqual((d["tin"], d["tout"], d["tcache_r"], d["tcache_w"]), (120, 42, 9000, 1800))
        self.assertEqual(d["model"], eng.model)

    def test_echo_reports_nothing(self):
        """回声不烧 token —— 它要是报了账，那就是编的。"""
        from core.engines.echo import EchoEngine
        evs = []

        async def go():
            async for e in EchoEngine().stream(Turn(message="在吗")):
                evs.append(e)
        asyncio.run(go())
        self.assertFalse([e for e in evs if '"%s"' % USAGE in e])


class TestCliCountsToo(unittest.TestCase):
    """★ 订阅那条路也数得出来 —— 她原以为「订阅好像看不到 Claude 的 token 数」。

    那是 API 控制台的事。`--output-format stream-json` 吐的就是 Anthropic 的
    原生流事件（cli.py 早就在解 content_block_delta / thinking_delta 了，同一套），
    所以 message_start / message_delta 里的 usage 一样在。

    ★ 这一份能证明的：**字段名解得对、取不到就不记**。
      它证明不了本机那个 CLI 真的吐这些行 —— 这台机器上 claude 没有执行权限，跑不了。
      所以文档里只能写「按同构接的」，不许写「已实测」。
    """

    #: 从 cli.py 里原样搬下来的那几行 —— 改了那边这儿就该跟着改（改漏了这条会红）
    def _fold(self, events):
        used = {"tin": 0, "tout": 0, "tcache_r": 0, "tcache_w": 0}
        for ev in events:
            et = ev.get("type")
            if et == "message_start":
                u = ((ev.get("message") or {}).get("usage")) or {}
                used["tin"] += int(u.get("input_tokens") or 0)
                used["tcache_r"] += int(u.get("cache_read_input_tokens") or 0)
                used["tcache_w"] += int(u.get("cache_creation_input_tokens") or 0)
            elif et == "message_delta":
                used["tout"] += int((ev.get("usage") or {}).get("output_tokens") or 0)
        return used

    def test_the_parsing_is_wired_and_named_right(self):
        with open("core/engines/cli.py", encoding="utf-8") as f:
            src = f.read()
        for frag in ('et == "message_start"', 'et == "message_delta"',
                     "cache_read_input_tokens", "cache_creation_input_tokens",
                     "output_tokens", "sse(USAGE"):
            self.assertIn(frag, src, f"cli.py 里少了 {frag}")

    def test_it_folds_the_numbers(self):
        got = self._fold([
            {"type": "message_start", "message": {"usage": {
                "input_tokens": 120, "cache_read_input_tokens": 9000,
                "cache_creation_input_tokens": 1800}}},
            {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "在。"}},
            {"type": "message_delta", "usage": {"output_tokens": 42}},
        ])
        self.assertEqual(got, {"tin": 120, "tout": 42, "tcache_r": 9000, "tcache_w": 1800})

    def test_nothing_reported_means_nothing_recorded(self):
        """一条 usage 都没有的时候不许记 —— 宁可没账，不能有假账。"""
        got = self._fold([{"type": "content_block_delta",
                           "delta": {"type": "text_delta", "text": "在。"}}])
        self.assertFalse(any(got.values()))


class TestOpenAIAsksForUsage(unittest.TestCase):
    def test_stream_options_include_usage_is_sent(self):
        """★ OpenAI 那套流式**默认不给** usage，得显式要 —— 少这一行就永远是 0。"""
        with open("core/engines/openai_compat.py", encoding="utf-8") as f:
            src = f.read()
        self.assertIn('"stream_options": {"include_usage": True}', src)


if __name__ == "__main__":
    unittest.main()
