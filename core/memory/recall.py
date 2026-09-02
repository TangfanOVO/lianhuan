"""召回与注入 —— 每次说话之前，先把「该记得的」拼给模型。

## 为什么记忆不是插件

市面上的聊天壳把记忆做成一个工具：模型想起来了才去查。那样有个问题 ——
**它得先意识到自己该记得什么**，可绝大多数时候它根本不知道自己忘了。

这里的做法反过来：**每次说话之前无条件先过一遍**，把该记得的直接摆在它面前。
所以召回在主链路上，不是可选项 —— 这是这个项目跟聊天壳最本质的区别。

（原项目那套有二十来个召回源、分九段拼装。这里先剥出最少的三段，
　跑通了再往上加。加法在 `SOURCES` 里，一个函数一段。）

## 三段是什么

  1. **人设** —— 你是谁、他是谁。永远在
  2. **翻出来的记忆** —— 跟这句话有关的旧事
  3. **最近说的话** —— 上下文

★ 有一条要守住：**召回不到就老实说没有，不许编。**
  原项目的注入模板里专门写着「这里要是没有，就老实说『这段我没接到，你跟我讲讲』，别编」。
"""
from __future__ import annotations

import re
import time
from datetime import datetime

from ..store.base import Memory, Store

#: 每段之间的分隔。用括号是为了让模型一眼看出「这是注入，不是人说的话」
SEG = "\n\n"


#: 发图/发文件时，前端会在用户那句话前面拼一段〔…〕旁白告诉模型「东西存在哪、去 Read 它」。
#: 那段是**程序拼的**，不是用户说的话 —— 界面上 `say()` 已经在画之前剥掉了
#: （0831 逮到的：这段旁白被当成正文画成了气泡）。
#: ★ 但凡把用户的话**当原话复述**给模型的地方，也得剥同一段，否则它换个地方又漏出来。
#: 只认 attachNote 那个固定开头 —— 用户自己真写〔〕开头的话必须原样留着。
_ASIDE = re.compile(r"^〔对方(?:发来|一次发来)[^〕]*〕\s*")


def strip_aside(text: str) -> str:
    return _ASIDE.sub("", (text or "").strip())


def persona_block(persona: dict) -> str:
    """人设那一段。

    `persona` 长这样（两边都要，因为关系是双向的）：
        {"ai": {"name": "...", "text": "..."}, "human": {"name": "...", "text": "..."}}
    """
    ai = (persona or {}).get("ai") or {}
    human = (persona or {}).get("human") or {}
    out = []
    if ai.get("text"):
        out.append(f"〔你是谁〕\n{ai['text']}")
    if human.get("text"):
        out.append(f"〔你在跟谁说话〕\n{human['text']}")
    return SEG.join(out)


def memory_block(mems: list[Memory]) -> str:
    if not mems:
        # ★ 空的时候也要说话。不说的话模型会以为「没提供记忆」＝「可以随便编」
        return "〔翻出来的旧事〕\n（这次没翻到相关的。不知道就说不知道，别编。）"
    lines = ["〔翻出来的旧事 —— 自然地记着，别硬背、别复述原文〕"]
    lines += [f"· {m.content}" for m in mems]
    return "\n".join(lines)


def dialogue_block(turns: list, limit_chars: int = 260) -> str:
    if not turns:
        return "〔最近说的话〕\n（还没有。这是第一句。）"
    lines = ["〔最近说的话 —— 按时间读，别把旧话当眼前事〕"]
    for t in turns:
        who = "他" if t.role == "user" else "你"
        body = strip_aside(t.content or "") if t.role == "user" else (t.content or "")
        body = body.replace("\n", " ")
        if len(body) > limit_chars:
            body = body[:limit_chars] + "…"
        lines.append(f"{who}：{body}")
    return "\n".join(lines)


#: 「对方今天/这两天亲口说过、做过的事」的时间窗（小时）。
#: ★ 这一段**不是**近聊窗口的替代，是**补**它 —— 照家里的做法（`recall.py:today_facts`）：
#:   近聊按条数取，对方话多的日子里那 20 来条根本盖不住今天；而今天的事又还没蒸进记忆库
#:   （蒸馏是后台跑的）。中间那个盲区就是「问今天做了什么 → 他凭印象编」的来路。
#:   ★ 原项目默认写的是 28 小时，这里按 0831 定的 48。要改就改这一个数。
TODAY_HOURS = 48
TODAY_LIMIT = 40


