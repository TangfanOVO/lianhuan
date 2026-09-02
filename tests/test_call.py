"""通话：按语言挑引擎，以及把 401 说成人话。

★ 不碰网络。这里验的是「怎么挑」和「怎么说错」，不是真去合成。
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import secrets                                   # noqa: E402
from optional.callkit import routes as call                 # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.old = os.environ.get("LIANHUAN_DB")
        os.environ["LIANHUAN_DB"] = str(Path(self.dir) / "x.db")
        for k in ("ELEVENLABS_API_KEY", "VOLC_TTS_APPID", "VOLC_TTS_TOKEN",
                  "TTS_PROVIDER", "CALL_LANG"):
            os.environ.pop(k, None)

    def tearDown(self):
        if self.old is None:
            os.environ.pop("LIANHUAN_DB", None)
        else:
            os.environ["LIANHUAN_DB"] = self.old

    def give(self, **kv):
        secrets.set_many(kv)


class TestPickByLanguage(Base):
    """★ 界面上问的是语言，不是厂商 —— 用的人不该关心底下接的是谁。"""

    def test_chinese_prefers_volc_english_prefers_eleven(self):
        self.assertEqual(["volc", "eleven"], call._order("zh"))
        self.assertEqual(["eleven", "volc"], call._order("en"))

    def test_default_language_is_chinese(self):
        self.assertEqual("zh", call.lang())

    def test_language_can_be_switched(self):
        self.give(CALL_LANG="en")
        self.assertEqual("en", call.lang())
        self.give(CALL_LANG="zh-CN")
        self.assertEqual("zh", call.lang())

    def test_an_explicit_provider_still_wins(self):
        """谁在环境变量里写死了哪家，照他的来 —— 别硬把人掰回去。"""
        self.give(TTS_PROVIDER="eleven")
        self.assertEqual(["eleven", "volc"], call._order("zh"))


class TestHonestAboutWhoSpeaks(Base):
    def test_with_only_one_vendor_both_languages_point_at_it(self):
        """★ 只贴了一家时，两种语言都走那家 —— 这件事必须报出来。
        人选了「英文」却不知道底下没接，那就是界面在骗他。"""
        self.give(VOLC_TTS_APPID="a", VOLC_TTS_TOKEN="b")
        v = call.voices()
        self.assertEqual("volc", v["zh"])
        self.assertEqual("volc", v["en"], "只有豆包时英文也只能走豆包，不许装作有得选")
        self.assertFalse(v["eleven"])

    def test_with_both_each_language_gets_its_own(self):
        self.give(ELEVENLABS_API_KEY="sk-x", VOLC_TTS_APPID="a", VOLC_TTS_TOKEN="b")
        v = call.voices()
        self.assertEqual("volc", v["zh"])
        self.assertEqual("eleven", v["en"])

    def test_with_nothing_it_says_nothing(self):
        v = call.voices()
        self.assertIsNone(v["zh"])
        self.assertIsNone(v["en"])


class TestBadlyPastedKey(Base):
    """回归：key 里混进中文/全角字符时，httpx 会抛 `'ascii' codec can't encode` ——
    那句话对用的人毫无意义，他只会以为是程序坏了。"""

    def test_non_ascii_key_is_caught_with_words_a_human_can_act_on(self):
        self.give(ELEVENLABS_API_KEY="sk-这里混进了中文")
        with self.assertRaises(RuntimeError) as e:
            call._eleven_key()
        m = str(e.exception)
        self.assertIn("重新建一把", m)
        self.assertIn("复制", m)
        self.assertNotIn("codec", m, "别把 Python 的报错原样甩给人看")

    def test_a_clean_key_passes_through(self):
        self.give(ELEVENLABS_API_KEY="sk-abc123")
        self.assertEqual("sk-abc123", call._eleven_key())


class TestElevenErrorsAreActionable(Base):
    """回一个「401」等于没说。把该查的摆出来 —— 下面这几条是真踩出来的。"""

    def test_401_names_the_three_real_causes(self):
        m = call._eleven_err(401, "")
        self.assertIn("复制", m)            # 「复制」按钮拿到的可能是残的
        self.assertIn("创建", m)            # key 只在创建那次完整显示
        self.assertIn("权限", m)            # 权限没勾全一样 401
        for perm in ("Voices read", "Text to Speech", "Speech to Text"):
            self.assertIn(perm, m, "没写清整条电话链要哪几项权限")

    def test_400_is_also_a_key_problem_and_carries_upstream_words(self):
        """★ 真撞出来的：复制不全时 ElevenLabs 回的是 **400** 不是 401，
        而且它自己会说「API key must be exactly N characters」——
        那句话比我们说十句都准，要原样带出去。"""
        body = '{"detail":{"type":"authentication_error","code":"invalid_api_key",' \
               '"message":"API key must be exactly 51 characters, got 55."}}'
        m = call._eleven_err(400, body)
        self.assertIn("51 characters", m, "上游那句最准的话被吃掉了")
        self.assertIn("复制不全", m)
        self.assertIn("重新建一把", m)

    def test_messages_carry_no_markdown_asterisks(self):
        """这些字直接显示在界面上，星号会原样露出来（机器人那页栽过一次）。"""
        for m in (call._eleven_err(400, '{"detail":{"message":"API key must be exactly 51"}}'),
                  call._eleven_err(401, ""), call._eleven_err(403, ""), call._eleven_err(429, "")):
            self.assertNotIn("**", m)

    def test_401_says_not_to_go_hunting_the_ip_allowlist(self):
        """白名单不匹配是 403。不说这一句，人会对着白名单查半天。"""
        self.assertIn("403", call._eleven_err(401, ""))

    def test_403_and_429_have_their_own_words(self):
        self.assertIn("白名单", call._eleven_err(403, ""))
        self.assertIn("频繁", call._eleven_err(429, ""))

    def test_other_codes_still_carry_the_body(self):
        self.assertIn("teapot", call._eleven_err(418, "i am a teapot"))




class TestToneAndTags(unittest.TestCase):
    """写在文本里的神态 → 真的语气。

    ★ 两条路，因为两类引擎吃的东西不一样：
      认标签的（ElevenLabs v3）走 `[sighs]`；不认的走语速/音量/音调三个数。
      **给不认标签的引擎留方括号 ＝ 它会把「[sighs]」念出来。**
    """

    def test_v3_gets_tags_others_get_them_stripped(self):
        from core import speech
        raw = "「叹了口气」我知道了。"
        v3, _ = speech.for_engine(raw, "eleven_v3")
        v2, _ = speech.for_engine(raw, "eleven_multilingual_v2")
        self.assertIn("[sighs]", v3)
        self.assertNotIn("[", v2, "不认标签的引擎会把方括号念出来")
        self.assertIn("我知道了", v2, "神态剥掉了，但话不能跟着没了")

    def test_unmappable_gestures_are_dropped_not_faked(self):
        """★ 映射不到的照旧丢掉，绝不硬凑 —— 凑错了它会照着演，比不演更怪。"""
        from core import speech
        out, _ = speech.for_engine("「把书放回架上」好。", "eleven_v3")
        self.assertNotIn("把头埋", out)
        self.assertNotIn("[", out)
        self.assertIn("好", out)

    def test_tone_marker_becomes_numbers(self):
        from core import speech
        text, p = speech.for_engine("〔tone:重话〕这次真的不行。", "volc")
        self.assertNotIn("tone", text)
        self.assertEqual(-28, p["speed"], "说重话要最慢")
        self.assertLess(p["loudness"], 0, "说重话要压低，不是拔高")

    def test_english_star_gestures_translate_too(self):
        from core import speech
        out, _ = speech.for_engine("*whispers* come here.", "eleven_v3")
        self.assertIn("[whispers]", out)

    def test_the_mood_marker_is_never_spoken_aloud(self):
        """★ 0901 抓到的：‹心情 …› 是**记账用的**，从来不是要说出口的话。

        文字聊天那条路上 apply_marker 会先把它抠走，所以一直没人发现这儿漏了 ——
        电话那条路不走 apply_marker，于是它被原样念了出来（字幕上也是原文）。
        「不许念出口」对哪条路都成立，所以钉在 speech 这一层，不由调用方各记各的。
        """
        from core import speech
        for engine in ("volc", "eleven_v3", "eleven_flash_v2_5", "duplex"):
            out, _ = speech.for_engine("我在这儿呢。‹心情 开心+5:聊到很晚›", engine)
            self.assertNotIn("心情", out, engine + "：记号被念出去了")
            self.assertNotIn("‹", out, engine + "：尖括号漏出去了")
            self.assertNotIn("+5", out, engine + "：分数被念出去了")
            self.assertIn("我在这儿呢", out, engine + "：正文不该被一起吃掉")

    def test_the_call_path_still_books_that_mood(self):
        """不念出口是一半，另一半是**得记上** —— 电话里记的心情原来永不入账。"""
        src = (Path(__file__).resolve().parent.parent
               / "optional/callkit/duplex.py").read_text(encoding="utf-8")
        i = src.find('whole = "|||".join(buf)')
        self.assertGreater(i, 0, "落库那一段不见了")
        seg = src[i:i + 900]
        self.assertIn("apply_marker", seg, "落库之前要把心情抠出来记账")
        self.assertIn("untrusted", seg,
                      "口径要跟文字那边一样：对方的话里也带了记号就整轮不记账")

    def test_split_marker_becomes_a_pause_not_three_bars(self):
        from core import speech
        out, _ = speech.for_engine("我在。|||你睡吧。", "volc")
        self.assertNotIn("|||", out)
        self.assertIn("。", out)

    def test_volc_gets_ratios_not_raw_numbers(self):
        """上游要的是倍率（1.0 ＝ 正常），我们内部是 -50~100 的相对值。"""
        from optional.callkit import routes as call
        from core import speech
        _, p = speech.for_engine("〔tone:哄〕乖。", "volc")
        self.assertEqual(round(1 + p["speed"] / 100, 3), 0.78)


if __name__ == "__main__":
    unittest.main()


class TestCallsDoNotPayForThinkingNobodySees(unittest.TestCase):
    """★ 0831（顺着「打电话慢是不是每句注入太多」这个疑问查出来的）：

    `think_line` 原来是**无条件**加的 —— 打电话时也要求模型「每一轮先把心里想的写在最开头」。
    但通话时：① 人在听声音，思考面板根本看不到 ② 全双工那条路更浪费，
    中继只收 `SAY`，那段内心独白**生成完直接丢掉** ③ 而人得等它写完才听得到第一个字。

    照原项目的做法（那边通话把思考深度降一档，原话「听声不看想法，可以 low」）：
    通话不要这一段，**文字聊天一个字不动**（思考链一直得在）。
    """

    def _store(self):
        import tempfile, os
        from core.store.sqlite import SqliteStore
        return SqliteStore(os.path.join(tempfile.mkdtemp(), "t.db"))

    def test_text_chat_still_asks_for_the_inner_voice(self):
        from core.memory.recall import build_injection
        inj = build_injection(self._store(), "在吗")
        self.assertIn("心里真实想的", inj, "文字聊天的思考链不许被顺手砍掉")

    def test_a_call_does_not(self):
        from core.memory.recall import build_injection
        inj = build_injection(self._store(), "喂", here="call")
        self.assertNotIn("心里真实想的", inj,
                         "通话还在要求写内心独白 —— 没人看得到，纯等它写完")

    def test_the_duplex_relay_would_have_thrown_it_away_anyway(self):
        """佐证：中继那条路只收 SAY，写了也是丢掉。"""
        import re
        from pathlib import Path
        p = Path(__file__).resolve().parent.parent / "optional/callkit/duplex.py"
        if not p.exists():
            self.skipTest("这份产物里没装：optional/callkit")
        src = p.read_text(encoding="utf-8")
        self.assertRegex(src, r'if d\.get\("type"\) != SAY:\s*\n\s*continue',
                         "中继要是改成也收 THINK 了，上面那条判断就得重想")
