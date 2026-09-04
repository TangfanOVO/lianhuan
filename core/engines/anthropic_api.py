"""Anthropic 官方 API —— 直接跟 Claude 说话。

## 为什么要单独一个引擎，不能填进「API」那一格

隔壁 `openai_compat.py` 打的是 `POST {base}/v1/chat/completions`，鉴权 `Authorization: Bearer`。
**Anthropic 不是这个形状**，四处都不一样，缺一处都通不了：

| | OpenAI 兼容那条 | 这条 |
|---|---|---|
| 路径 | `/v1/chat/completions` | `/v1/messages` |
| 鉴权头 | `Authorization: Bearer <key>` | `x-api-key: <key>` |
| 版本头 | 没有 | `anthropic-version: 2023-06-01`（**必须带**） |
| 人设 | 塞进 `messages[0]` 当 system 消息 | 顶层单独一个 `system` 字段 |
| `max_tokens` | 可省 | **必填** |
| 流式事件 | `data: {choices:[{delta:{content}}]}` | `content_block_delta` 里的 `text_delta` |
| 工具 | `{"type":"function","function":{...,"parameters"}}` | `{"name",...,"input_schema"}` |

所以把 `api.anthropic.com` 填进那一格是接不通的 —— 0904 有人问「你们接口怎么没有 Claude」，
一查确实没有。这一份是补上的那个。

★ **新增，没动 openai 那条。** 那条验过能用的路一个字节没改。

## 两样白给的好处

1. **思考链是原生的。** OpenAI 兼容那边靠模型自己在回复开头写〔…〕，看模型脸色；
   这边是 API 一等公民（`thinking` 块）。这里开的是 `display: "summarized"` ——
   拿得到可读的摘要。（原始思维链任何模型都不返回，这是接口的规矩，不是我们藏了。）
2. **人设可以缓存。** 连环的注入很大（人设＋记忆动辄一两万字）而且每轮几乎不变。
   这里给 system 打了 `cache_control`，重复那部分按缓存价走。
   ★ 这不是省事，是**这个应用特别吃这个**：我们每一轮都把整份记忆重发一遍。

## 说清楚：订阅 ≠ API 额度

Claude 的订阅（Pro/Max）买的是官方客户端的使用权，**不能拿来调 API**。
想用订阅，走隔壁 `cli.py`（本机 CLI 引擎，用你已经登录的官方客户端，不碰 key）。
这一条走 API，是单独计费的。仓库里那条硬线照旧：**绝不接管任何消费级订阅的 Cookie。**
"""
from __future__ import annotations

import json
import os
import sys
from typing import AsyncIterator

import httpx

from .base import Engine, Turn
from ..protocol import DONE, SAY, STAGE, THINK, sse

#: 版本头。Anthropic 要求每个请求都带，缺了直接 400。
API_VERSION = "2023-06-01"

#: 一轮最多吐多少。★ 必填字段，省了就是 400。
MAX_TOKENS = 8192


def _browser_transport():
    """浏览器版（Pyodide）没有 socket：让 httpx 走页面的 fetch。电脑上回 None ＝ httpx 默认。"""
    if sys.platform != "emscripten":
        return None
    from core.browser import transport
    return transport()


