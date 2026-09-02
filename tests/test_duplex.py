"""能插话的那种通话 —— 中继。

★ 这里钉的是**架构**，不是协议细节：
  对面那家只当耳朵和嘴，**脑子必须还是用户自己配的那个引擎**。
  一旦有人把 instructions/tools 塞回去，用户的记忆和人设就全丢了 —— 那是最糟的坏法，
  因为它「还是能说话」，听起来一切正常。
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.store.sqlite import SqliteStore                   # noqa: E402
from optional.callkit import duplex as dx                    # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.old = os.environ.get("LIANHUAN_DB")
        os.environ["LIANHUAN_DB"] = str(Path(self.dir) / "d.db")
        self.store = SqliteStore(Path(self.dir) / "d.db")
        dx.bind(self.store, lambda: None)

    def tearDown(self):
        if self.old is None:
            os.environ.pop("LIANHUAN_DB", None)
        else:
            os.environ["LIANHUAN_DB"] = self.old


class TestItOnlyBorrowsEarsAndMouth(Base):
    """整件事的地基：只借耳朵和嘴，脑子是自己的。"""

    def test_opening_frame_gives_no_brain_away(self):
        s = dx.session_create()["session"]
        self.assertNotIn("instructions", s,
                         "给了 instructions ＝ 让对面那家自己去想，用户的人设就白设了")
        self.assertNotIn("tools", s,
                         "给了 tools ＝ 它会自己动手，而那些手接的是我们这边的库")

    def test_audio_format_matches_what_the_upstream_wants(self):
        s = dx.session_create()["session"]
        self.assertEqual(16000, s["audio"]["input"]["format"]["sample_rate"])
        self.assertEqual(24000, s["audio"]["output"]["format"]["sample_rate"])

    def test_the_relay_cancels_the_far_side_brain(self):
        """ASR 一出字就要掐掉对面的脑子 —— 不掐它会自己抢答。

        ★ 0901 检查范围跟着搬了（**不是放宽**）：耳朵和嘴抽进 ears.py 之后，
          「掐掉对面脑子」这件事对两家的做法不一样 ——
          豆包要真发 `response.cancel`（它自己有脑子会抢答）；
          11lab 的 Scribe 只转写、**根本没有脑子要掐**，那边 hush() 是停正在推的音频。
          所以：中继必须在听见人开口/听完那两处都调 hush()，
          而豆包那副耳朵的 hush() 必须真发 response.cancel。两头都钉住。
        """
        src = (Path(__file__).resolve().parent.parent
               / "optional/callkit/duplex.py").read_text(encoding="utf-8")
        ears = (Path(__file__).resolve().parent.parent
                / "optional/callkit/ears.py").read_text(encoding="utf-8")
        self.assertIn('"type": "response.cancel"', ears, "豆包那副耳朵得真掐它的脑子")
        self.assertIn("transcription", ears, "得认得出上游的转写事件")
        # ★ 0901 从「数个数」改成「按位置查」——**不是为了让它变绿**：
        #   加了回声防线之后掐的地方变成三处（我没在说话时有人开口 / 挂起之后
        #   判出真是对方在插话 / 听完一整句），数个数只会逼着下一个人去改数字，
        #   改完还不知道少了哪一处。改成一处一处指名查。
        for 哪一处, 锚 in (
            ("我没在说话，有人开口", 'await tell({"type": "lianhuan.listening"})'),
            ("听完一整句", 'job = asyncio.create_task(think(text, state["turn"]))'),
        ):
            i = src.find(锚)
            self.assertGreater(i, 0, 哪一处 + "：这段代码不见了")
            self.assertIn("await mouth.hush()", src[max(0, i - 400):i + 200],
                          哪一处 + "：这儿得掐掉对面的脑子")
        self.assertGreaterEqual(src.count("await mouth.hush()"), 2,
                                "至少人开口和听完那两处要掐")

    def test_the_answer_goes_back_to_that_mouth(self):
        """自己引擎的回复要塞回上游那张嘴。

        ★ 0901 换过帧、也换了这条断言 —— **不是为了让测试变绿**：
          原项目 0818 栽过一次并把结论写进了代码：`replacement` 那套
          **只在上游模型正生成回复的窗口内有效**，而我们是 `response.cancel`
          掐掉它的脑子之后才发 —— 那个窗口已经关了。这条路正是「先 cancel 再发」，
          也就是说它多半根本不出声，只是这个功能从来没真跑过，没人发现。
          换成原项目验过能用的 `speech_text_buffer.commit`。
        ★ 这条原来断的是**帧名**（实现细节），现在断的是**意图**（回复真的回到那张嘴），
          并且**反向钉住**那个已知失效的帧不许再用 —— 比原来严。
        """
        src = (Path(__file__).resolve().parent.parent
               / "optional/callkit/duplex.py").read_text(encoding="utf-8")
        ears = (Path(__file__).resolve().parent.parent
                / "optional/callkit/ears.py").read_text(encoding="utf-8")
        # ★ 0901：协议细节搬进 ears.py 了（两家各成一条完整的路，耳朵和嘴抽成一层）。
        #   中继本身现在只认那一层给的事件，跟哪一家无关 —— 所以往 ears 里查。
        self.assertIn('"type": "speech_text_buffer.commit"', ears, "豆包那张嘴得真收到话")
        self.assertIn("text-to-speech", ears, "11lab 那张嘴也得真接上")
        self.assertIn("mouth.say(", src, "中继把话交给那张嘴，不自己拼帧")
        # ★ 只认**真发出去的那个帧**，不是源码里出现过这几个字 ——
        #   否则一条解释「原来发的是 replacement」的注释就能把它搞红（今晚已经撞过一次）。
        self.assertNotIn('"type": "speech_text_buffer.replacement', src,
                         "replacement 在 cancel 之后是无效的（原项目 0818 的教训）")
        # 第一句一到就发，别等整段收齐
        self.assertIn("spoken_first", src, "第一句该立刻发，不等整段")

    def test_it_asks_our_own_engine_with_memories(self):
        src = (Path(__file__).resolve().parent.parent
               / "optional/callkit/duplex.py").read_text(encoding="utf-8")
        self.assertIn("build_injection", src, "不带记忆去问，等于换了个陌生人接电话")
        self.assertIn("_pick()", src, "要用用户自己配的引擎")

    def test_interruption_invalidates_the_running_turn(self):
        """人一开口，正在生成的那一轮作废 —— 一个字都不许再念出来。"""
        src = (Path(__file__).resolve().parent.parent
               / "optional/callkit/duplex.py").read_text(encoding="utf-8")
        self.assertIn('state["turn"] += 1', src)
        self.assertIn('if turn != state["turn"]', src)


class TestOneThingNotTwo(Base):
    """★ 0830 定的：通话就是一件事，能不能插话是它的一个选项，别拆成两个包。
    —— 对，那是错的。通话就是一件事，能不能插话是它的一个选项。"""

    def test_there_is_no_separate_duplex_pack(self):
        from core import packs
        ids = [p["id"] for p in packs.PACKS]
        self.assertNotIn("duplex", ids, "别再把它拆成两个包了")
        self.assertIn("call", ids)

    def test_the_pack_blurb_is_written_for_a_human(self):
        """说明是给用的人看的，不是给写代码的人看的。

        ★ 0901 改过检查范围（不是放宽标准）：这张卡看不懂，查下来毛病是
          **同一件事说两遍** —— 顶上那段和下面每个格子的说明互相重复，
          人不知道该看哪句。于是把「哪把钥匙买到什么」从顶上那段挪进了**格子自己的说明**
          （就在你要填的那个框旁边，本来就该在那儿）。
          所以这条改成查**整张卡**（说明 ＋ 分组小标题 ＋ 每个格子的说明）——
          「用的人能不能读懂」本来就该按整张卡算，只查顶上那段反而是漏的。
        """
        from core import packs
        p = [x for x in packs.PACKS if x["id"] == "call"][0]
        desc = p["desc"]
        card = desc + " " + " ".join(
            (k.get("group") or "") + (k.get("label") or "") + (k.get("hint") or "")
            for k in p.get("keys", []))
        for jargon in ("Seeduplex", "instructions", "pip install", "WebSocket", "代理"):
            self.assertNotIn(jargon, card, "卡片上不该出现「%s」这种词" % jargon)
        # ★ 「API」只许作为对方控制台里那一项的**原名**出现（用户要照着去找），
        #   不许拿它解释功能 —— 跟下面「端到端」那条同一个道理。
        import re as _re
        self.assertEqual([], _re.findall(r"API(?! Key)", card),
                         "「API」只许作为对方控制台里那一项的原名（API Key）出现，"
                         "不许拿它解释功能")
        self.assertIn("插话", card, "用的人得读得懂「能插话」是什么")
        self.assertTrue(any(w in card for w in ("不用等他说完", "打断")),
                        "光说「插话」不够，得用大白话讲清是什么意思")
        # ★ 「端到端实时语音」是对方控制台里那一项的**原名**，用户要照着去找 ——
        #   所以允许出现，但必须是在**引用名字**（「叫…」），不能拿它来解释功能。
        if "端到端" in card:
            self.assertTrue("叫「端到端" in card or "「端到端实时语音」钥匙" in card
                            or "「新版控制台" in card,
                            "专有名词只能引用，不能拿来当解释")

    def test_missing_things_are_said_in_plain_words(self):
        for m in dx.check():
            self.assertNotIn("API Key（新版控制台 › API Key 管理）", m)
        self.assertTrue(any("钥匙" in m for m in dx.check()))


class TestErrorsAreActionable(Base):
    def test_401_points_at_the_right_key(self):
        m = dx.up_err(Exception("server rejected WebSocket connection: HTTP 401"))
        self.assertIn("新版控制台", m)
        self.assertIn("appid", m, "要说清楚跟语音合成那套不是一回事")
        self.assertNotIn("**", m)



class TestWhatGetsLanded(unittest.TestCase):
    """★ 0831 交接的待办②：通话的两条纪律原来嵌在 WS 连接里，一条都没法单独验。
    提成 should_land() 之后钉住它们。"""

    def test_normal_turn_lands(self):
        from optional.callkit.duplex import should_land
        ok, why = should_land(turn=3, cur_turn=3, gen_at_start=0, gen_now=0)
        self.assertTrue(ok, "没人打断、档案也没换 —— 该落")
        self.assertEqual("", why)

    def test_interrupted_does_not_land(self):
        """人又开口了：这一轮剩下的全部作废，一个字都不许念、不许落。"""
        from optional.callkit.duplex import should_land
        ok, why = should_land(turn=3, cur_turn=4, gen_at_start=0, gen_now=0)
        self.assertFalse(ok)
        self.assertIn("又开口", why)

    def test_archive_swapped_does_not_land(self):
        """说话期间档案被 replace 换了：这句是照旧档案说的，落进去就配错原文。"""
        from optional.callkit.duplex import should_land
        ok, why = should_land(turn=3, cur_turn=3, gen_at_start=0, gen_now=1)
        self.assertFalse(ok)
        self.assertIn("档案", why)

    def test_interrupt_wins_over_archive(self):
        """两条同时破：先报打断（那是人的动作，更该让人看懂）。"""
        from optional.callkit.duplex import should_land
        ok, why = should_land(turn=3, cur_turn=9, gen_at_start=0, gen_now=7)
        self.assertFalse(ok)
        self.assertIn("又开口", why)


if __name__ == "__main__":
    unittest.main()


class TestBothSidesSpeakTheSameEvents(unittest.TestCase):
    """★ 0831 外部验收 P0-01：中继发的是 `lianhuan.listening/heard/said/audio/spoken`，
    主页面却还在等豆包的**原始协议事件**（`conversation.item.*` / `response.output_*`）——
    对账下来：后端 5 种业务事件，主页面显式处理 **0 种**。

    后果不是「全坏」，所以更难发现：声音链是通的（`duplex.js` 认 audio/listening/spoken），
    但**你说的话和他说的字幕一个都不显示**。真机上表现为「转录没有」。

    这条就是那张对账表 —— 谁改了一边的事件名，另一边没跟上，它当场红。
    """

    def _names(self, path, pat=r"lianhuan\.[a-z]+"):
        import re
        from pathlib import Path as _P
        root = _P(__file__).resolve().parent.parent
        p = root / path
        if not p.exists():
            self.skipTest("这份产物里没装：" + path)
        return set(re.findall(pat, p.read_text(encoding="utf-8")))

    def test_every_event_the_relay_sends_is_handled_somewhere(self):
        sent = self._names("optional/callkit/duplex.py")
        page = self._names("core/web/index.html")
        audio = self._names("optional/callkit/web/duplex.js")
        handled = page | audio
        missing = sorted(sent - handled)
        self.assertEqual([], missing,
                         "中继发了这些事件，但页面和音频层都没人接：%s" % missing)

    def test_the_page_does_not_wait_for_events_nobody_sends(self):
        page = self._names("core/web/index.html")
        sent = self._names("optional/callkit/duplex.py")
        js = self._names("optional/callkit/web/duplex.js")
        # open/close 是音频层自己造的，不由中继发
        own = {"lianhuan.open", "lianhuan.close"}
        ghosts = sorted(page - sent - own)
        self.assertEqual([], ghosts,
                         "页面在等这些事件，可没有人会发：%s" % ghosts)

    def test_the_page_no_longer_waits_for_the_raw_upstream_protocol(self):
        from pathlib import Path as _P
        f = _P(__file__).resolve().parent.parent / "core/web/index.html"
        if not f.exists():
            self.skipTest("这份产物里没装：core/web/index.html")
        h = f.read_text(encoding="utf-8")
        i = h.index("DXL.dx = Duplex({on:")
        seg = h[i:i + 1800]
        for dead in ("conversation.item.input_audio_transcription",
                     "response.output_text.done", "response.output_audio."):
            self.assertNotIn(dead, seg,
                             "还在等上游原始事件 %s —— 中继不会发它，这是死分支" % dead)
