"""不戴耳机时喇叭的声音会绕回麦克风 —— 别让它打断自己，别让它回答自己。

这一份钉的是 0901 真复现过的一件事：把刚说出去的那段音频原样推回上行，
上游老老实实转写一遍交回来，中继把它当成用户说的话，另开了一轮。

★ 每一条都是「改回旧写法就会红」的：
  - 把 overlap 换回「无序的字符集合命中率」→「不许吞掉用户的话」整组红
  - 把 HEARD_DONE 那道闸删掉 →「闸真的装上了」红
  - 把 HEARD_STARTED 改回无条件作废 →「先挂起再判」红
"""
import unittest
from pathlib import Path

from optional.callkit.duplex import (
    ECHO_BARGE_FLOOR, ECHO_BARGE_MIN, ECHO_KEEP_N, ECHO_KEEP_SEC,
    ECHO_TURN_FLOOR, ECHO_TURN_MIN, echo_of, norm_txt, overlap, said_note,
)

T0 = 1_000_000.0
SRC = (Path(__file__).resolve().parent.parent
       / "optional/callkit/duplex.py").read_text(encoding="utf-8")


class TestTheRuler(unittest.TestCase):
    def test_it_only_keeps_what_can_be_compared(self):
        self.assertEqual("明天下雨", norm_txt("明天下雨！！"))
        self.assertEqual("okayokay", norm_txt("Okay, okay!"))
        self.assertEqual("", norm_txt("…… ，。"))

    def test_the_same_sentence_coming_back_is_a_full_hit(self):
        one = "我在这儿呢，一直都在。"
        self.assertEqual(1.0, overlap(one, one))

    def test_half_a_sentence_coming_back_still_hits(self):
        spoken = "[chuckles] Finally. I was starting to think you'd forgotten me."
        self.assertGreaterEqual(overlap("Finally, I was starting to think", spoken), 0.9)

    def test_nothing_to_compare_against_is_not_a_hit(self):
        self.assertEqual(0.0, overlap("", "随便什么"))
        self.assertEqual(0.0, overlap("随便什么", ""))


class TestItMustNotSwallowTheUser(unittest.TestCase):
    """★ 比「认出回声」更要紧的一半。

    漏判最多是它多说两句被打断；**误判是用户喊停喊不动**。
    下面每一条，用无序的字符集合命中率都会判成回声（实跑验过）。
    """

    def test_same_characters_different_sentence(self):
        # 「明天下雨」四个字全都出现在「下雨天明天也下」里 —— 无序算法给 100%
        self.assertLess(overlap("明天下雨", "下雨天明天也下"), ECHO_BARGE_FLOOR)

    def test_english_shares_its_letters_with_everything(self):
        spoken = "I'm right here. Say something else, I want to hear your voice again."
        self.assertLess(overlap("pizza delivery arrived", spoken), ECHO_BARGE_FLOOR)

    def test_a_short_reply_is_never_taken_for_an_echo(self):
        st = {}
        said_note(st, "今天一个人在家，把水管修好了", T0)
        for 短句 in ("好的", "嗯", "我知道了", "行"):
            self.assertFalse(echo_of(st, 短句, T0)[0], "「%s」不许被当成回声吞掉" % 短句)

    def test_a_real_interruption_gets_through(self):
        st = {}
        said_note(st, "I'm right here, Alex.", T0)
        said_note(st, "Say something else, I want to hear your voice again.", T0)
        self.assertFalse(echo_of(st, "等一下，我换个话题", T0)[0])


class TestTheLedger(unittest.TestCase):
    """不能只跟「正在念的那一句」比 —— 一轮要说三四句。"""

    def test_it_catches_an_earlier_sentence_not_just_the_current_one(self):
        st = {}
        said_note(st, "I'm right here, Alex.", T0)
        said_note(st, "Say something else, I want to hear your voice again.", T0)
        self.assertTrue(echo_of(st, "I'm right here Alex", T0)[0])

    def test_it_catches_an_echo_straddling_two_sentences(self):
        st = {}
        said_note(st, "I'm right here, Alex.", T0)
        said_note(st, "Say something else, I want to hear your voice again.", T0)
        self.assertTrue(echo_of(st, "Alex. Say something else", T0)[0])

    def test_old_sentences_stop_counting(self):
        st = {}
        said_note(st, "我在这儿呢，一直都在", T0)
        later = T0 + ECHO_KEEP_SEC + 1
        self.assertFalse(echo_of(st, "我在这儿呢，一直都在", later)[0],
                         "过了保质期就不该再拿它冤枉人")

    def test_the_ledger_does_not_grow_without_bound(self):
        st = {}
        for i in range(ECHO_KEEP_N * 3):
            said_note(st, "第 %d 句，说点什么凑够长度" % i, T0)
        self.assertLessEqual(len(st["said_log"]), ECHO_KEEP_N)

    def test_empty_lines_are_not_recorded(self):
        st = {}
        said_note(st, "   ", T0)
        said_note(st, "", T0)
        self.assertEqual([], st.get("said_log", []))