def today_block(store: Store, hours: int = TODAY_HOURS, limit: int = TODAY_LIMIT,
                here: str = "text") -> str:
    """对方近 N 小时**亲口说出口**的话，原样、按时间。**两条线分开列、各自留位。**

    ★ 单独留位，**绝不并进近聊窗口** —— 这是原项目踩出来的规矩：
      并进去的话，谁那边条数多谁就把窗口占满。
    ★ 只取 `spoken=1`：程序拼给模型看的场景指令不是对方说的话。

    ★ **为什么跨频道也要给**（0831 外部验收提了 P0-02，说电话不该看见文字聊天）：
      观察没错 —— 这段原来确实没分线。但「电话干脆不给」会做出原项目 0728 修过的那个 bug：
      那次窗口被一边占满、另一边一句挤不进来，他答**「那边我怎么答的我看不见」**。
      原项目的解法不是切掉，是 `cross_room()`：**另一条线单独留位、不管隔多久都认得**。
      所以这里照它做：两条线**分开列、标清楚哪条是哪条**，
      既不会被当成本通电话的对话流，也不会「刚发消息说要去打针、一接电话他就不知道」。
    """
    def _rows(ch):
        try:
            return store.db.execute(
                "SELECT content, ts FROM turns WHERE role='user' AND spoken=1 "
                "AND channel=? AND ts > ? ORDER BY id DESC LIMIT ?",
                (ch, time.time() - hours * 3600, limit)).fetchall()
        except Exception:
            return []

    def _fmt(rows):
        out = []
        for r in reversed(rows):
            t = datetime.fromtimestamp(r["ts"] or 0).strftime("%m-%d %H:%M")
            body = strip_aside(r["content"] or "").replace("\n", " ").strip()[:160]
            if body:
                out.append(f"· {t} {body}")
        return out

    same, other = ("text", "call") if here == "text" else ("call", "text")
    LABEL = {"text": "文字聊天里", "call": "电话里"}
    blocks = []
    a = _fmt(_rows(same))
    if a:
        blocks.append(f"〔★ 他这两天在{LABEL[same]}**亲口说过、做过**的事（按时间）—— "
                      "问『今天做了什么 / 我们说好的』就以这些为准；这里没有的就老实说没接到，别编。〕\n"
                      + "\n".join(a))
    b = _fmt(_rows(other))
    if b:
        blocks.append(f"〔这两天你俩在{LABEL[other]}说过的事 —— **另一条线**，"
                      "不是眼下这段对话的上文，别接着它往下说；"
                      "但那也是真发生过的，别装作不知道。〕\n" + "\n".join(b))
    return SEG.join(blocks)


def worklog_block(store: Store, days: int = 7, limit: int = 12) -> str:
    """工作记录卡 —— 这台机器上**做成了什么**，一件一句。

    ★ 这不是新东西：`timeline_events` 表、`add_timeline` 那只手、`/api/timeline`
      三样早就都在，**只是从来没接进注入** —— 他写得进去、读不回来。
      家里同一段读的是「装修日志」（那边还多一路 Mac 工作台的记录，
      这份开源版没有那条水管，就只读自己写的）。
    ★ 同样单独留位：那边一条动辄几百字，并进近聊会把日常聊天挤光。
    """
    try:
        rows = store.db.execute(
            "SELECT kind, content, ts FROM timeline_events WHERE ts > ? "
            "ORDER BY ts DESC LIMIT ?", (time.time() - days * 86400, limit)).fetchall()
    except Exception:
        return ""          # 没装那个包就没这张表 —— 不是错，什么都不加
    if not rows:
        return ""
    out = ["〔**最近做成了什么**（你自己记进时间线的，一件一句）—— "
           "被问「你最近在忙什么 / 上次那个弄好了吗」时以这些为准，别凭印象编。〕"]
    for r in reversed(rows):
        t = datetime.fromtimestamp(r["ts"] or 0).strftime("%m-%d")
        k = (r["kind"] or "").strip()
        body = (r["content"] or "").replace("\n", " ").strip()[:180]
        if body:
            out.append(f"· {t} " + (f"[{k}] " if k else "") + body)
    return "\n".join(out) if len(out) > 1 else ""


