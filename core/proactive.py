"""主动找你 —— 他自己凑过来说一句，不等你先开口。

照原项目 proactive.py＋wake_gate.py 的骨架收进一个模块：
  · 「主动找你的频率」滑钮（whisper_freq.level 0–100）是**总闸**：
    0 = 彻底安静（默认——主动说话走你配的引擎，会花你的钱，所以出厂是关的）；
    换算成一天最多几句用的是原项目 wake_gate 的公式：round(level/100 × 9)，
    50 → 4 句、100 → 9 句。★ 前端「通知与频率」页也按这条公式给人翻译，
    两边必须一致 —— 原项目 0807 的教训：不一样用户就不信这个数了。
  · 节流照原项目：一天封顶之外，**两句之间至少隔 90 分钟**，不刷屏。
  · 到点了就用当前引擎想一句（带注入 —— 他记得你们的事，不是模板问候），
    存进对话（你打开就看到）＋碎碎念，再 push 弹你锁屏一下。

跑法：server 启动时挂一个后台任务，每 15 分钟醒一次掷骰子。
失败静默 —— 主动说话这件事，出错绝不能吵到正常聊天。
"""
from __future__ import annotations

import asyncio
import json
import random
import time

CAP_AT_100 = 9          # level=100 时一天最多几句（原项目 wake_gate 同款）
MIN_GAP_MIN = 90        # 两句之间至少隔这么久（原项目 proactive 同款）
TICK_S = 15 * 60        # 多久醒一次

_store = None
_deps = {}


import contextlib


#: 主动消息带多少条原文、每条留多少字。窗口本身跟召回共用 `recall.TODAY_HOURS`（48 小时）。
PROACTIVE_MAX_MSGS = 40
PROACTIVE_MAX_CHARS = 200


@contextlib.contextmanager
def _nullctx():
    yield


def bind(store, *, engine_turn, pick_engine, add_turn, mood_inject=None, send_push=None,
         activity=None) -> None:
    global _store
    _store = store
    _deps.update(engine_turn=engine_turn, pick_engine=pick_engine, add_turn=add_turn,
                 mood_inject=mood_inject, send_push=send_push, activity=activity)
    store.db.execute(
        "CREATE TABLE IF NOT EXISTS speak_log (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " source TEXT DEFAULT 'proactive', ts REAL)")
    store.db.commit()


def level() -> int:
    d = _store.get_setting("whisper_freq", {}) or {}
    try:
        return max(0, min(100, int(d.get("level") or 0)))
    except Exception:
        return 0


def daily_max(lv: int | None = None) -> int:
    """一天最多说几句。0 → 全静音；50 → 4 句；100 → 9 句。（原项目公式，别动）"""
    lv = level() if lv is None else lv
    return int(round(lv / 100.0 * CAP_AT_100))


def _said_today() -> int:
    # 本地日界：今天 00:00 起算
    import datetime
    t0 = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    return _store.db.execute("SELECT count(*) n FROM speak_log WHERE ts>=?", (t0,)).fetchone()["n"]


def _last_said() -> float:
    r = _store.db.execute("SELECT ts FROM speak_log ORDER BY id DESC LIMIT 1").fetchone()
    return r["ts"] if r else 0.0


def may_speak() -> bool:
    cap = daily_max()
    if cap <= 0:
        return False
    if _said_today() >= cap:
        return False
    if (time.time() - _last_said()) < MIN_GAP_MIN * 60:
        return False
    return True


