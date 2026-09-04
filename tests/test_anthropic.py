"""Anthropic 引擎的线路契约 —— 拿一个假上游验，不花一分钱、不需要真 key。

★ 这一份能证明的：**我们发出去的形状对不对、回来的流解得对不对**。
  它证明不了 Anthropic 真的接受这个请求 —— 那要真 key 打一次。
  所以文档里只能写「契约已测，真 Key 待验」，不许写「已实测」。

0904 起因：有人问「你们的 API 接口怎么没有 Claude」，一查确实没有 ——
`openai_compat` 打的是 /v1/chat/completions ＋ Bearer，Anthropic 是 /v1/messages ＋ x-api-key。
"""
import asyncio
import json
import unittest

from core.engines.anthropic_api import API_VERSION, AnthropicEngine
from core.engines.base import Turn
from core.protocol import DONE, SAY, THINK


class _Resp:
    """假的 httpx 响应。"""
    def __init__(self, status=200, payload=None, lines=None):
        self.status_code = status
        self._payload = payload or {}
        self._lines = lines or []
        self.text = json.dumps(self._payload, ensure_ascii=False)

    def json(self):
        return self._payload

    async def aread(self):
        return self.text.encode()

    async def aiter_lines(self):
        for l in self._lines:
            yield l

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _FakeClient:
    """记下每一次请求，按剧本回。"""
    def __init__(self, script):
        self.script = list(script)
        self.seen = []

    def _next(self):
        return self.script.pop(0) if self.script else _Resp(200, {"content": [], "stop_reason": "end_turn"})

    async def post(self, url, headers=None, json=None):
        self.seen.append({"url": url, "headers": headers or {}, "body": json or {}})
        return self._next()

    def stream(self, method, url, headers=None, json=None):
        self.seen.append({"url": url, "headers": headers or {}, "body": json or {}, "stream": True})
        return self._next()

    async def aclose(self):
        return None


def _sse(*events):
    """把几个流式事件包成**一个**响应 —— 它是 script 里的一项，不是一串。
    （0904 第一版直接返回了行列表，被当成响应 pop 出来，报 AttributeError。台架的错，不是引擎的。）"""
    return [_Resp(200, lines=["data: " + json.dumps(e, ensure_ascii=False) for e in events])]


def _run(engine, turn, script):
    fake = _FakeClient(script)
    engine._client = fake
    out = []

    async def go():
        # 直接替掉构造：stream() 里会自己 new 一个，这儿把它按住
        import core.engines.anthropic_api as mod
        real = mod.httpx.AsyncClient
        mod.httpx.AsyncClient = lambda *a, **k: fake
        try:
            async for ev in engine.stream(turn):
                out.append(ev)
        finally:
            mod.httpx.AsyncClient = real

    asyncio.run(go())
    return out, fake


class TestWireShape(unittest.TestCase):
    """发出去的请求得长成 Anthropic 认的样子 —— 这四处任何一处错都通不了。"""

    def setUp(self):
        self.eng = AnthropicEngine(key="sk-ant-test", model="claude-opus-5")

    def test_it_talks_to_messages_not_chat_completions(self):
        _, fake = _run(self.eng, Turn(message="在吗"), _sse({"type": "message_stop"}))
        self.assertTrue(fake.seen[0]["url"].endswith("/v1/messages"),
                        "Anthropic 是 /v1/messages，不是 /v1/chat/completions")

    def test_auth_is_x_api_key_plus_version(self):
        _, fake = _run(self.eng, Turn(message="在吗"), _sse({"type": "message_stop"}))
        h = fake.seen[0]["headers"]
        self.assertEqual(h.get("x-api-key"), "sk-ant-test")
        self.assertEqual(h.get("anthropic-version"), API_VERSION, "缺版本头直接 400")
        self.assertNotIn("Authorization", h, "别把 OpenAI 那套鉴权带过来")

    def test_system_is_top_level_and_cached(self):
        """人设走顶层 system，不塞进 messages；而且要打缓存标记 ——
        连环每轮都把整份记忆重发一遍，这个应用特别吃这个。"""
        _, fake = _run(self.eng, Turn(message="在吗", system="你是青枫"), _sse({"type": "message_stop"}))
        b = fake.seen[0]["body"]
        self.assertEqual(b["system"][0]["text"], "你是青枫")
        self.assertEqual(b["system"][0]["cache_control"], {"type": "ephemeral"})
        self.assertTrue(all(m["role"] != "system" for m in b["messages"]),
                        "system 不该混进 messages")

    def test_max_tokens_is_always_sent(self):
        _, fake = _run(self.eng, Turn(message="在吗"), _sse({"type": "message_stop"}))
        self.assertGreater(fake.seen[0]["body"].get("max_tokens", 0), 0, "max_tokens 是必填")

    def test_thinking_is_on_and_summarized(self):
        """思考链是她最看重的东西。这条路上它是一等公民，别关掉。"""
        _, fake = _run(self.eng, Turn(message="在吗"), _sse({"type": "message_stop"}))
        th = fake.seen[0]["body"].get("thinking") or {}
        self.assertEqual(th.get("type"), "adaptive")
        self.assertEqual(th.get("display"), "summarized")