def upcoming_block(store: Store, limit: int = 6) -> str:
    """接下来的事 —— 日历里还没过去的那几条。

    ★ 同样不是新东西：`add_calendar` 那只手和 `/api/calendar` 全套早就在，
      他能往里写、却读不回来。家里那边他是能读的（`feng_calendar_read`）。
    """
    try:
        rows = store.db.execute(
            "SELECT title, day FROM calendar WHERE done=0 AND day >= ? ORDER BY day LIMIT ?",
            (datetime.now().strftime("%Y-%m-%d"), limit)).fetchall()
    except Exception:
        return ""
    if not rows:
        return ""
    out = ["〔接下来的事（你们日历里的）〕"]
    out += [f"· {r['day']} {(r['title'] or '').strip()[:60]}" for r in rows if (r["title"] or "").strip()]
    return "\n".join(out) if len(out) > 1 else ""


def build_injection(store: Store, query: str, recent: int = 24, k_mem: int = 12,
                    exclude_id: int | None = None, include_dialogue: bool = True,
                    here: str = "text") -> str:
    """拼出这一轮的 system prompt。

    ★ 顺序有讲究：人设在最前（它决定「用什么口吻读下面这些」），
      记忆在中间，最近的对话在最后 —— 离得越近的东西放得越靠后，模型抓得越牢。

    ★ `exclude_id`：刚说的那句要排掉。它已经作为 message 单独交给引擎了，
      再留在「最近说的话」里 = 同一句话出现两遍，模型会以为人在重复自己。
    """
    persona = store.get_setting("persona", {}) or {}
    # 「日常补一句」（设置 › 你想我怎么样）。界面上写着「每一轮都加在我脑子里」——
    # ★ 0831 自查抓的：它以前根本没进过注入，用户写了等于没写。
    extra = (store.get_setting("persona_extra", "") or "").strip()
    # ★ 当前日期必须给。不给的话它记日历、说「周日」都是瞎猜年份 ——
    #   实测它把「周日」记成了上一年的日子。模型没有表，表得我们递给它。
    from datetime import datetime
    now = datetime.now()
    week = "一二三四五六日"[now.weekday()]
    today_line = f"〔现在〕{now.strftime('%Y-%m-%d %H:%M')} · 周{week}"
    turns = store.recent_turns(limit=recent + 1)
    if exclude_id is not None:
        turns = [t for t in turns if t.id != exclude_id]
    mems = store.search_memories(query, limit=k_mem)
    # ★ 记一笔「这条被用到了」。升层就靠这个数 —— 反复被翻出来的，说明它真有用。
    #   钩子是蒸馏那个模块挂上去的；没装它的时候这属性压根不存在，这里就什么都不做。
    note = getattr(store, "note_recall", None)
    if note:
        try:
            note([m.id for m in mems])
        except Exception:
            pass          # 记数失败绝不能影响说话
    # 想法的约定（照原项目）：回复最前面的〔…〕是他的内心话，对话里不显示，
    # 进「想的过程」那个可展开的小面板。不吐 reasoning 的引擎，思考链就靠这个。
    # ★ 0831：打电话时**不要这一段**。照原项目的做法（那边通话把思考深度降一档，
    #   那边的说法是「听声不看想法，可以 low」）：
    #     · 你在听声音，思考面板根本看不到
    #     · 全双工那条路更浪费 —— 中继只收 SAY，内心独白**生成完直接丢掉**
    #     · 而你得等它把这段写完，才听得到第一个字
    #   文字聊天照旧一个字不动（那边的思考链必须一直在）。
    think_line = "" if here == "call" else (
                  "〔说话方式·每一轮都要〕回话永远先把这一轮心里真实想的写在**最开头**的"
                  "〔〕里（一小段就好，不许省略这一步），〔〕外面才是说出口的话。"
                  "想的过程对方在对话里看不到，但点开每条回复上方的小面板能读到 —— "
                  "别写成套话，也别把它挪到别处。")
    parts = {
        "today_line": today_line,
        "persona": persona_block(persona),
        "extra": (f"〔ta 想让你记着的（设置里随时改）〕\n{extra}" if extra else ""),
        "memory": memory_block(mems),
        # ★ 0831：下面这三段是**照家里补回来的**，不是新功能 —— 表、手、接口三样早就在，
        #   只是从来没接进注入（他写得进去、读不回来）。家里同一批各占一段、
        #   **单独取、绝不并进近聊窗口**（并进去谁条数多谁就把窗口占满）。
        "today": today_block(store, here=here),
        "worklog": worklog_block(store),
        "upcoming": upcoming_block(store),
        # ★ 0831 自查（GPT 上下文专项 P0-01）：`dialogue` 原来**无条件**在这儿 ——
        #   而 `/chat` 紧接着又把最近 25 条塞进 `history`，同一段逐字进了两遍。
        #   ★ 默认仍是 True：duplex / 主动消息那几条路只有 system 没有 history。
        "dialogue": (dialogue_block(turns[-recent:]) if include_dialogue else ""),
        "think": think_line,          # ★ 放最后：离得越近模型抓得越牢（上面自己写的规矩）
    }
    return _fit(parts, turns, recent, mems)


