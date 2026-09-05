"""聊天框那颗 ▾ 该列**模型**，不是引擎。

她 0904 的原话：「不应该自己选吧，应该是一个公司链接了，然后里面可以像我们一样
聊天框切换模型呀」—— 让人手打模型名是给会配环境变量的人做的，不是给人用的。

★ 老行为（传引擎名换引擎）一条没动：回声和 CLI 问不出模型名单，那两条照旧。
"""
import asyncio
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock


class _Req:
    """够 engine_models / engine_config_set 用的最小 Request：只要一个 .json()。
    body 传 None＝空请求（老路）。"""

    def __init__(self, body):
        self._b = body

    async def json(self):
        if self._b is None:
            raise ValueError("no body")
        return self._b


def _fresh():
    """每条用例一个干净的库 —— 引擎和 key 都是全局状态，串着会互相污染。"""
    d = tempfile.mkdtemp(prefix="lh-mp-")
    os.environ["LIANHUAN_DB"] = os.path.join(d, "x.db")
    import importlib
    import core.server as S
    importlib.reload(S)
    return S


class TestListsModelsNotEngines(unittest.TestCase):
    def setUp(self):
        self.S = _fresh()

    def test_echo_still_lists_engines(self):
        """没接 API 的时候照旧列引擎 —— 老行为不许动。"""
        out = self.S.ai_model()
        self.assertEqual(out["model"], "echo")
        self.assertIn("echo", out["options"])
        self.assertNotIn("provider", out, "回声这条不该冒出 provider")

    def test_with_an_api_engine_it_lists_models(self):
        S = self.S
        S.store.set_setting("engine", "anthropic")
        S.store.set_setting("engine_models", {"anthropic": [
            {"id": "claude-opus-5", "name": "Opus 5"},
            {"id": "claude-sonnet-5", "name": "Sonnet 5"}]})
        with mock.patch.dict(os.environ, {"LIANHUAN_ANTHROPIC_KEY": "sk-ant-x"}):
            out = S.ai_model()
        self.assertEqual(out.get("provider"), "anthropic")
        self.assertIn("claude-opus-5", out["options"])
        self.assertIn("claude-sonnet-5", out["options"])
        self.assertEqual(out["names"]["claude-opus-5"], "Opus 5")

    def test_the_one_in_use_is_always_on_the_list(self):
        """★ 正在用的那个必须在单子上 —— 不然人看不见自己在用什么（0810 定的规矩）。"""
        S = self.S
        S.store.set_setting("engine", "anthropic")
        S.store.set_setting("engine_models", {"anthropic": [{"id": "claude-sonnet-5", "name": "Sonnet 5"}]})
        with mock.patch.dict(os.environ, {"LIANHUAN_ANTHROPIC_KEY": "sk-ant-x",
                                          "LIANHUAN_ANTHROPIC_MODEL": "claude-opus-5"}):
            out = S.ai_model()
        self.assertEqual(out["options"][0], "claude-opus-5")


class TestSwitching(unittest.TestCase):
    def setUp(self):
        self.S = _fresh()

    def test_engine_name_still_switches_engine(self):
        S = self.S
        r = asyncio.run(S.ai_model_set(_req({"model": "echo"})))
        self.assertEqual(S.store.get_setting("engine"), "echo")
        self.assertEqual(r["model"], "echo")

    def test_model_name_switches_the_model_not_the_engine(self):
        S = self.S
        S.store.set_setting("engine", "anthropic")
        with mock.patch.dict(os.environ, {"LIANHUAN_ANTHROPIC_KEY": "sk-ant-x"}):
            r = asyncio.run(S.ai_model_set(_req({"model": "claude-sonnet-5"})))
        self.assertEqual(r["model"], "claude-sonnet-5")
        self.assertEqual(S.store.get_setting("engine"), "anthropic", "换模型不该动引擎")
        sec = json.loads(S.SECRETS.read_text(encoding="utf-8"))
        self.assertEqual(sec["anthropic_model"], "claude-sonnet-5")
        self.assertNotIn("api_model", sec, "别串到 OpenAI 那一组去")

    def test_garbage_model_names_are_refused(self):
        S = self.S
        S.store.set_setting("engine", "anthropic")
        with mock.patch.dict(os.environ, {"LIANHUAN_ANTHROPIC_KEY": "sk-ant-x"}):
            r = asyncio.run(S.ai_model_set(_req({"model": "模型名带中文"})))
        self.assertEqual(r.status_code, 400)


class _Req:
    def __init__(self, body):
        self._b = body

    async def json(self):
        return self._b


