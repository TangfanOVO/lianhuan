"""本机 CLI 引擎 —— 用你**已经登录的官方客户端**说话，不用交出任何 key。

## 为什么这条路值得单独做一个

订阅制的 AI 客户端（Claude Code、Codex、Gemini CLI）在你机器上已经登录好了。
直接把它当子进程调，就等于借用你自己的登录 —— 于是：

  · 不用申请 API key，也不用把 key 存在任何地方
  · 不碰浏览器 Cookie、不模拟登录、不接管任何人的会话
  · 计费走你自己的订阅，跟这个项目无关

★ **这是唯一正当的「用订阅」方式。** 任何号称能帮你「接上 ChatGPT / Gemini 订阅」
  却要你交出 Cookie 或会话令牌的做法，都是在拿你的账号冒险 —— 这个项目不做那种事，
  也不接受那种实现。

## 它要什么

本机装了对应的 CLI 并且登录过。没装就 `ready=False`，界面老实显示「待接」。

## 加一个新的 CLI

在 `PRESETS` 里加一条：可执行文件名、怎么拼命令行、怎么读它的输出。
读输出那部分各家格式不一样，所以给了 `parse` 钩子。
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
from typing import AsyncIterator

from ..protocol import DONE, SAY, SEP, STAGE, THINK, TOOL_LIVE, USAGE, sse
from .base import Engine, Turn

#: 一直没有字节吐出来就喂一口心跳。长考、跑工具的时候会静很久，
#: 不喂的话中间的反向代理会按「空闲」把连接掐了。
READ_TIMEOUT = 20
#: 整轮的上限。★ 没有这个，一个卡住的子进程会永远占着。
TOTAL_TIMEOUT = 600
#: ★ 管道读取上限调大。默认 64KB，而一个返回图片或大文件的工具结果
#: 会把整坨 base64 挤在**一行**里 —— 超过上限直接炸穿读取循环，整轮被杀。
STREAM_LIMIT = 8 * 1024 * 1024


PRESETS = {
    "claude": {
        "bin": "claude",
        "label": "Claude Code",
        "args": lambda t, sysprompt: (
            ["-p", t.message, "--output-format", "stream-json", "--verbose",
             "--include-partial-messages",
             # 默认**一个工具都不给**：这里是聊天，不是让它在你机器上干活。
             # 想让它动手的人自己改这行，并且自己想清楚风险。
             "--allowedTools", ""]
            + (["--append-system-prompt", sysprompt] if sysprompt else [])
            + (["--resume", t.session_id] if t.session_id else [])
        ),
    },
}


class CliEngine(Engine):
    name = "cli"
    label = "本机 CLI"
    needs = "本机装了官方 CLI 并且登录过（目前支持 Claude Code）。不用 API key，走你自己的订阅。"

    def __init__(self, preset: str = "claude"):
        self.preset = PRESETS.get(preset) or PRESETS["claude"]
        self.bin = os.environ.get("LIANHUAN_CLI_BIN") or self.preset["bin"]
        self.label = self.preset["label"]
        self.ready, self.needs = self._probe()
        self._proc: asyncio.subprocess.Process | None = None

    def _probe(self) -> tuple[bool, str]:
        """查它能不能跑，而且**说清楚差的是什么**。

        ★ 「没装」和「装了但跑不了」是两回事，差的东西完全不一样：
          前者要去装，后者要 chmod。只说「找不到」会把人送错方向 ——
          这条是实测撞出来的：某台机器上 CLI 装好了，但那个软链接没有执行位，
          `shutil.which()` 一样返回 None，而人对着「找不到」会去重装一遍，白忙。
        """
        if shutil.which(self.bin):
            return True, self.needs

        # PATH 里有同名文件吗？有就是权限问题，不是没装
        # ★ 0831（GPT 二轮 P2）：这些话会经 /api/ai_model 出到界面 ——
        #   界面上不摆宿主机绝对路径（那是在给看屏幕的人报你的目录结构）。
        #   要诊断的人看服务端日志，那儿印全路径。
        for d in (os.environ.get("PATH") or "").split(os.pathsep):
            p = os.path.join(d, self.bin)
            if os.path.exists(p):
                if not os.access(p, os.X_OK):
                    print(f"[cli] 找到了但没有执行权限：{p}", flush=True)
                    return False, (f"`{self.bin}` 在 PATH 里找到了，但没有执行权限 —— "
                                   f"跑一句 `chmod +x $(which {self.bin})` 就行。")
                print(f"[cli] 找到了但跑不起来：{p}", flush=True)
                return False, f"`{self.bin}` 在 PATH 里，但跑不起来。手动执行一次看它报什么。"
        return False, f"没找到 `{self.bin}`。装上官方 CLI 并登录之后它会自己出现。"

    # ── 分句 ────────────────────────────────────────────
    # 模型吐的是连续的字符流，屏幕上要的是一句一个气泡。
    # 所以在这儿攒着，遇到分隔记号就吐一句 —— 跟前端 splitSay() 是同一个约定。
    @staticmethod
    def _feeder():
        buf = ""

        def feed(chunk: str, flush: bool = False):
            nonlocal buf
            buf += chunk
            out = []
            while SEP in buf:
                head, buf = buf.split(SEP, 1)
                if head.strip():
                    out.append(head.strip())
            if flush and buf.strip():
                out.append(buf.strip())
                buf = ""
            return out

        return feed

    async def stream(self, turn: Turn) -> AsyncIterator[str]:
        if not self.ready:
            yield sse("error", text=self.needs)
            yield sse(DONE, session_id=turn.session_id)
            return

        cmd = [self.bin] + self.preset["args"](turn, turn.system)
        feed = self._feeder()
        session_id = turn.session_id
        said_anything = False
        # ★ 0904：订阅这条路**也数得出 token**。
        #   她原以为「订阅好像看不到 Claude 的 token 数」—— 那是 API 控制台的事；
        #   `--output-format stream-json` 吐的就是 Anthropic 的原生流事件
        #   （下面早就在解 content_block_delta / thinking_delta 了，同一套），
        #   所以 message_start / message_delta 里的 usage 一样在。
        #   ★ 数不到就一条都不记 —— 宁可没账，不能有假账。
        used = {"tin": 0, "tout": 0, "tcache_r": 0, "tcache_w": 0}

        yield sse(STAGE, text="在想")
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                limit=STREAM_LIMIT)

            loop = asyncio.get_running_loop()
            deadline = loop.time() + TOTAL_TIMEOUT

            while True:
                if loop.time() > deadline:
                    yield sse("error", text="想太久了，我先停下。再叫我一声。")
                    break
                try:
                    line = await asyncio.wait_for(self._proc.stdout.readline(),
                                                  timeout=READ_TIMEOUT)
                except asyncio.TimeoutError:
                    yield sse("hb")          # 静了太久，喂一口，别让连接被掐
                    continue
                if not line:
                    break

                try:
                    d = json.loads(line)
                except Exception:
                    continue                  # 不是 JSON 的行（横幅、警告）直接跳过

                if d.get("session_id"):
                    session_id = d["session_id"]

                t = d.get("type")
                if t == "stream_event":
                    ev = d.get("event") or {}
                    et = ev.get("type")
                    if et == "message_start":
                        u = ((ev.get("message") or {}).get("usage")) or {}
                        used["tin"] += int(u.get("input_tokens") or 0)
                        used["tcache_r"] += int(u.get("cache_read_input_tokens") or 0)
                        used["tcache_w"] += int(u.get("cache_creation_input_tokens") or 0)
                    elif et == "message_delta":
                        used["tout"] += int((ev.get("usage") or {}).get("output_tokens") or 0)
                    if et == "content_block_delta":
                        delta = ev.get("delta") or {}
                        if delta.get("type") == "text_delta":
                            for s in feed(delta.get("text") or ""):
                                said_anything = True
                                yield sse(SAY, text=s)
                        elif delta.get("type") == "thinking_delta":
                            yield sse(THINK, delta=delta.get("thinking") or "")
                    elif et == "content_block_start":
                        cb = ev.get("content_block") or {}
                        if cb.get("type") == "tool_use" and cb.get("name"):
                            # ★ 工具一启动就报名字：写个大文件可能要几分钟，
                            #   别让人对着三个点干等，不知道它是死了还是在干活
                            yield sse(TOOL_LIVE, name=cb["name"])

            for s in feed("", flush=True):    # 收尾：最后没有分隔记号的那一句
                said_anything = True
                yield sse(SAY, text=s)

            if not said_anything:
                # ★ 一个字都没说出来要老实讲，不能静悄悄地结束 ——
                #   那样界面上什么都不会发生，人会以为自己没点到发送
                yield sse("error", text="这轮它一个字也没说出来。可能是没登录，或者额度用完了。")

        except FileNotFoundError:
            yield sse("error", text=f"找不到 `{self.bin}`。装上官方 CLI 并登录之后再试。")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            yield sse("error", text=f"跑 CLI 的时候出事了：{type(e).__name__}")
        finally:
            await self.close()

        if any(used.values()):
            # model 记的是**哪个 CLI**（claude / codex / …）—— 具体是哪个模型
            # 由那个客户端自己定，我们这头看不见，不编一个填上去。
            yield sse(USAGE, engine="cli", model=self.preset.get("bin") or self.bin, **used)
        yield sse(DONE, session_id=session_id)

    async def close(self) -> None:
        p, self._proc = self._proc, None
        if p is not None and p.returncode is None:
            try:
                p.kill()          # ★ 人关了页面，它不该还活着烧额度
                await p.wait()
            except Exception:
                pass