async def speak_once(reason: str = "") -> str:
    """真说一句：引擎想（带注入）→ 存对话＋碎碎念 → push。返回说的话（空=没说成）。

    `reason` 非空 = 这次不是掷骰子来的，是**他自己之前给自己定的闹钟到点了**。
    那句提醒原样交给他，让他照着那件事开口，而不是随便找话。
    """
    from .memory.recall import build_injection
    from .protocol import SAY

    # ★ 0831 实际用下来发现：骰子发出来的主动消息会翻出已经解决的事、回答过的问题。
    #   两个病根，都在这儿：
    #   ① 翻记忆用的检索词是**写死的这句话**，翻出来的当然跟你俩最近在聊什么无关
    #   ② 整条路**一句 history 都不带** —— 它只看得见 system 里那 24 条摘要，
    #      而正常回话是 system ＋ history 两份都有。
    #   修法（照定下来的口径：「带上决定发之前的 48 小时原文」）：
    #   把最近 48 小时**双方**真说过的话取出来，既当检索词、也当真正的 history。
    from .memory.recall import TODAY_HOURS
    recent = []
    try:
        recent = _store.context_turns(channel="text", limit=PROACTIVE_MAX_MSGS,
                                      since=time.time() - TODAY_HOURS * 3600)
    except Exception as e:
        print("[proactive] 取最近对话失败（照旧往下走）:", e, flush=True)
    # 拿最近说的话当检索词 —— 这样翻出来的记忆才跟眼下这件事有关
    probe = " ".join((t.content or "")[:80] for t in recent[-6:]).strip() or "想用户了，主动说一句"
    system = build_injection(_store, probe)
    mi = _deps.get("mood_inject")
    if mi:
        try:
            system = system + "\n\n" + mi()
        except Exception:
            pass
    if reason:
        system += ("\n\n〔★你之前给自己定了个闹钟，到点了，就是现在。当时你写给自己的是：\n"
                   + reason.strip()[:400]
                   + "\n照这件事开口 —— 那是你自己要说的话，不是待办清单，别念给对方听。"
                   "要是先读完下面这些发现这事已经过去了/已经说过了，那就别硬提，说点别的或者干脆不说。〕")
    system += (
        "\n\n〔★对方这会儿没在跟你说话 —— 是你自己想凑过去说一句。"
        "就一两句，像随手发出去的那种：想到的事、惦记的半句话、刚看到的什么。"
        "别写成问候模板（「在吗」「吃了吗」不算话），别长篇，别连环问问题。〕")

    # ★ 真把这 48 小时的原文交给它 —— 「这事聊完没有」只有看见原文才答得上来。
    history = [{"role": t.role, "content": (t.content or "")[:PROACTIVE_MAX_CHARS]}
               for t in recent]
    if history:
        system += (f"\n\n〔下面 history 里是你俩最近 {TODAY_HOURS} 小时真说过的话。"
                   "**先读完再决定说什么**：已经聊完的事别再问一遍，"
                   "已经答过的问题别再问，说好了的事别当没说过。"
                   "要是这阵子该说的都说过了，那就说点新的，或者干脆别硬找话。〕")
    turn = _deps["engine_turn"](message="（主动说一句）", system=system, history=history)
    eng = _deps["pick_engine"]()
    outs = []
    gen_at_start = getattr(_store, "generation", 0)   # ★ 这句是照哪一份档案想的
    act = _deps.get("activity")
    ctx = act("proactive") if act else _nullctx()
    with ctx:                                          # ★ 让 import 的 409 看得见我
        async for ev in eng.stream(turn):
            try:
                d = json.loads(ev[6:])
            except Exception:
                continue
            if d.get("type") == SAY:
                outs.append(d.get("text") or "")
    text = " ".join(x for x in outs if x).strip()[:400]
    if not text:
        return ""
    if getattr(_store, "generation", 0) != gen_at_start:
        # ★ 0831（GPT 四轮 P0-03b）：想这句的时候档案被换掉了 —— 它是照旧档案想的，
        #   落进新档案就是串线（连带那条碎碎念也别写）。
        print("[proactive] 想的时候档案换了，这句不落库", flush=True)
        return ""

    # ‹心情› 标记照聊天那条路走：落库前清＋记账
    try:
        from optional.homelife.routes import apply_marker
        text, _ = apply_marker(text, "proactive")
    except Exception:
        pass
    _deps["add_turn"](role="assistant", content=text)
    try:
        _store.db.execute("INSERT INTO notes(kind,content,ts) VALUES('whisper',?,?)",
                          (text, time.time()))
    except Exception:
        pass
    _store.db.execute("INSERT INTO speak_log(source,ts) VALUES('proactive',?)", (time.time(),))
    _store.db.commit()

    sp = _deps.get("send_push")
    if sp:
        try:
            cfg = _store.get_setting("config", {}) or {}
            name = (cfg.get("ai") or {}).get("name") or "他"
            await asyncio.to_thread(sp, name, text[:120], "/")
        except Exception as e:
            print("[proactive] push fail:", e, flush=True)
    return text


