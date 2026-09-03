"""每一条出产物的流水线都要过隐私闸。

★ 这条钉的是**接线**，不是扫描器本身：扫描器写得再好，没人调它就等于没有。
  （0903 的验收就是这么指出来的：CI 只跑形状扫描，私人词表那半从来没参与过。）
"""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
WF = ROOT / ".github" / "workflows"
ACTION = ROOT / ".github" / "actions" / "privacy-gate" / "action.yml"

#: 会把东西送出门的流水线。新增一条就往这儿加一行 —— 加不加得上是这条测试逼出来的。
PUBLISHING = ["pages.yml", "android.yml", "android-full.yml", "docker.yml", "ci.yml"]


@unittest.skipUnless(WF.exists(), "create.py 的产物不带 .github/，这条只在源码仓库里跑")
class TestPrivacyGateWiring(unittest.TestCase):
    def test_gate_action_exists_and_takes_markers_from_a_secret(self):
        self.assertTrue(ACTION.exists(), "隐私闸那个复合 action 不在")
        a = ACTION.read_text(encoding="utf-8")
        self.assertIn("LIANHUAN_PRIVATE_MARKERS", a)
        self.assertIn("PUBLIC_RELEASE=1", a, "配了词表就得走发布模式")

    def test_every_publishing_workflow_goes_through_the_gate(self):
        for name in PUBLISHING:
            y = (WF / name).read_text(encoding="utf-8")
            self.assertIn("actions/privacy-gate", y, name + " 没过隐私闸")
            self.assertIn("secrets.LIANHUAN_PRIVATE_MARKERS", y, name + " 没把词表传进去")

    def test_marker_list_is_never_written_into_the_repo(self):
        """★ 把要藏的东西列个清单贴在门口，本身就是泄露。词表只能走 Secret。"""
        for name in PUBLISHING:
            y = (WF / name).read_text(encoding="utf-8")
            for line in y.splitlines():
                if "LIANHUAN_PRIVATE_MARKERS" in line and "secrets." not in line:
                    self.fail(f"{name} 里像是写死了词表：{line.strip()}")

    def test_clean_copy_is_scanned_too(self):
        """真正会发出去的是 create.py 的产物，那一份也得扫。"""
        y = (WF / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("root: ${{ env.CLEAN_COPY }}", y)


if __name__ == "__main__":
    unittest.main()


class TestEndToEndCoverage(unittest.TestCase):
    """★ 合同测试证明不了「真浏览器里能用」。这条钉住那一层验收还在。"""

    def test_browser_version_has_a_real_browser_check(self):
        spec = ROOT / "apps" / "local" / "e2e" / "browser-version.spec.mjs"
        self.assertTrue(spec.exists(), "浏览器版的端到端验收不在了")
        s = spec.read_text(encoding="utf-8")
        for must in ("__lianhuanLocal", "api/hist", "reload", "--kb"):
            self.assertIn(must, s, "端到端里少了 " + must)
        # 只查真用了没（注释里提到这两个名字是为了说明**为什么不用**）
        self.assertNotIn("bypassCSP:", s, "开了 bypassCSP 就验不到 CSP 有没有拦掉自己人")
        self.assertNotIn("page.waitForFunction(", s, "它走 eval，会被这一版的 CSP 拦下")

    def test_e2e_runs_in_ci(self):
        y = (WF / "e2e.yml").read_text(encoding="utf-8")
        self.assertIn("playwright test", y)
        self.assertIn("check-provider-cors.mjs", y, "各家还让不让直连，也该有人盯着")
