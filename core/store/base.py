"""存储接口 —— 「东西存哪儿」这件事的唯一抽象点。

原项目的数据 100% 在 PostgreSQL 里。开源版默认要能**完全不用服务器**，
所以这里把存储抽出来，三种都能插：

  · `sqlite.py`   零配置，一个文件，默认就是它
  · `postgres.py` 照原项目那套（想上多设备/多端同步的人用）
  · 浏览器本地     数据留在你手机里，一个字节都不出门（前端那半边实现）

★ 接口**故意做得很小**。方法越少，你自己写一个实现就越容易。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Turn:
    """一轮对话。一轮 = 一次说话，屏幕上可能显示成好几个气泡。"""
    role: str                  # "user" | "assistant"
    content: str
    think: str = ""            # 思考链。想留就留，不想留就空着
    #: 这一轮**真的**动了哪些手，成没成。JSON: [{"name":…,"ok":true/false,"err":…}]
    #: ★ 0831（GPT 四轮 P0-04）：工具失败原来只是个瞬时状态条，模型下一句就把它盖掉，
    #:   最终页面只剩「已经写好了」而库里 0 条。真实结果必须跟着这一轮永久存下来。
    tools: str = ""
    #: 机器拼的指令（「翻空间 / 打电话 / 收新消息」那类）。1 = 界面上不画成人的气泡。
    #: ★ 0831 自查：这一列原来只由 `core/views.py` 的 bind() 用 ALTER 建出来、
    #:   `Turn` 里根本没有它 —— 于是**导出压根不带**，导入之后全归 0，
    #:   那些机器指令重新变成人的假气泡（正是真机上抓过的那个 bug）。
    hidden: int = 0
    #: ★ `spoken` 跟 `hidden` **是两件事**，别合并（0831 自查差点在这儿栽）：
    #:   · `hidden` 是**界面**标记，两种情况都会置 1 —— 机器拼的指令，
    #:     以及**用户自己把一句真话收起来**（/api/chat/{id}/hide）。
    #:   · `spoken` 说的是「这句到底是不是人真说出口的」。
    #:   拿 hidden 当「不是原话」的判据，会把用户真说过、只是收起来的话从上下文里抹掉 ——
    #:   那比多读几句糟得多。所以单开一列。
    spoken: int = 1
    #: 'text' | 'call'。文字和电话共用一张表，但**不共用上下文**。
    channel: str = "text"
    #: 每通电话一个。挂断再拨必须是新线程，不能靠 session_id='call' 全局共用一个。
    call_id: str | None = None
    session_id: str | None = None
    ts: float = 0.0
    id: int | None = None


@dataclass
class Memory:
    """一条记忆。

    `layer` 是分层：L1 最近发生的、L2 沉下来的事实、L3 关系的地基。
    分层是**召回时决定读多少**用的，不是重要性排名。
    """
    content: str
    layer: str = "L1"
    tags: list[str] = field(default_factory=list)
    ts: float = 0.0
    id: int | None = None


class Store:
    """要实现的就这些。"""

    # ── 对话 ──
    def add_turn(self, turn: Turn) -> int: raise NotImplementedError
    def recent_turns(self, limit: int = 24) -> list[Turn]: raise NotImplementedError
    def all_turns(self) -> list[Turn]: raise NotImplementedError

    # ── 记忆 ──
    def add_memory(self, mem: Memory) -> int: raise NotImplementedError
    def search_memories(self, query: str, limit: int = 12) -> list[Memory]: raise NotImplementedError
    def all_memories(self) -> list[Memory]: raise NotImplementedError
    def delete_memory(self, mid: int) -> None: raise NotImplementedError

    # ── 人设 / 设置 ──
    def get_setting(self, key: str, default: Any = None) -> Any: raise NotImplementedError
    def set_setting(self, key: str, value: Any) -> None: raise NotImplementedError

    # ── 搬家 ──
    def export_all(self) -> dict:
        """整个家打包成一个 dict。**不加密、不混淆** —— 你自己的东西你得看得懂。"""
        return {
            "lianhuan": 1,
            "persona": self.get_setting("persona", {}),
            "settings": {k: v for k, v in (self.get_setting("_public", {}) or {}).items()},
            "memories": [asdict(m) for m in self.all_memories()],
            "turns": [asdict(t) for t in self.all_turns()],
        }

    def import_all(self, data: dict, mode: str = "merge") -> dict:
        """导入。

        `mode="merge"` 往里加（默认，安全）；`mode="replace"` 先清空。
        ★ replace 之前一定先 export 一份存着 —— 这是不可逆的。
        """
        raise NotImplementedError