#: 到点多久之内还补推。★ 照原项目的规矩（`remind_fire.py`）：超期太久就不补了 ——
#: 不然服务停一天再起来，用户会被一堆陈年提醒淹掉。
REMIND_GRACE_S = 2 * 3600


def set_reminder(title: str, due_ts: float, notes: str = "") -> int:
    """他给自己定一个闹钟：到点了系统提醒他，他再来找用户。

    ★ 这是原项目早就有的一样东西（`create_reminder` 那只手 ＋ 每分钟跑的 `remind_fire.py`），
      这份候选里一直没有。写在这儿而不是另起一个进程 —— 这边是单进程，
      主动消息那个循环每拍顺手看一眼就够了。
    """
    _store.db.execute(
        "CREATE TABLE IF NOT EXISTS reminders (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " title TEXT NOT NULL, notes TEXT DEFAULT '', due_ts REAL NOT NULL,"
        " made_ts REAL, fired_ts REAL)")
    cur = _store.db.execute(
        "INSERT INTO reminders(title, notes, due_ts, made_ts) VALUES(?,?,?,?)",
        (title[:200], (notes or "")[:800], float(due_ts), time.time()))
    _store.db.commit()
    return int(cur.lastrowid)


def due_reminders() -> list:
    """到点了、还没响过、而且没超期太久的那几条。"""
    try:
        now = time.time()
        rows = _store.db.execute(
            "SELECT id, title, notes FROM reminders WHERE fired_ts IS NULL "
            "AND due_ts <= ? AND due_ts >= ? ORDER BY due_ts LIMIT 5",
            (now, now - REMIND_GRACE_S)).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []                      # 还没建表 = 一条都没设过，不是错


async def fire_due_reminders() -> int:
    """到点的闹钟：让他照着那件事开口。返回响了几条。

    ★ 先盖 `fired_ts` 再去说 —— 说的过程要几秒，中间再进来一拍就重了。
      宁可漏一次也不许重复打扰用户（原项目那边同样是先盖 notified_at）。
    """
    n = 0
    for r in due_reminders():
        _store.db.execute("UPDATE reminders SET fired_ts=? WHERE id=?", (time.time(), r["id"]))
        _store.db.commit()
        reason = r["title"] + (("\n" + r["notes"]) if r.get("notes") else "")
        try:
            said = await speak_once(reason=reason)
            if said:
                n += 1
                print("[proactive] 闹钟到点，说了：", said[:60], flush=True)
        except Exception as e:
            print("[proactive] 闹钟这条没说成:", e, flush=True)
    return n


async def run_forever() -> None:
    """后台循环。每一拍：闸门全过了，再掷一骰（拍数多、每拍概率压低，说话时刻才不机械）。"""
    await asyncio.sleep(60)          # 起动缓一分钟，别跟启动挤
    while True:
        try:
            # ★ 闹钟先看 —— 它是他自己定的、有具体的事要说，比掷骰子那种优先。
            #   而且**不受掷骰子的闸门管**：定了闹钟就是要说，不该被概率吃掉。
            await fire_due_reminders()
            if may_speak():
                # 一天 cap 句摊到白天 ~16 小时 = 64 拍上；乘 1.6 补被闸门吃掉的机会
                p = min(0.5, daily_max() / 64.0 * 1.6)
                if random.random() < p:
                    said = await speak_once()
                    if said:
                        print("[proactive] 说了：", said[:60], flush=True)
        except Exception as e:
            print("[proactive] tick fail:", e, flush=True)
        await asyncio.sleep(TICK_S)