def _req(body):
    return _Req(body)


class TestDiscovery(unittest.TestCase):
    def setUp(self):
        self.S = _fresh()

    def test_it_asks_the_provider_and_remembers(self):
        S = self.S
        S.store.set_setting("engine", "anthropic")
        with mock.patch.dict(os.environ, {"LIANHUAN_ANTHROPIC_KEY": "sk-ant-x"}):
            async def fake(self_):
                return [{"id": "claude-opus-5", "name": "Opus 5"}]
            with mock.patch("core.engines.anthropic_api.AnthropicEngine.list_models", fake):
                r = asyncio.run(S.engine_models())
        self.assertTrue(r["ok"])
        self.assertEqual(r["models"][0]["id"], "claude-opus-5")
        self.assertEqual(S.store.get_setting("engine_models")["anthropic"][0]["id"], "claude-opus-5")

    def test_a_provider_that_wont_tell_us_is_reported_honestly(self):
        """★ 问不到就说问不到 —— 不塞一份写死的名单冒充「支持的模型」。"""
        S = self.S
        S.store.set_setting("engine", "anthropic")
        with mock.patch.dict(os.environ, {"LIANHUAN_ANTHROPIC_KEY": "sk-ant-x"}):
            async def none(self_):
                return []
            with mock.patch("core.engines.anthropic_api.AnthropicEngine.list_models", none):
                r = asyncio.run(S.engine_models())
        self.assertFalse(r["ok"])
        self.assertEqual(r["models"], [])
        self.assertIn("直接填", r["error"])

    def test_no_key_says_what_is_missing(self):
        S = self.S
        S.store.set_setting("engine", "anthropic")
        r = asyncio.run(S.engine_models())
        self.assertEqual(r.status_code, 428)


class TestBadCacheDoesNotTakeDownTheModelButton(unittest.TestCase):
    """★ 0904 真摔出来的：engine_models 是**存在库里**的设置项 —— 换版本、手改、
    导别人的备份进来，形状都可能不是 [{"id":…}]。原来那行直接 m.get("id")，
    碰上一个字符串就 AttributeError → /api/ai_model 500 →
    聊天框那颗模型按钮和整页跟着全黑。

    这条钉住：坏形状跳过，好的照常出来，接口不许摔。
    """

    def test_strings_and_junk_in_the_cache_are_tolerated(self):
        S = _fresh()
        S.store.set_setting("engine", "anthropic")
        S.store.set_setting("engine_models", {"anthropic": [
            "claude-sonnet-5",                                # 光秃秃一个字符串
            {"id": "claude-opus-5", "name": "Opus 5"},        # 正常那种
            None, 42, {"noid": 1}, [],                        # 彻底不认识的
        ]})
        with mock.patch.dict(os.environ, {"LIANHUAN_ANTHROPIC_KEY": "sk-ant-x"}):
            out = S.ai_model()
        opts = out["options"]
        self.assertIn("claude-opus-5", opts)
        self.assertIn("claude-sonnet-5", opts)
        self.assertTrue(all(isinstance(x, str) and x for x in opts), opts)
        self.assertEqual(out["names"].get("claude-opus-5"), "Opus 5")
        self.assertNotIn(42, opts)


