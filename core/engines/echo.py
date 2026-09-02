"""假引擎 —— 不接任何模型，也能把整条链路跑通。

装完还没填 key 的时候用它。它做三件事：
  1. 让你**立刻**看到界面是活的（不用先去申请 key）
  2. 当测试桩：跑单测、验前端、演示流式和分句，都不烧一分钱
  3. **老实说自己是假的**。它不会假装是谁，回的每一句都写着「这是回声引擎」

★ 它是唯一一个 ready=True 却不接模型的引擎。这不矛盾 ——
  它接通的是它自己承诺的那件事：把你说的话原样回给你。
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator

from ..protocol import DONE, SAY, STAGE, THINK, sse
from .base import Engine, Turn


class EchoEngine(Engine):
    name = "echo"
    label = "未接模型"
    needs = "什么都不要。它不接模型，只把你说的话回给你 —— 先看看界面长什么样。"
    ready = True
    stub = True

    def __init__(self, delay: float = 0.35):
        self.delay = delay      # 装成在想的样子，好看清流式对不对

    async def stream(self, turn: Turn) -> AsyncIterator[str]:
        yield sse(STAGE, text="在想")
        await asyncio.sleep(self.delay)

        yield sse(THINK, delta="（回声引擎：没有真的模型在想，这行是给你看流式长什么样的。）")
        await asyncio.sleep(self.delay)

        n = len(turn.history)
        for line in [
            "这是回声引擎，还没有接真的模型。",
            f"你刚说的是：{turn.message}",
            f"记忆是通的 —— 这之前我们已经来回过 {n} 轮。" if n else "这是我们的第一句话。",
            "去设置里挑一个引擎，就能换成真的了。",
        ]:
            yield sse(SAY, text=line)
            await asyncio.sleep(self.delay)

        yield sse(DONE, session_id=turn.session_id)
