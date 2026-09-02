"""引擎接口 —— 「拿什么跟模型说话」这件事的唯一抽象点。

## 为什么长这样

原项目只有一个引擎：本机的 `claude` CLI 子进程。那条路子有个别处学不来的好处 ——
**用的是你自己已经登录的官方客户端**，不碰任何 cookie、不用把 key 交出去。
所以那条被原样搬过来当了第一个实现（`cli.py`），别的都是围着同一个接口新写的适配器。

这么分的用意：新写的适配器要是有毛病，坏的只是那一个，验过的那条照跑。

## 你要加一个引擎

继承 `Engine`，实现 `stream()`，产出 `protocol.py` 里那些事件。就这一件事。
不用管：怎么分句、怎么落库、刷新了怎么补播 —— 那些在上面那层，跟引擎无关。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import AsyncIterator


@dataclass
class Turn:
    """要说的这一轮。"""
    message: str                       # 人说的这句
    system: str = ""                   # 人设 ＋ 召回出来的记忆，拼好的
    history: list[dict] = field(default_factory=list)   # [{"role": "user"|"assistant", "content": str}]
    session_id: str | None = None      # 有的引擎能续会话（CLI 的 --resume），没有就留空


class Engine:
    name = "base"
    #: 顶栏上给人看的短名字。别写内部标识符 —— `echo` 这种词对用人来说没有意义
    label = ""
    #: 给人看的一句话：这个引擎要什么才能跑
    needs = ""
    #: False = 还没真接通。★ 界面必须老实显示「待接」，不许拿假数据冒充能用
    ready = False
    #: True = 它能跑，但**后面没有真的模型**（比如回声引擎）。
    #: ready 和 stub 是两件事：ready 说「点了有反应吗」，stub 说「那个反应是真的吗」。
    #: 界面上这两种都要标出来，只是话不一样。
    stub = False

    async def stream(self, turn: Turn) -> AsyncIterator[str]:
        """产出 SSE 字符串（用 protocol.sse() 打包）。

        实现时记着三件事：
          1. **长考时要有心跳。** 一分钟不吐字节，中间的反向代理会按「空闲」把连接掐了
          2. **别在这儿落库。** 落库在上层，因为断网时也得落 —— 那段逻辑不该每个引擎抄一遍
          3. **最后要吐 DONE**，带上 session_id（能续会话的话）
        """
        raise NotImplementedError

    async def close(self) -> None:
        """收尾。子进程记得杀掉 —— 人关了页面它不该还活着烧 token。"""