class TestStreamParsing(unittest.TestCase):
    def setUp(self):
        self.eng = AnthropicEngine(key="sk-ant-test")

    def test_text_and_thinking_deltas_come_out_separately(self):
        evs, _ = _run(self.eng, Turn(message="在吗"), _sse(
            {"type": "content_block_delta", "delta": {"type": "thinking_delta", "thinking": "她在问我在不在。"}},
            {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "在的。"}},
            {"type": "message_stop"},
        ))
        blob = "".join(evs)
        self.assertIn(THINK, blob)
        self.assertIn(SAY, blob)
        self.assertIn("她在问我在不在", blob)
        self.assertIn("在的", blob)
        self.assertIn(DONE, blob)

    def test_upstream_error_says_the_real_reason(self):
        """余额不足、key 写错、模型名打错 —— 处理方式完全不同，别只说「出错了」。"""
        evs, _ = _run(self.eng, Turn(message="在吗"),
                      [_Resp(401, {"error": {"message": "invalid x-api-key"}})])
        blob = "".join(evs)
        self.assertIn("401", blob)
        self.assertIn("invalid x-api-key", blob)
        self.assertIn(DONE, blob)

    def test_saying_nothing_is_reported_not_swallowed(self):
        evs, _ = _run(self.eng, Turn(message="在吗"), _sse({"type": "message_stop"}))
        self.assertIn("一个字也没说", "".join(evs))


class TestTools(unittest.TestCase):
    """换成 Claude 不该把「AI 的手」弄丢 —— 那是静默降级，比坏掉还糟。"""

    def test_openai_tool_shape_is_converted(self):
        tools = [{"type": "function", "function": {
            "name": "write_memo", "description": "记一条", "parameters": {"type": "object", "properties": {}}}}]
        got = AnthropicEngine._tools_for_anthropic(tools)
        self.assertEqual(got[0]["name"], "write_memo")
        self.assertIn("input_schema", got[0], "Anthropic 叫 input_schema，不叫 parameters")
        self.assertNotIn("parameters", got[0])

    def test_a_tool_round_runs_and_results_go_back_in_one_message(self):
        eng = AnthropicEngine(key="sk-ant-test")
        eng.tools = [{"type": "function", "function": {
            "name": "peek", "description": "看一眼", "parameters": {"type": "object", "properties": {}}}}]
        called = []

        async def run(name, args):
            called.append(name)
            return "看到了"
        eng.exec_tool = run

        evs, fake = _run(eng, Turn(message="看一眼"), [
            _Resp(200, {"stop_reason": "tool_use", "content": [
                {"type": "tool_use", "id": "tu_1", "name": "peek", "input": {}}]}),
            _Resp(200, {"stop_reason": "end_turn", "content": [{"type": "text", "text": "看完了。"}]}),
        ])
        self.assertEqual(called, ["peek"])
        # 第二次请求里：助手那轮原样回填，tool_result 装在**一条** user 消息里
        second = fake.seen[1]["body"]["messages"]
        self.assertEqual(second[-2]["role"], "assistant")
        self.assertEqual(second[-1]["role"], "user")
        results = [b for b in second[-1]["content"] if b["type"] == "tool_result"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["tool_use_id"], "tu_1", "对不上 id 会 400")
        self.assertIn("看完了", "".join(evs))


class TestHonesty(unittest.TestCase):
    def test_no_key_means_not_ready_and_says_why(self):
        eng = AnthropicEngine(key="")
        self.assertFalse(eng.ready)
        self.assertIn("API key", eng.needs)
        self.assertIn("订阅", eng.needs, "得说清订阅不能当 API 用，不然人会白试")

    def test_non_ascii_key_is_caught_before_it_looks_like_a_network_error(self):
        eng = AnthropicEngine(key="sk-ant-中文")
        self.assertFalse(eng.ready)
        self.assertIn("ASCII", eng.needs)


if __name__ == "__main__":
    unittest.main()
