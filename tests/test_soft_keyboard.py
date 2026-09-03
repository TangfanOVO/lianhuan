"""软键盘：输入框和最后一条消息不许被键盘盖住。

★ 为什么要有这几条：这一份前端被四个壳共用（网页 PWA、iOS 加主屏、安卓壳、安卓完整体）。
  iOS 上键盘**不改**布局视口 —— 100dvh 一动不动，而输入条是贴着 .app 底边绝对定位的，
  于是整条被盖住。安卓的 adjustResize 只能覆盖其中一部分，靠它不够。
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def app_html() -> str:
    return (ROOT / "core" / "web" / "index.html").read_text(encoding="utf-8")


class TestSoftKeyboard(unittest.TestCase):
    def setUp(self):
        self.h = app_html()

    def test_viewport_asks_the_browser_to_resize_content(self):
        m = re.search(r'<meta name="viewport" content="([^"]+)"', self.h)
        self.assertIsNotNone(m)
        self.assertIn("interactive-widget=resizes-content", m.group(1))

    def test_app_height_subtracts_the_keyboard(self):
        """两条 .app 高度（手机的 100dvh、宽屏的 min(...)）都要扣掉 --kb。"""
        heights = re.findall(r"height:\s*(calc\([^;]*dvh[^;]*\))", self.h)
        self.assertGreaterEqual(len(heights), 2, "找不到 .app 的两条高度：" + str(heights))
        for hh in heights:
            self.assertIn("--kb", hh, "这条高度没扣键盘：" + hh)

    def test_keyboard_inset_comes_from_visual_viewport(self):
        self.assertIn("visualViewport", self.h)
        self.assertIn("--kb", self.h)
        self.assertIn("kb-open", self.h)

    def test_zoom_is_not_mistaken_for_a_keyboard(self):
        """双指放大也会让 visualViewport 变矮 —— 那不是键盘，扣了就白掉一块。"""
        self.assertRegex(self.h, r"vv\.scale\s*>\s*1", "没有排掉缩放")

    @unittest.skipUnless((ROOT / "app" / "index.html").exists(),
                         "create.py 的产物不带 app/，这条只在源码仓库里跑")
    def test_both_copies_stay_identical(self):
        """app/index.html 是 core/web/index.html 的副本，CI 里 diff 钉着，这儿也钉一道。"""
        other = (ROOT / "app" / "index.html").read_text(encoding="utf-8")
        self.assertEqual(self.h, other, "两份前端漂开了")


if __name__ == "__main__":
    unittest.main()
