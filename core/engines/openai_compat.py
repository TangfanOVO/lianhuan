"""OpenAI 兼容引擎 —— 一个接口接一大票模型。

DeepSeek、Kimi、智谱、通义、MiniMax、硅基流动、OpenRouter、Ollama、LM Studio、
以及 OpenAI 自己 —— 都说同一种话（`/v1/chat/completions` ＋ SSE 流）。
所以这一个文件就够了，换家只改 `base_url` 和 `model`。

## key 放哪儿（0831 把这段改成了实话——原来写「绝不落盘」，代码却先读 secrets.json）

两个来源，优先级从高到低：

1. `data/secrets.json`（0600）—— 界面 设置 › 功能包 › 引擎 里贴的那把。
   普通用户唯一顺手的路。**它不进数据库、不进 /api/export 的导出、
   不进 git（.gitignore 挡着）**；备份/迁移时想带就单独拷这个文件。
2. 环境变量 —— `export LIANHUAN_API_KEY/BASE/MODEL`，给不想让 key 碰盘的人。

★ **不要**让浏览器直接拿着 key 调模型 —— 装了扩展的人、共用设备的人、
  一张截图，都能把它带走。这一薄层后端存在的唯一理由就是替你拿着它。

★ 也**不要**让浏览器直接拿着 key 调模型 —— 装了扩展的人、共用设备的人、
  一张截图，都能把它带走。这一薄层后端存在的唯一理由就是替你拿着它。

## 分句

模型吐的是连续字符流。这里在**句末标点**处断句（。！？…），
一句一个气泡、边想边冒 —— 跟原项目用 `|||` 断句是同一件事，
只是不用要求模型学会打那个记号。人设里写了 `|||` 的话也照样认。
"""
from __future__ import annotations

import json
import sys
import os
import re
from typing import AsyncIterator

from ..protocol import DONE, SAY, SEP, STAGE, THINK, USAGE, sse
from .base import Engine, Turn, upstream_error

#: 句末标点。在这些字符后面断句
END = "。！？…!?"
#: 太短的不单独成句，接着攒 —— 不然「嗯。」「好。」会各占一个气泡
MIN_SAY = 6
#: 一句最多攒多长，超了强行断（防止模型一口气不打标点）
MAX_SAY = 180



def _browser_transport():
    """浏览器版（Pyodide）没有 socket：让 httpx 走页面的 fetch。电脑上回 None ＝ httpx 默认，行为一字不变。"""
    if sys.platform != "emscripten":
        return None
    from core.browser import transport
    return transport()

