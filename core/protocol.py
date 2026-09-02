"""说话的事件协议。

这套事件是从原项目里**已经在跑**的那条链路上抄下来的 —— 它本来就跟「谁在说话」无关，
所以刚好能当引擎的接口：不管后面接的是本机 CLI 还是某家的 HTTP API，
只要吐出下面这些事件，前端就不用改一个字。

前端约定：一条回复可以由**好几句**组成。原项目用 `|||` 分句，
一句一个气泡，边想边冒 —— 所以 `say` 是「一句」，不是「一段」。
"""
from __future__ import annotations

import json
from typing import Any


# ── 事件类型 ────────────────────────────────────────────────
STAGE = "stage"       # 他在干嘛：翻记忆 / 在想 / 在写东西。不是转圈菊花，是一行人话
THINK = "os"          # 思考链的增量（原项目字段名就叫 os，沿用，免得前端要改）
SAY = "s"             # 一句话（完整的一句，不是字符增量）
TOOL_LIVE = "tool_live"   # 工具刚启动，名字先报出来 —— 写大文件要好几分钟，别让人对着三个点干等
TOOL = "tool"             # 工具在跑，带参数摘要
TOOL_DONE = "tool_done"   # 工具跑完
DONE = "done"         # 说完了，带 session_id
HEARTBEAT = "hb"      # 心跳：长考期一个字节都没有时喂一口，免得中间的反向代理按「空闲」掐断
RECV = "recv"         # 收到了，任务已在寄存器里 —— 带 job id，断线后靠它 attach 补播
GONE = "gone"         # 那条任务已经不在寄存器里了（前端转轮询兜底）
ERROR = "error"       # 出事了，而且要老实告诉人


def sse(kind: str, **fields: Any) -> str:
    """打包成一条 SSE。

    ★ 两个坑，都是真咬过人的：
      1. `ensure_ascii=False` —— 不写的话中文会被转成 \\uXXXX，体积翻几倍
      2. 结尾必须是**两个** \\n，少一个浏览器不会把这条派发出去
    """
    return "data: " + json.dumps({"type": kind, **fields}, ensure_ascii=False) + "\n\n"


#: 分句记号。★★ 前端 `index.html` 里的 splitSay() 用的是同一个记号 ——
#: **改一边必须改另一边**，不然刷新前后的气泡对不上。
SEP = "|||"


def split_say(text: str, sep: str = SEP) -> list[str]:
    """把一段回复切成一句句。

    分隔符可配，因为这是**人格层**的约定不是协议层的 —— 你要是让你的 AI 用别的记号断句，
    改这里一个参数就行，前端不用动。
    """
    return [s.strip() for s in text.split(sep) if s.strip()]

import re as _re

_MARKS = _re.compile(r"‹[^›]*›")


def strip_marks(text: str) -> str:
    """剥掉 ‹…› 带内标记。它是给后处理记账用的（比如 ‹心情 …›），
    落库前有人会正经解析它 —— 但**观众席上不能让人看见**。
    0831 真机验收当场抓的：标记作为最后一句直接蹦在了聊天气泡里。"""
    return _MARKS.sub("", text or "").strip()