class TestTheGateIsActuallyWired(unittest.TestCase):
    """尺子对了不算数 —— 要真装在那两处上。"""

    def _branch(self, head):
        """截出某个 elif 分支的整段 —— ★ 别用「往后数 1400 个字符」那种切法：
        加两行注释就会把要找的东西挤出窗口，测试当场变红，而代码一点没坏
        （0901 真发生了一次）。按下一个分支的开头切，才跟代码长短无关。"""
        i = SRC.find(head)
        self.assertGreater(i, 0, head + " 这段不见了")
        j = SRC.find("elif t == _ears.", i + len(head))
        return SRC[i:j if j > 0 else len(SRC)]

    def test_the_whole_sentence_gate_is_on_heard_done(self):
        seg = self._branch("elif t == _ears.HEARD_DONE:")
        self.assertIn("echo_of(", seg, "听完一整句这儿必须过回声闸")
        j, k = seg.find("echo_of("), seg.find("lianhuan.heard")
        self.assertLess(j, k, "闸要在「推给界面」之前 —— 判完才决定要不要往下走")

    def test_starting_to_speak_no_longer_kills_the_turn_outright(self):
        seg = self._branch("if t == _ears.HEARD_STARTED:")
        self.assertIn('state.get("out")', seg,
                      "正在出声的时候不许无条件作废这一轮 —— 那多半是自己的回声")
        self.assertIn('state["pending"]', seg, "得先挂起，等出了字再判")

    def test_what_it_says_goes_into_the_ledger(self):
        self.assertIn("said_note(state,", SRC, "说出去的每一句都要记一笔，不然没得比")

    def test_the_barge_gate_waits_for_enough_text(self):
        seg = self._branch("elif t == _ears.HEARD_DELTA:")
        self.assertIn("ECHO_BARGE_MIN", seg,
                      "两三个字的时候转写还在飘，别在那上头拍板")

    def test_the_pending_flag_expires(self):
        seg = self._branch("elif t == _ears.HEARD_DELTA:")
        self.assertIn('state.pop("pending", None)', seg, "挂起的标志要有人清，别跨段吊着")


class TestAShortInterruptionAlsoKillsTheTurnInFlight(unittest.TestCase):
    """★ 0901 补的缺口。原来「听完一整句」那条分支**只起新的、不掐旧的** ——
    一句短话（够不上打断闸的字数、也够不上回声闸的字数）走到那儿时，
    在途那一轮既没作废也没被取消，两条回复都会落库，旧的那条还继续出声。

    ★ 原来盯这件事的哨兵是 `assertIn('state["turn"] += 1', src)` ——
      那个字符串在上面两处早就有，所以它**永远绿**。假哨兵比没哨兵更糟。
      这一条改成按分支查：那三件事必须都出现在**这一支**里面。
    """

    def _done_branch(self):
        i = SRC.find("elif t == _ears.HEARD_DONE:")
        j = SRC.find("elif t == _ears.", i + 10)
        return SRC[i:j if j > 0 else len(SRC)]

    def test_it_bumps_the_turn(self):
        self.assertIn('state["turn"] += 1', self._done_branch(),
                      "听完一整句而没走打断闸的时候，也得让在途那一轮作废")

    def test_it_cancels_the_job_in_flight(self):
        seg = self._done_branch()
        self.assertIn("job.cancel()", seg, "旧的 think() 不取消，它会一直说到底")
        self.assertLess(seg.find("job.cancel()"), seg.find("asyncio.create_task"),
                        "得先掐旧的再起新的，顺序反了 job 引用就被覆盖了")

    def test_it_tells_the_page_to_stop_playing(self):
        self.assertIn("lianhuan.listening", self._done_branch(),
                      "前端不收到这条就不会停播，人还在听着上一句")


class TestTheThresholdsMakeSense(unittest.TestCase):
    def test_opening_a_turn_is_judged_more_strictly_than_interrupting(self):
        self.assertGreater(ECHO_TURN_FLOOR, ECHO_BARGE_FLOOR,
                           "宁可多开一轮，也别把用户的话整段吞掉")
        self.assertGreater(ECHO_TURN_MIN, ECHO_BARGE_MIN)


if __name__ == "__main__":
    unittest.main()