class TestTheSheetFindsModelsByItself(unittest.TestCase):
    """接了 API 就自己去认模型 —— 不用人先跑一趟设置页。

    她 0904 的原话：「所以如果是 API，那么，可以做自动识别放进聊天打字框那里吗，
    如果我们识别了的话。」（更早那句：「所有 API 支持的模型被识别之后自动进入聊天框下面」）

    ★ 这是前端逻辑，Python 摸不到运行时。这一份钉的是**那四条边界还在源码里**；
      真正的行为验证是拿 tests/fake_upstream.py 起一个真上游、在浏览器里点的，
      两种情形都走过：上游活着（7 个模型自己出来、缓存落库）、
      上游死了（安静退回只列当前那个，一个错都不弹）。
    """

    def setUp(self):
        with open("core/web/index.html", encoding="utf-8") as f:
            self.src = f.read()

    @unittest.skipUnless(pathlib.Path("app/index.html").exists(),
                         "create.py 的产物不带 app/，这条只在源码仓库里跑")
    def test_the_two_copies_stay_identical(self):
        """app/index.html 是 core/web/index.html 的副本，改了一边必须复制过去。

        ★ 这一条**第三次**在同一个坑上栽：写了读仓库文件的测试，本机绿就以为过了，
          `create.py` 的干净副本里那个文件根本不存在，当场红。
          规矩：加了读仓库文件的测试，一定要在干净副本上再跑一遍。"""
        with open("app/index.html", encoding="utf-8") as f:
            self.assertEqual(f.read(), self.src, "两份不一样了 —— cp 一下")

    def test_it_goes_through_the_endpoint_table(self):
        """URL 只从 EP 表拿，不在逻辑里写字面地址（这仓库的老规矩）。"""
        self.assertIn("engineModels: '/api/engine/models'", self.src)
        self.assertIn("call('engineModels'", self.src)

    def test_only_when_it_has_not_asked_and_only_once(self):
        """认过就有缓存了；每次开弹层都打一次外部请求是白烧别人的配额。
        这家要是不给名单，试一次就收手，不重试。"""
        self.assertIn("!autoScanned && opts.length <= 1", self.src)
        self.assertIn("autoScanned = true;", self.src)

    def test_it_never_blocks_the_sheet(self):
        """认模型要走真网络，最长能等 20 秒 —— 不许拿它卡住弹层。
        所以是 draw() 之后在 .then() 里重画，不是 await 在前面。"""
        i_draw = self.src.index("    draw();")
        i_scan = self.src.index("call('engineModels'")
        self.assertLess(i_draw, i_scan, "自动识别跑到画面前面去了，会卡住弹层")
        self.assertIn(".then(", self.src[i_scan:i_scan + 300])
        self.assertNotIn("await call('engineModels'", self.src)

    def test_failing_to_find_models_is_not_an_error(self):
        """认不出来不算失败 —— 手填模型名那条路本来就一直能走，别弹错吓人。"""
        seg = self.src[self.src.index("call('engineModels'"):][:300]
        self.assertIn("fallback: null", seg)
        self.assertIn("if (r && r.ok", seg, "没拿到就该什么都不做")