class AnthropicEngine(Engine):
    name = "anthropic"
    label = "Claude"

    @staticmethod
    def _secrets() -> dict:
        """界面里填的那份（data/secrets.json，0600）。
        ★ 优先级跟隔壁一致：**界面 > 环境变量 > 默认**。界面是刚点下去的明确意图，它说了算。"""
        try:
            import pathlib
            f = pathlib.Path(os.environ.get("LIANHUAN_DB", "data/lianhuan.db")).parent / "secrets.json"
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def __init__(self, base: str | None = None, model: str | None = None, key: str | None = None):
        sec = self._secrets()
        self.base = (base or sec.get("anthropic_base") or os.environ.get("LIANHUAN_ANTHROPIC_BASE")
                     or "https://api.anthropic.com").rstrip("/")
        self.model = (model or sec.get("anthropic_model")
                      or os.environ.get("LIANHUAN_ANTHROPIC_MODEL") or "claude-opus-5")
        self._key = (key or sec.get("anthropic_key")
                     or os.environ.get("LIANHUAN_ANTHROPIC_KEY") or "").strip()
        self.label = f"Claude · {self.model}"
        # ★ HTTP header 只装 ASCII。key 里混进中文/全角（粘贴时很容易带上）会在**建请求头时**
        #   就抛 UnicodeEncodeError —— 那个错长得像网络问题，会把人送去查网络。先在这儿拦住。
        self._key_ok = self._key.isascii()
        self.ready = bool(self._key) and self._key_ok
        self.needs = (
            f"接 Anthropic 的 {self.model}。"
            if self.ready else
            "key 里有非 ASCII 字符（中文？全角引号？多余的空格？）。"
            "HTTP 请求头只装得下 ASCII —— 检查一下是不是复制粘贴时带上了什么。"
            if self._key and not self._key_ok else
            "要一个 Anthropic API key（sk-ant-… 开头）。两条路：\n"
            "  · 界面里贴（设置 › 功能包 › 引擎 › Claude）—— 存 data/secrets.json，0600，不进导出\n"
            "  · 或者环境变量：export LIANHUAN_ANTHROPIC_KEY\n"
            "★ 订阅（Pro/Max）不能当 API 用。想用订阅请改选「本机 CLI」那个引擎。")
        self._client = None
        #: AI 的手：server 注入 (tools_schema, executor)。没注入就是纯聊天
        self.tools = None
        self.exec_tool = None

    # ── 分句 ──────────────────────────────────────────────
    @staticmethod
    def _feeder():
        """★ 直接借隔壁那份，不再写第二遍 —— 分句规则两处各写一份，早晚漂开。
        它按 protocol.SEP 和标点切句，返回 [(kind, text)]，kind 是 "t"（想法）或 "s"（说的话）。"""
        from .openai_compat import OpenAICompatEngine
        return OpenAICompatEngine._feeder()

    # ── 工具：OpenAI 的形状 → Anthropic 的形状 ──────────────
    @staticmethod
    def _tools_for_anthropic(tools) -> list:
        """`hands.all_tools()` 给的是 OpenAI 的形状，这儿换成 Anthropic 的。
        只换外壳：`function.parameters` 原样搬进 `input_schema`，JSON Schema 两边通用。"""
        out = []
        for t in tools or []:
            fn = t.get("function") if isinstance(t, dict) else None
            if not fn:
                continue
            out.append({
                "name": fn.get("name", ""),
                "description": (fn.get("description") or "")[:1024],
                "input_schema": fn.get("parameters") or {"type": "object", "properties": {}},
            })
        return out

    def _headers(self) -> dict:
        return {
            "x-api-key": self._key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        }

    def _body(self, turn: Turn, msgs: list, stream: bool) -> dict:
        body = {
            "model": self.model,
            "max_tokens": MAX_TOKENS,
            "messages": msgs,
            "stream": stream,
            # 思考链：这条路上是一等公民。summarized ＝ 拿得到可读的摘要
            # （原始思维链任何模型都不返回 —— 接口的规矩，不是我们藏了）
            "thinking": {"type": "adaptive", "display": "summarized"},
        }
        if turn.system:
            # ★ 人设＋记忆打上缓存标记。连环每轮都把整份注入重发一遍，
            #   这个应用比一般聊天壳更吃这个。
            body["system"] = [{
                "type": "text",
                "text": turn.system,
                "cache_control": {"type": "ephemeral"},
            }]
        return body

    async def stream(self, turn: Turn) -> AsyncIterator[str]:
        if not self.ready:
            yield sse("error", text=self.needs)
            yield sse(DONE, session_id=turn.session_id)
            return

        msgs = [m for m in (turn.history or []) if m.get("content")]
        msgs.append({"role": "user", "content": turn.message})

        feed = self._feeder()
        said = False
        yield sse(STAGE, text="在想")

        self._client = httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=15.0),
                                         transport=_browser_transport())
        try:
            # ── 有手的路：先走工具轮（非流式），它说要动手就替它动，动完再想 ──
            tool_defs = self._tools_for_anthropic(self.tools) if (self.tools and self.exec_tool) else []
            rounds = 0
            while tool_defs and rounds < 5:
                rounds += 1
                body = self._body(turn, msgs, stream=False)
                body["tools"] = tool_defs
                r = await self._client.post(f"{self.base}/v1/messages",
                                            headers=self._headers(), json=body)
                if r.status_code != 200:
                    yield sse("error", text=f"模型那边回了 {r.status_code}：{r.text[:260]}")
                    yield sse(DONE, session_id=turn.session_id)
                    return
                d = r.json()
                if d.get("stop_reason") != "tool_use":
                    # 它不想动手，把这一轮的话直接吐出去（别再发一次请求，那是白花钱）
                    for blk in d.get("content") or []:
                        if blk.get("type") == "thinking" and blk.get("thinking"):
                            yield sse(THINK, delta=blk["thinking"])
                        elif blk.get("type") == "text" and blk.get("text"):
                            for kind, s in feed(blk["text"]):
                                if kind == "t":
                                    yield sse(THINK, delta=s)
                                    continue
                                said = True
                                yield sse(SAY, text=s)
                    break

                # ★ 助手这一轮的 content **原样**放回历史 —— 里面的 tool_use 块要跟
                #   下一条 user 里的 tool_result 一一对上（少一块就 400）。
                msgs.append({"role": "assistant", "content": d.get("content") or []})
                results = []
                for blk in d.get("content") or []:
                    if blk.get("type") == "thinking" and blk.get("thinking"):
                        yield sse(THINK, delta=blk["thinking"])
                    elif blk.get("type") == "text" and blk.get("text"):
                        for kind, s in feed(blk["text"]):
                            if kind == "t":
                                yield sse(THINK, delta=s)
                                continue
                            said = True
                            yield sse(SAY, text=s)
                    elif blk.get("type") == "tool_use":
                        name = blk.get("name", "")
                        yield sse("tool_live", name=name)     # 先报「他动手了」，别让人干等
                        ok, err = True, ""
                        try:
                            out = await self.exec_tool(name, blk.get("input") or {})
                        except Exception as e:                # noqa: BLE001 —— 要把真话说给人听
                            ok, err, out = False, f"{type(e).__name__}: {e}"[:200], err
                        results.append({
                            "type": "tool_result",
                            "tool_use_id": blk.get("id", ""),
                            "content": str(out)[:4000],
                            **({"is_error": True} if not ok else {}),
                        })
                        yield sse("tool_done", name=name, ok=ok, err=err)
                # ★ 一条 user 消息里装齐所有 tool_result —— 拆成几条会让它以后不敢并行动手
                msgs.append({"role": "user", "content": results})
            else:
                if tool_defs and rounds >= 5:
                    yield sse("error", text="它连着动了五轮手还没说话……再叫它一声？")

            if said:
                for kind, s in feed("", flush=True):
                    if kind == "s":
                        yield sse(SAY, text=s)
                yield sse(DONE, session_id=turn.session_id)
                return

            # ── 没有手（或工具轮没说话）：走流式，边想边冒 ──
            async with self._client.stream("POST", f"{self.base}/v1/messages",
                                           headers=self._headers(),
                                           json=self._body(turn, msgs, stream=True)) as r:
                if r.status_code != 200:
                    body = (await r.aread()).decode("utf-8", "replace")[:300]
                    # ★ 把真实原因说出来。「出错了」这三个字帮不了任何人 ——
                    #   余额不足、key 写错、模型名打错，处理方式完全不同
                    yield sse("error", text=f"模型那边回了 {r.status_code}：{body}")
                    yield sse(DONE, session_id=turn.session_id)
                    return

                async for line in r.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    try:
                        d = json.loads(line[6:].strip())
                    except Exception:
                        continue
                    typ = d.get("type")
                    if typ == "content_block_delta":
                        delta = d.get("delta") or {}
                        dt = delta.get("type")
                        if dt == "thinking_delta" and delta.get("thinking"):
                            yield sse(THINK, delta=delta["thinking"])
                        elif dt == "text_delta" and delta.get("text"):
                            for kind, s in feed(delta["text"]):
                                if kind == "t":
                                    yield sse(THINK, delta=s)
                                    continue
                                said = True
                                yield sse(SAY, text=s)
                    elif typ == "error":
                        err = (d.get("error") or {}).get("message", "")
                        yield sse("error", text=f"模型那边报错：{err[:200]}")

            for kind, s in feed("", flush=True):
                if kind == "t":
                    yield sse(THINK, delta=s)
                    continue
                said = True
                yield sse(SAY, text=s)
            if not said:
                yield sse("error", text="这轮它一个字也没说出来。可能是被内容策略挡了，或者上下文太长。")

        except httpx.ConnectError:
            yield sse("error", text=f"连不上 {self.base} —— 地址写对了吗？网络通吗？")
        except httpx.ReadTimeout:
            yield sse("error", text="模型那边一直没回话（超时）。可能是网络慢，也可能是它卡住了。")
        except Exception as e:                                # noqa: BLE001
            yield sse("error", text=f"跟模型说话时出事了：{type(e).__name__}"[:160])
        finally:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None
            yield sse(DONE, session_id=turn.session_id)

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None