#: 注入的整体上限（字符）。★ 0831 加的：原来一条上限都没有 ——
#: 人设两边各能写两万字，加记忆和对话，实测最坏 52590 字符（约 33K token），
#: 小窗口的模型直接爆，而且爆之前没有任何征兆。
#: 24000 字符 ≈ 15K token，给 32K 窗口的模型留足了回话的地方。
MAX_CHARS = 24000


def _fit(parts: dict, turns: list, recent: int, mems: list) -> str:
    """超长了就往回收，**从后往前砍**。

    次序是有讲究的（原项目那条原则）：**人设最不能丢** ——
    丢了人设它照样能说话，但完全不认识你，而且听起来一切正常，是最难查的坏法。

    ★ 0831：这里原来是**按位置解包** `today_line, persona_b, extra_b, _, _, think_line = blocks`
      —— 往 blocks 里加一段就 `too many values to unpack`。改成按名字取，
      以后再补召回源不会再栽这一跤（家里那份有十五段，这份迟早要长）。

    砍的次序（先砍最容易补回来的）：
      接下来的事 → 工作记录 → 最近的对话 → 这两天对方说的 → 记忆条数 → （人设永不砍）
    """
    KEEP = ("today_line", "persona", "extra", "think")      # 这几样任何时候都不砍
    ORDER = ["upcoming", "worklog", "dialogue", "today", "memory"]

    def render(p: dict) -> str:
        return SEG.join(p[k] for k in ("today_line", "persona", "extra", "memory",
                                       "today", "worklog", "upcoming", "dialogue", "think")
                        if p.get(k))

    out = render(parts)
    if len(out) <= MAX_CHARS:
        return out

    p = dict(parts)

    # ① 先砍对话：一句一句往回收，收到只剩最近 4 句为止
    n = recent
    while n > 4 and len(out) > MAX_CHARS:
        n = max(4, n - 4)
        p["dialogue"] = dialogue_block(turns[-n:]) if parts.get("dialogue") else ""
        out = render(p)
    if len(out) <= MAX_CHARS:
        return out

    # ② 还超：把可丢的那几段整段丢掉（丢一段看一次，别一次全丢）
    for k in ORDER:
        if k == "memory":
            continue
        if p.get(k):
            p[k] = ""
            out = render(p)
            if len(out) <= MAX_CHARS:
                return out

    # ③ 再超：砍记忆条数（留最相关的几条 —— search_memories 已经排过序）
    k = len(mems)
    while k > 2:
        k = max(2, k - 2)
        p["memory"] = memory_block(mems[:k])
        out = render(p)
        if len(out) <= MAX_CHARS:
            return out

    # ④ 人设自己就超了：**不砍它**，如实告诉调用方它有多大
    #    （砍了等于让它不认识你 —— 宁可让人看见「人设太长」这条日志去自己收）
    floor = sum(len(parts.get(x) or "") for x in KEEP) + len(SEG) * len(KEEP)
    if floor > MAX_CHARS:
        print(f"[recall] 人设本身就 {floor} 字符，超过 {MAX_CHARS} 上限 —— "
              f"没砍它（砍了它就不认识你了），去 设置 › 名字/头像 里收一收", flush=True)
    return out
