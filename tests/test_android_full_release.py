"""完整体的发布形状。★ 这几条钉的是**数据事故**，不是功能。

完整体的家在应用沙箱里，所以三件事必须一直成立：
  · 版本号每次能递增（不然装不上去）
  · 有钥匙就出正式签名包（签名固定 = 能覆盖升级 = 数据留着）
  · 文档不许再教人「先卸载旧的」—— 那句话在完整体上等于「把家删了」
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
AF = ROOT / "android-full"


@unittest.skipUnless(AF.exists(), "create.py 的产物不带 android-full/，这条只在源码仓库里跑")
class TestAndroidFullRelease(unittest.TestCase):
    def setUp(self):
        self.gradle = (AF / "app" / "build.gradle").read_text(encoding="utf-8")
        self.wf = (ROOT / ".github" / "workflows" / "android-full.yml").read_text(encoding="utf-8")
        self.manifest = (AF / "app" / "src" / "main" / "AndroidManifest.xml").read_text(encoding="utf-8")

    def test_version_code_is_not_pinned_to_one(self):
        """写死 versionCode 1 的包，第二次打出来装不上去。"""
        self.assertNotRegex(self.gradle, r"versionCode\s+1\b", "versionCode 不许写死")
        self.assertIn("LH_VERSION_CODE", self.gradle)
        self.assertIn("LH_VERSION_CODE: ${{ github.run_number }}", self.wf, "CI 要传一个每次递增的号")

    def test_release_signing_config_exists(self):
        """有 keystore 就得出正式签名包 —— 签名固定才能覆盖升级，才不丢数据。"""
        self.assertIn("signingConfigs", self.gradle)
        self.assertIn("LH_KEYSTORE", self.gradle)
        self.assertIn("signingConfig signingConfigs.release", self.gradle)
        self.assertIn("ANDROID_KEYSTORE_BASE64", self.wf, "钥匙要从 Actions Secrets 来")
        self.assertIn("assembleRelease", self.wf)

    def test_unsigned_build_is_labelled_test_only(self):
        """没钥匙时打出来的包，名字和发布说明都要说清它是一次性的。"""
        self.assertIn("TESTONLY", self.wf)
        self.assertIn("先在 设置 › 搬家 里导出", self.wf)

    def test_signature_change_is_caught_by_ci(self):
        """签名指纹一变就是一次数据事故，CI 得当场拦住，不能等用户装不上才发现。"""
        self.assertIn("SIGNING_FINGERPRINT.txt", self.wf)
        self.assertIn("apksigner", self.wf)

    def test_backup_is_on_but_keys_are_excluded(self):
        """开系统备份接住这份家；但模型 key 不该跟着上云。"""
        self.assertIn('android:allowBackup="true"', self.manifest)
        for f in ("backup_rules.xml", "data_extraction_rules.xml"):
            p = AF / "app" / "src" / "main" / "res" / "xml" / f
            self.assertTrue(p.exists(), f + " 不在")
            self.assertIn("data/secrets.json", p.read_text(encoding="utf-8"), "key 要排除在备份之外")

    def test_docs_do_not_tell_people_to_uninstall_without_warning(self):
        """★ 回归：完整体的文档里，「先卸载」旁边必须跟着「先导出」。"""
        md = (AF / "README.md").read_text(encoding="utf-8")
        self.assertIn("导出", md)
        for m in re.finditer(r"卸载", md):
            window = md[max(0, m.start() - 220): m.start() + 220]
            self.assertTrue("导出" in window or "丢" in window or "没了" in window,
                            "提到卸载的地方要说清代价：\n" + window)


if __name__ == "__main__":
    unittest.main()