class OpenAICompatEngine(Engine):
    name = "openai"
    label = "API"

    @staticmethod
    def _secrets() -> dict:
        """界面里填的那份（data/secrets.json，0600）。
        ★ 优先级：**界面 > 环境变量 > 默认**。第一版反过来，结果用户在界面里
          切了 R1、启动脚本里的 env 把它静默压掉 —— 看着改了，实际没生效，
          这种「改了没反应」比报错难查十倍。界面是刚刚点下去的明确意图，它说了算。"""
        try:
            import pathlib
            f = pathlib.Path(os.environ.get("LIANHUAN_DB", "data/lianhuan.db")).parent / "secrets.json"
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def __init__(self, base: str | None = None, model: str | None = None, key: str | None = None):
        sec = self._secrets()
        self.base = (base or sec.get("api_base") or os.environ.get("LIANHUAN_API_BASE")
                     or "https://api.openai.com").rstrip("/")
        self.model = model or sec.get("api_model") or os.environ.get("LIANHUAN_API_MODEL") or "gpt-4o-mini"
        self._key = (key or sec.get("api_key") or os.environ.get("LIANHUAN_API_KEY") or "").strip()
        host = self.base.split("//")[-1].split("/")[0]
        self.label = f"API · {self.model}"
        # ★ HTTP header 只能装 ASCII。key 里混进中文/全角字符（复制粘贴时很容易带上，
        #   或者干脆填了个占位符）会在**建请求头的时候**就抛 UnicodeEncodeError ——
        #   那个错长得像网络问题，会把人送去查网络。先在这儿拦住，说人话。
        self._key_ok = self._key.isascii()
        self.ready = bool(self._key) and self._key_ok
        self.needs = (f"接 {host} 的 {self.model}。"
                      if self.ready else
                      "LIANHUAN_API_KEY 里有非 ASCII 字符（中文？全角引号？多余的空格？）。"
                      "HTTP 请求头只装得下 ASCII —— 检查一下是不是复制粘贴时带上了什么。"
                      if self._key and not self._key_ok else
                      "要一个 API key。两条路：\n"
                      "  · 界面里贴（设置 › 功能包 › 引擎）—— 存 data/secrets.json，0600，不进导出\n"
                      "  · 或者环境变量：export LIANHUAN_API_KEY / _BASE / _MODEL")
        self._client = None
        #: AI 的手：server 注入 (tools_schema, executor)。没注入就是纯聊天
        self.tools = None
        self.exec_tool = None

    def _reasoner_only(self) -> bool:
        """R1 那类纯推理模型**不支持 function calling** —— 带 tools 会被拒或被无视。
        碰到它们就收起手、走流式路（那条路会把 reasoning_content 当思考链吐出来）。
        有思考链没手，或有手没思考链 —— 这是模型的真实取舍，不装。"""
        m = self.model.lower()
        return "reasoner" in m or m.startswith("deepseek-r1") or "/deepseek-r1" in m

    # ── 分句 ──────────────────────────────────────────────
    @staticmethod
    def _feeder():
        buf = ""

        def feed(chunk: str, flush: bool = False):
            """返回 [(kind, text)]：kind 是 "t"（想法）或 "s"（说出口的话）。

            ★〔…〕是他的想法（照原项目的约定：写在回复最前面，对话里不显示，
              进「想的过程」面板）。deepseek-chat 这类不吐 reasoning_content 的模型，
              思考链就靠这个 —— 0831 真机上抓到过一次思考链整段不见。
              流式时〕可能还没到，先攒着不放行。"""
            nonlocal buf
            buf += chunk
            out = []
            while True:
                s = buf.lstrip()
                if not s.startswith("〔"):
                    break
                j = s.find("〕")
                if j < 0:
                    if flush:
                        buf = ""          # 到头了还没闭合：残缺的想法丢掉，别念出来
                    return out            # 没闭合先攒着，别把半个想法当话说
                out.append(("t", s[1:j].strip()))
                buf = s[j + 1:]
            # 人设里写了 ||| 就照着断
            while SEP in buf:
                head, buf = buf.split(SEP, 1)
                if head.strip():
                    out.append(("s", head.strip()))
            # 否则在句末标点处断
            while True:
                m = None
                depth = 0                       # ★ 括号里的句号不算切点 ——
                for i, ch in enumerate(buf):    #   否则「（…。）」被切成「（…。」＋孤儿「）」
                    if ch in "（(「〔":
                        depth += 1
                    elif ch in "）)」〕":
                        depth = max(0, depth - 1)
                    elif ch in END and depth == 0 and i + 1 >= MIN_SAY:
                        m = i
                        break
                if m is None:
                    break
                head, buf = buf[:m + 1], buf[m + 1:]
                if head.strip():
                    out.append(("s", head.strip()))
            if len(buf) > MAX_SAY and not flush:
                cut = buf.rfind("，", 0, MAX_SAY)         # 找个逗号断，别切在词中间
                cut = cut if cut > MIN_SAY else MAX_SAY
                out.append(("s", buf[:cut + 1].strip()))
                buf = buf[cut + 1:]
            if flush and buf.strip():
                out.append(("s", buf.strip()))
                buf = ""
            return [x for x in out if x[1]]

        return feed

    async def stream(self, turn: Turn) -> AsyncIterator[str]:
        if not self.ready:
            yield sse("error", text=self.needs)
            yield sse(DONE, session_id=turn.session_id)
            return

        import httpx

        msgs = []
        if turn.system:
            msgs.append({"role": "system", "content": turn.system})
        msgs += [m for m in (turn.history or []) if m.get("content")]
        msgs.append({"role": "user", "content": turn.message})

        feed = self._feeder()
        said = False
        #: (0904) 这一轮烧了多少。拿不到就全是 0，收尾时不报 —— 不猜。
        used = {"tin": 0, "tout": 0, "tcache_r": 0, "tcache_w": 0}
        yield sse(STAGE, text="在想")

        # ── 有手的路：先走工具轮（非流式），模型说要动手就替它动，动完再想 ──
        # ★ 纯推理模型（R1 系）不支持 tools，别硬塞 —— 让它走下面的流式路吐思考链
        if self.tools and self.exec_tool and not self._reasoner_only():
            import httpx as _hx
            rounds = 0
            client = _hx.AsyncClient(timeout=_hx.Timeout(180.0, connect=15.0), transport=_browser_transport())
            try:
                while rounds < 5:
                    rounds += 1
                    r = await client.post(
                        f"{self.base}/v1/chat/completions",
                        headers={"Authorization": f"Bearer {self._key}",
                                 "Content-Type": "application/json"},
                        json={"model": self.model, "messages": msgs, "tools": self.tools})
                    if r.status_code != 200:
                        yield sse("error", text=upstream_error(r.status_code, r.text, self.model))
                        yield sse(DONE, session_id=turn.session_id)
                        return
                    _j = r.json()
                    _u = _j.get("usage") or {}
                    used["tin"] += int(_u.get("prompt_tokens") or 0)
                    used["tout"] += int(_u.get("completion_tokens") or 0)
                    m = (_j.get("choices") or [{}])[0].get("message") or {}
                    # ★ 思考链在这条路上曾经被漏掉：只取了 content 和 tool_calls。
                    #   支持 thinking+tools 的模型（GLM-4.5、K 系…）每轮都可能带它
                    if m.get("reasoning_content"):
                        yield sse(THINK, delta=m["reasoning_content"])
                    calls = m.get("tool_calls") or []
                    if not calls:
                        for kind, sseg in self._feeder()(m.get("content") or "", flush=True):
                            if kind == "t":
                                yield sse(THINK, delta=sseg)
                                continue
                            said = True
                            yield sse(SAY, text=sseg)
                        break
                    msgs.append(m)
                    for c in calls:
                        fn = (c.get("function") or {})
                        name = fn.get("name") or ""
                        yield sse("tool_live", name=name)      # 先报「他动手了」，别让人干等
                        try:
                            args = json.loads(fn.get("arguments") or "{}")
                        except Exception:
                            args = {}
                        try:
                            result = await self.exec_tool(name, args)
                        except Exception as e:
                            result = {"ok": False, "err": f"{type(e).__name__}: {e}"[:200]}
                        # ★ 0831（GPT 三轮 P0-03）：原来无条件发一个不带状态的 tool_done ——
                        #   工具失败了前端照样显示「✓」。**成没成必须带出去。**
                        ok = not (isinstance(result, dict) and result.get("ok") is False)
                        err = ""
                        if not ok:
                            err = str(result.get("err") or result.get("error") or "没成")[:120]
                        yield sse("tool_done", name=name, ok=ok, err=err)
                        msgs.append({"role": "tool", "tool_call_id": c.get("id"),
                                     "content": json.dumps(result, ensure_ascii=False)[:2000]})
                if not said:
                    yield sse("error", text="它光动手没说话……再叫它一声？")
            except Exception as e:
                yield sse("error", text=f"跟模型说话时出事了：{type(e).__name__}"[:160])
            finally:
                try:
                    await client.aclose()
                except Exception:
                    pass
            yield sse(DONE, session_id=turn.session_id)
            return

        try:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=15.0), transport=_browser_transport())
            async with self._client.stream(
                "POST", f"{self.base}/v1/chat/completions",
                headers={"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"},
                json={"model": self.model, "messages": msgs, "stream": True,
                      # ★ 0904：流式默认**不给** usage，得显式要。不认这个字段的家会忽略它。
                      "stream_options": {"include_usage": True}},
            ) as r:
                if r.status_code != 200:
                    body = (await r.aread()).decode("utf-8", "replace")[:300]
                    # ★ 把真实原因说出来。「出错了」这三个字帮不了任何人 ——
                    #   余额不足、key 写错、模型名打错，处理方式完全不同
                    yield sse("error", text=upstream_error(r.status_code, body, self.model))
                    yield sse(DONE, session_id=turn.session_id)
                    return

                async for line in r.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        d = json.loads(payload)
                    except Exception:
                        continue
                    _u = d.get("usage")
                    if _u:                       # (0904) 末尾那一帧才带
                        used["tin"] = int(_u.get("prompt_tokens") or 0)
                        used["tout"] = int(_u.get("completion_tokens") or 0)
                        used["tcache_r"] = int((_u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
                    delta = (d.get("choices") or [{}])[0].get("delta") or {}
                    # 推理模型（deepseek-reasoner、o 系列）把思考放在单独的字段里
                    rc = delta.get("reasoning_content")
                    if rc:
                        yield sse(THINK, delta=rc)
                    txt = delta.get("content")
                    if txt:
                        for kind, s in feed(txt):
                            if kind == "t":
                                yield sse(THINK, delta=s)
                                continue
                            said = True
                            yield sse(SAY, text=s)

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
        except UnicodeEncodeError:
            # 理论上构造时就拦住了，留着兜底
            yield sse("error", text="key 或 base_url 里有非 ASCII 字符，请求头装不下。检查一下有没有中文或全角符号。")
        except Exception as e:
            yield sse("error", text=f"跟模型说话时出事了：{type(e).__name__}: {e}"[:200])
        finally:
            await self.close()

        if any(used.values()):
            yield sse(USAGE, engine=self.name, model=self.model, **used)
        yield sse(DONE, session_id=turn.session_id)

    async def list_models(self) -> list[dict]:
        """问这家有哪些模型（GET /v1/models —— OpenAI 兼容那套的标准接口）。

        ★ 不是每家都开这条（有的要额外权限，有的干脆没有）。问不到就回空列表，
          界面照实退回手填 —— 不猜、不塞一份写死的名单冒充「支持的模型」。
        """
        if not self.ready:
            return []
        import httpx
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=8.0),
                                         transport=_browser_transport()) as c:
                r = await c.get(f"{self.base}/v1/models",
                                headers={"Authorization": f"Bearer {self._key}"})
                if r.status_code != 200:
                    return []
                data = r.json().get("data") or []
                out = [{"id": m.get("id", ""), "name": m.get("id", "")} for m in data if m.get("id")]
                out.sort(key=lambda x: x["id"])
                return out
        except Exception:
            return []

    async def close(self) -> None:
        c, self._client = self._client, None
        if c is not None:
            try:
                await c.aclose()
            except Exception:
                pass