class TestFirstTimeSetup(unittest.TestCase):
    """全新装的人第一次配置 —— 0904 外部验收报的两条 P0 都在这儿。

    验收的原话：
      1.「『认一下有哪些模型』没有读取当前输入框，发的是空请求，只会扫描已经保存的旧配置。」
      2.「公司并没有真正自动识别。后端只判断地址里有没有 anthropic.com，
         自建 Claude 代理、第三方 Anthropic 兼容地址会被误判成 OpenAI 接口。」
      它拿全新临时数据库复现过：填本地假 Claude 地址和 Key 后，后端存成了 engine:"api"，
      随后一个模型也认不出来。
    """

    def setUp(self):
        self.S = _fresh()                      # ★ 全新库：engine=echo，secrets 里什么都没有

    def test_a_brand_new_install_has_nothing_saved(self):
        c = self.S.engine_config_get()
        self.assertEqual(c.get("engine"), "echo")
        self.assertFalse(c.get("key_set"))

    def test_probing_uses_what_is_typed_not_what_was_saved(self):
        """★ P0-1：拿**这一刻框里填着的**去问，不是问上一份存下的旧配置。

        原来只有「问已保存的引擎」这一条路，前端还发空请求 ——
        第一次填完地址和 key 还没保存就点它，问的是空配置，一个也认不出来。
        """
        S = self.S
        seen = {}

        async def fake_list(self_):            # 截住真网络：只看它拿什么去问
            seen["base"] = self_.base
            seen["key"] = self_._key
            return [{"id": "claude-opus-5", "name": "Claude Opus 5"},
                    {"id": "claude-opus-4-7", "name": "Claude Opus 4.7"}]

        from core.engines.anthropic_api import AnthropicEngine
        with mock.patch.object(AnthropicEngine, "list_models", fake_list):
            r = asyncio.run(S.engine_models(_Req({
                "engine": "anthropic",
                "base": "http://127.0.0.1:8455",       # ★ 自建地址，不含 anthropic.com
                "key": "sk-ant-t1"})))
        self.assertEqual(seen["base"], "http://127.0.0.1:8455", "没用框里填的地址")
        self.assertEqual(seen["key"], "sk-ant-t1", "没用框里填的 key")
        self.assertTrue(r["ok"])
        self.assertEqual(r["provider"], "anthropic")
        self.assertIn("claude-opus-4-7", [m["id"] for m in r["models"]])

    def test_probing_writes_nothing(self):
        """探一次不该留下任何痕迹 —— 这份配置还没保存呢。"""
        S = self.S
        from core.engines.anthropic_api import AnthropicEngine

        async def fake_list(self_):
            return [{"id": "claude-opus-5", "name": "Claude Opus 5"}]

        with mock.patch.object(AnthropicEngine, "list_models", fake_list):
            asyncio.run(S.engine_models(_Req({
                "engine": "anthropic", "base": "http://127.0.0.1:8455", "key": "sk-ant-x"})))
        self.assertEqual(S.store.get_setting("engine", "echo"), "echo", "临时探不许改当前引擎")
        self.assertEqual(S.store.get_setting("engine_models", {}), {}, "临时探不许写缓存")

    def test_a_custom_anthropic_address_is_not_guessed_as_openai(self):
        """★ P0-2：协议**明说**就照明说的走，不看地址里有没有 anthropic.com。"""
        S = self.S
        r = asyncio.run(S.engine_config_set(_Req({
            "engine": "anthropic",                     # ← 明说
            "base": "https://my-claude-proxy.example.com",   # ← 一点 anthropic.com 都没有
            "model": "claude-opus-4-7",
            "key": "sk-ant-x"})))
        self.assertEqual(r["engine"], "anthropic", "自建 Claude 代理被猜成 OpenAI 了")
        self.assertEqual(S.store.get_setting("engine"), "anthropic")
        c = S.engine_config_get()
        self.assertEqual(c["base"], "https://my-claude-proxy.example.com")
        self.assertEqual(c["model"], "claude-opus-4-7")

    def test_every_preset_says_which_protocol_it_is(self):
        """界面不该再靠地址猜 —— 每条预设自己带着协议。"""
        ps = self.S.engine_config_get()["presets"]
        self.assertTrue(ps)
        for p in ps:
            self.assertIn(p.get("engine"), ("api", "anthropic"), f"{p['name']} 没说协议")
        claude = [p for p in ps if "Claude" in p["name"]]
        self.assertTrue(claude)
        for p in claude:
            self.assertEqual(p["engine"], "anthropic")
        for p in ps:
            if "Claude" not in p["name"]:
                self.assertEqual(p["engine"], "api", f"{p['name']} 不该是 anthropic")

    def test_the_old_no_argument_path_still_works(self):
        """★ 老路一个字没动 —— 聊天框那颗 ▾ 的自动识别、老调用方都还走它。"""
        S = self.S
        S.store.set_setting("engine", "anthropic")
        from core.engines.anthropic_api import AnthropicEngine

        async def fake_list(self_):
            return [{"id": "claude-opus-5", "name": "Claude Opus 5"}]

        with mock.patch.dict(os.environ, {"LIANHUAN_ANTHROPIC_KEY": "sk-ant-x"}), \
             mock.patch.object(AnthropicEngine, "list_models", fake_list):
            r = asyncio.run(S.engine_models(_Req(None)))       # 空 body
        self.assertTrue(r["ok"])
        self.assertNotIn("probe", r, "老路不该被当成临时探")
        self.assertEqual(S.store.get_setting("engine_models", {}).get("anthropic"),
                         [{"id": "claude-opus-5", "name": "Claude Opus 5"}], "老路该写缓存")

    def test_a_brand_new_install_with_no_key_says_so(self):
        """全新装、库里一把 key 都没有 —— 这时候才该说「还差 key」。"""
        r = asyncio.run(self.S.engine_models(_Req({
            "engine": "anthropic", "base": "http://127.0.0.1:8455"})))
        self.assertEqual(r.status_code, 428)

    def test_an_empty_key_box_reuses_the_saved_one(self):
        """★ 0904 复验抓的 P1：key 框空 ≠ 没有 key。

        页面刷新后 key 框按设计是空的（明文 key 不回填到界面），这时候再点
        「连接并识别模型」，该用**已经存着的那把**。
        界面上那句注释本来就这么承诺，可后端原来只要没收到明文就 428，
        逼人重新翻出 key 粘一遍。

        ★ 更糟的是上一版**我把这个错误行为写成了测试**（`test_probing_without_a_key_says_so`
          不分「真没有」和「没重贴」）—— 等于拿测试给 bug 盖了章。
          现在拆成两条：真没有 → 说清楚；有存下的 → 复用。
        """
        S = self.S
        seen = {}

        async def fake_list(self_):
            seen["key"] = self_._key
            seen["base"] = self_.base
            return [{"id": "claude-opus-5", "name": "Claude Opus 5"}]

        from core.engines.anthropic_api import AnthropicEngine
        with mock.patch.dict(os.environ, {"LIANHUAN_ANTHROPIC_KEY": "sk-ant-t2"}), \
             mock.patch.object(AnthropicEngine, "list_models", fake_list):
            r = asyncio.run(S.engine_models(_Req({
                "engine": "anthropic",
                "base": "http://127.0.0.1:8455"})))       # ← key 一个字都没带
        self.assertTrue(r["ok"], "刷新之后再识别不该说「还差 key」")
        self.assertEqual(seen["key"], "sk-ant-t2", "没去用存下的那把")
        self.assertEqual(S.store.get_setting("engine", "echo"), "echo", "复用 key 也不许落盘")
        self.assertEqual(S.store.get_setting("engine_models", {}), {}, "复用 key 也不许写缓存")

    def test_the_saved_key_is_read_per_protocol(self):
        """两条协议各存各的 key。选了 Anthropic 就不该摸到 OpenAI 那把。"""
        S = self.S
        seen = {}

        async def fake_list(self_):
            seen["key"] = self_._key
            return [{"id": "gpt-4o-mini", "name": "gpt-4o-mini"}]

        from core.engines.openai_compat import OpenAICompatEngine
        with mock.patch.dict(os.environ, {"LIANHUAN_API_KEY": "sk-openai-saved",
                                          "LIANHUAN_ANTHROPIC_KEY": "sk-ant-saved"}), \
             mock.patch.object(OpenAICompatEngine, "list_models", fake_list):
            asyncio.run(S.engine_models(_Req({
                "engine": "api", "base": "https://api.deepseek.com"})))
        self.assertEqual(seen["key"], "sk-openai-saved", "串到另一条协议的 key 上了")


