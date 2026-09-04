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

    async def list_models(self) -> list[dict]:
        """这家现在有哪些模型可选。回 [{"id": …, "name": …}]，拿不到就空列表。

        ★ 0904 加的。她的原话：「不应该自己选吧，应该是一个公司链接了，
          然后里面可以像我们一样聊天框切换模型呀」—— 让人手打模型名是给会配环境变量的人
          做的，不是给人用的。选完一家、贴了 key，就该由**这家自己**告诉我们有哪些模型。

        ★ 空列表不是错误，是「这条路问不出来」（回声、CLI 都问不出来）。
          界面照实退回手填，不假装有。
        """
        return []

    async def close(self) -> None:
        """收尾。子进程记得杀掉 —— 人关了页面它不该还活着烧 token。"""


def upstream_error(status: int, raw: str, model: str = "") -> str:
    """把上游那坨 JSON 翻成一句人话 —— **原文照旧带着**。

    ★ 0904 起因：她问「手动输入模型，会不会也会识别错误因为我们没做过」。
      真去试了一次：模型名少打一个字母，界面吐的是
      `模型那边回了 404：{"type":"error","error":{"type":"not_found_error",...}}`。
      技术上没说错，可看的人不知道那是**自己名字打错了**，更不知道去哪儿改。

    ★ 为什么原文要留着：余额不足、key 过期、模型下线、区域不支持 —— 处理方式各不相同，
      我们猜一句话把它盖掉，反而是把人送错方向。所以是「人话 ＋ 原文」，不是「人话取代原文」。
    """
    raw = (raw or "")[:260]
    low = raw.lower()
    hint = ""
    if status == 404 or "not_found" in low or "model_not_found" in low:
        hint = (f"这家不认得「{model}」这个模型名。" if model else "这家不认得这个模型名。")                + "去 设置 › 功能包 › 引擎 改一下，或者点那儿的「认一下有哪些模型」看它到底有哪些。"
    elif status in (401, 403):
        hint = "key 没被认。可能是抄错了、过期了，或者这把 key 用不了这个模型。"
    elif status == 429:
        hint = "被限流了 —— 要么问得太密，要么这个月的额度到头了。等等再说，或者去它家后台看看余额。"
    elif status == 400:
        hint = "这家没接受这个请求。多半是模型名或者参数对不上。"
    elif status >= 500:
        hint = "是它那边出问题了，不是你这边。过一会儿再试。"
    return (hint + f"\n（上游 {status}：{raw}）") if hint else f"模型那边回了 {status}：{raw}"
