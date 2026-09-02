"""颜文字抽屉：AI 也得能挑、能收。

在这之前抽屉只有人点得动 —— 网页上收藏、删除、拖分类全是手指的活，
AI 这头一只手都没有：对方发来一枚新的，看过就没了，下次还是只能从老的里头挑。

★ 每一条都是「把那只手拿掉就会红」的。
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BAD = "(\u0001)"          # 控制字符，传不过去的那种


def _fresh():
    """一个**真的空**抽屉，落在临时目录里 —— 绝不许写进真的 data/。

    ★ 不能只指个空目录：没文件时 _read() 会拿组件自带的 325 条种子铺底，
      那样「新收一枚」会撞上种子里本来就有的，测的就不是收这件事了。
    """
    import importlib
    import json
    d = tempfile.mkdtemp()
    os.environ["LIANHUAN_DB"] = os.path.join(d, "t.db")
    f = Path(d) / "kaomoji_v2.json"
    f.write_text(json.dumps({"version": 4, "items": [], "removed": [], "categoryOrder": []}),
                 encoding="utf-8")
    from optional.kaomoji_drawer import routes as kao
    importlib.reload(kao)
    return kao, f


class TestItCanTakeANewOne(unittest.TestCase):
    def setUp(self):
        self.kao, self.f = _fresh()

    def test_one_kaomoji_lands_with_its_categories(self):
        r = self.kao.collect({"value": "(\u0e51>\u0602<\u0e51)", "categories": ["害羞", "可爱"]})
        self.assertEqual(1, len(r["收了"]))
        it = self.kao._find(self.kao._read(), r["收了"][0])
        self.assertEqual(["害羞", "可爱"], it["categories"])
        self.assertEqual("stable", it["compatibility"])

    def test_a_whole_pile_at_once(self):
        r = self.kao.collect([{"value": "(≧▽≦)", "categories": ["开心"]},
                              {"value": "(╥﹏╥)", "categories": ["哭哭"]},
                              {"value": "( ˘ ³˘)", "categories": ["亲亲"]}])
        self.assertEqual(3, len(r["收了"]))

    def test_the_same_one_twice_is_not_stored_twice(self):
        self.kao.collect({"value": "(≧▽≦)", "categories": ["开心"]})
        r = self.kao.collect({"value": "(≧▽≦)", "categories": ["开心"]})
        self.assertEqual(["(≧▽≦)"], r["本来就有"])
        self.assertEqual(1, len([i for i in self.kao._read()["items"] if i["value"] == "(≧▽≦)"]))

    def test_the_same_one_can_gain_a_category(self):
        self.kao.collect({"value": "(≧▽≦)", "categories": ["开心"]})
        r = self.kao.collect({"value": "(≧▽≦)", "categories": ["可爱"]})
        self.assertEqual(["(≧▽≦)"], r["给旧的补了分类"])
        self.assertEqual(["开心", "可爱"], self.kao._find(self.kao._read(), "(≧▽≦)")["categories"])

    def test_no_category_still_gets_kept(self):
        """★ 归不出类也不许丢 —— 丢了就违背「偶尔发一个新的也能被记住」这件事本身。"""
        r = self.kao.collect("(´･_･`)")
        self.assertEqual(["(´･_･`)"], r["收了"])
        self.assertEqual(["未分类"], self.kao._find(self.kao._read(), "(´･_･`)")["categories"])
        self.assertIn("提醒", r)

    def test_it_tells_you_what_categories_exist(self):
        """归类得有个词表可选，不然只会一路「未分类」。"""
        self.kao.collect({"value": "(≧▽≦)", "categories": ["开心"]})
        r = self.kao.collect({"value": "(*´∀`*)", "categories": ["开心"]})
        self.assertIn("开心", r["现有分类"])


class TestWhatItRefuses(unittest.TestCase):
    def setUp(self):
        self.kao, self.f = _fresh()

    def test_what_was_deleted_never_comes_back(self):
        """★ 对方亲手删掉的，AI 不许再塞回来 —— removed 那张名单就是为这个存在的。"""
        st = self.kao._read()
        st["removed"] = ["(≧▽≦)"]
        self.kao._write(st)
        r = self.kao.collect({"value": "(≧▽≦)", "categories": ["开心"]})
        self.assertEqual([], r["收了"])
        self.assertEqual(["(≧▽≦)"], r["删过所以没收"])
        self.assertIsNone(self.kao._find(self.kao._read(), "(≧▽≦)"))

    def test_characters_that_cannot_travel_are_refused(self):
        r = self.kao.collect({"value": BAD, "categories": ["开心"]})
        self.assertEqual([], r["收了"])
        self.assertTrue(r["没收进去"])
        self.assertIsNone(self.kao._find(self.kao._read(), BAD))

    def test_stacked_marks_are_kept_but_flagged(self):
        """叠加符号多的照收 —— 很多好看的本来就带组合符号；抽屉自己会标出来。"""
        v = "\u1421\u02c3\u0335\u0348 \u1d17 \u02c2\u0335\u0348\u1421"
        r = self.kao.collect({"value": v, "categories": ["可爱"]})
        self.assertEqual(1, len(r["收了"]))
        it = self.kao._find(self.kao._read(), r["收了"][0])
        self.assertIn(it["compatibility"], ("limited", "stable"))

    def test_empty_gets_nothing_and_says_so(self):
        self.assertFalse(self.kao.collect([])["ok"])


class TestItCanPickOneBack(unittest.TestCase):
    def setUp(self):
        self.kao, self.f = _fresh()

    def test_pick_returns_something_from_that_category(self):
        self.kao.collect([{"value": "(≧▽≦)", "categories": ["开心"]},
                          {"value": "(*´∀`*)", "categories": ["开心"]}])
        got = self.kao.pick("开心", 1)
        self.assertEqual(1, len(got["颜文字"]))
        self.assertIn(got["颜文字"][0], ["(≧▽≦)", "(*´∀`*)"])

    def test_an_unknown_category_hands_back_the_list(self):
        """挑不到不能只说「没有」—— 得把有哪些告诉它，不然它只能瞎猜。"""
        self.kao.collect({"value": "(≧▽≦)", "categories": ["开心"]})
        r = self.kao.pick("不存在的分类")
        self.assertIn("err", r)
        self.assertIn("开心", r["现有分类"])

    def test_picking_counts_as_using(self):
        self.kao.collect({"value": "(≧▽≦)", "categories": ["开心"]})
        self.kao.pick("开心")
        self.assertEqual(1, self.kao._find(self.kao._read(), "(≧▽≦)")["useCount"])


class TestTheHandsAreActuallyWired(unittest.TestCase):
    """底座对了不算数 —— 引擎那头要真拿得到这两只手。"""

    def test_both_hands_are_declared(self):
        from core import hands
        names = [t["function"]["name"] for t in hands.TOOLS]
        self.assertIn("collect_kaomoji", names)
        self.assertIn("pick_kaomoji", names)

    def test_execute_routes_to_the_drawer(self):
        import asyncio
        _fresh()
        from core import hands
        r = asyncio.run(hands.execute("collect_kaomoji",
                                      {"value": "(≧▽≦)", "categories": ["开心"]}))
        self.assertEqual(["(≧▽≦)"], r["收了"])
        r2 = asyncio.run(hands.execute("pick_kaomoji", {"category": "开心"}))
        self.assertEqual(["(≧▽≦)"], r2["颜文字"])

    def test_collecting_nothing_is_refused_not_silently_ok(self):
        import asyncio
        _fresh()
        from core import hands
        r = asyncio.run(hands.execute("collect_kaomoji", {}))
        self.assertFalse(r["ok"])


if __name__ == "__main__":
    unittest.main()