class TestTheManualSaveButtonAlsoCarriesTheProtocol(unittest.TestCase):
    """★ 0904 复验抓的 P0：手填兜底那条路也得带协议。

    验收的原话：「选择『Anthropic 协议』后使用『直接保存上面填的』，前端仍没传 engine，
    后端再次误判成 api。」—— 上一轮我只把「识别后点模型」那条带上了，漏了这颗按钮。
    而它恰恰是**厂商不开模型列表接口时唯一的路**，一走就废。

    ★ 它还说了一句我该听的：「新增一条**从页面保存函数出发的**回归测试，
      不要只直接调用后端函数」—— 我上一轮的测试全在后端，
      所以前端漏传参数一条也测不出来。这一组就是钉前端那几行的。
    """

    def setUp(self):
        with open("core/web/index.html", encoding="utf-8") as f:
            self.src = f.read()

    def _handler(self, anchor):
        i = self.src.index(anchor)
        return self.src[i:i + 1400]

    def test_manual_save_sends_the_chosen_protocol(self):
        seg = self._handler("var sv = document.getElementById('engsave')")
        self.assertIn("engine: window.__engProto", seg, "手填保存没带协议")
        self.assertIn("/api/engine/config", seg)

    def test_picking_a_discovered_model_sends_it_too(self):
        seg = self._handler("function drawModels(")
        self.assertIn("engine: window.__engProto", seg)

    def test_discovery_sends_it_too(self):
        seg = self._handler("var scan = document.getElementById('engscan')")
        self.assertIn("engine: window.__engProto", seg)

    def test_no_request_in_this_card_relies_on_the_backend_guessing(self):
        """这张卡里但凡往 engine/config 或 engine/models 发东西的，都得明说协议。"""
        card = self.src[self.src.index("/* ══ 引擎那格的三个帮手"):]
        card = card[:card.index("document.addEventListener('click', function(e){\n    if (e.target.closest && e.target.closest('[data-open=\"packspage\"]')")]
        # 只数**写**的那些：同一张卡里还有一次 GET /api/engine/config 读当前配置，
        # 那次不该带协议（它是问「现在存的是什么」，不是「按这个协议去做」）。
        posts = (card.count("'/api/engine/config', {method:'POST'")
                 + card.count("'/api/engine/models', {method:'POST'"))
        self.assertGreaterEqual(posts, 3, "锚点漂了，这条测试没在测该测的东西")
        self.assertEqual(card.count("engine: window.__engProto"), posts,
                         "有一条请求没带协议 —— 后端就得回去猜地址")

    def test_the_button_keeps_its_own_label(self):
        """★ P2：存完别把文案改成**另一颗按钮**的名字。"""
        seg = self._handler("var sv = document.getElementById('engsave')")
        self.assertIn("var SAVE_LABEL = sv.textContent", seg)
        self.assertNotIn("sv.textContent = '保存并用它说话'", seg)
        self.assertIn("sv.textContent = SAVE_LABEL", seg)


if __name__ == "__main__":
    unittest.main()
