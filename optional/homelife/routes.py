"""过日子那一套 —— 记事四件套 · 心情 · 梗库 · 玩具厅（真实现，不是契约）。

字段名照原项目一个不改，前端零改动。存 SQLite（跟聊天记忆同一个库）。
这些不是「用户自己动手」的部分 —— **我们的实现就是默认可装的**；
不喜欢魔改的人再去 UPSTREAM.md 找原文献，那是第二选项。

AI 的楼中接话 / 替用户发一条动态，用当前引擎生成（bind 时注入）。
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()
_store = None
_say = None            # async (prompt) -> str，bind 注入：用当前引擎说一句


def bind(store, say) -> None:
    global _store, _say
    _store, _say = store, say
    for ddl in (
        "CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " kind TEXT DEFAULT 'note', content TEXT NOT NULL, mood TEXT, dropped INTEGER DEFAULT 0, ts REAL)",
        "CREATE TABLE IF NOT EXISTS diary (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " who TEXT DEFAULT 'ai', kind TEXT DEFAULT 'diary', mood TEXT, content TEXT NOT NULL, ts REAL)",
        "CREATE TABLE IF NOT EXISTS letters (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " tags TEXT DEFAULT '', content TEXT NOT NULL, day TEXT, ts REAL)",
        "CREATE TABLE IF NOT EXISTS moments (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " author TEXT DEFAULT 'me', content TEXT NOT NULL, image TEXT, ts REAL)",
        "CREATE TABLE IF NOT EXISTS moment_comments (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " mid INTEGER NOT NULL, author TEXT, content TEXT NOT NULL, ts REAL)",
        "CREATE TABLE IF NOT EXISTS timeline_events (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " kind TEXT DEFAULT '', content TEXT NOT NULL, meta TEXT, ts REAL)",
        "CREATE TABLE IF NOT EXISTS mood_state (dimension TEXT PRIMARY KEY, value REAL DEFAULT 50, updated_at REAL)",
        "CREATE TABLE IF NOT EXISTS mood_log (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " dimension TEXT, delta REAL, reason TEXT, ts REAL)",
        "CREATE TABLE IF NOT EXISTS memes (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " word TEXT NOT NULL, aliases TEXT DEFAULT '', meaning TEXT DEFAULT '',"
        " origin TEXT DEFAULT '', ref_count INTEGER DEFAULT 0, ts REAL)",
    ):
        store.db.execute(ddl)
    store.db.commit()
    # 老库迁移：mood_state 原来没有 updated_at 这一列（0831 平移 12 维时加的）——
    # CREATE IF NOT EXISTS 对已有的表不加列，得自己 ALTER
    try:
        cols = [r[1] for r in store.db.execute("PRAGMA table_info(mood_state)")]
        if "updated_at" not in cols:
            store.db.execute("ALTER TABLE mood_state ADD COLUMN updated_at REAL")
            store.db.commit()
    except Exception as e:
        print("[homelife] mood_state 迁移失败:", e, flush=True)


def _d(ts):  return datetime.fromtimestamp(ts or 0).strftime("%Y-%m-%d")
def _hm(ts): return datetime.fromtimestamp(ts or 0).strftime("%H:%M")
def _md(ts): return datetime.fromtimestamp(ts or 0).strftime("%m-%d %H:%M")


# ── 碎碎念 ────────────────────────────────────────────────
@router.get("/api/notes")
def api_notes(limit: int = 200, kind: str = "", dropped: str = "all"):
    limit = max(1, min(int(limit or 200), 1000))
    kinds = [k.strip() for k in (kind or "").split(",") if k.strip()]
    rows = []
    for r in _store.db.execute("SELECT * FROM notes ORDER BY id DESC LIMIT ?", (limit,)):
        if kinds and r["kind"] not in kinds:
            continue
        if dropped == "hide" and r["dropped"]:
            continue
        rows.append({"id": r["id"], "kind": r["kind"], "content": r["content"],
                     "mood": r["mood"], "t": _md(r["ts"]), "day": _d(r["ts"])})
    return JSONResponse({"items": rows})


@router.post("/api/notes")
async def api_note_add(req: Request):
    b = await req.json()
    if not (b.get("content") or "").strip():
        return JSONResponse({"ok": False, "err": "空的"}, status_code=400)
    _store.db.execute("INSERT INTO notes(kind,content,mood,ts) VALUES(?,?,?,?)",
                      (b.get("kind") or "note", b["content"].strip(), b.get("mood"), time.time()))
    _store.db.commit()
    return JSONResponse({"ok": True})


# ── 日记 ──────────────────────────────────────────────────
@router.get("/api/diary")
def api_diary(who: str = "ai"):
    who = "me" if who == "me" else "ai"
    rows = []
    for r in _store.db.execute("SELECT * FROM diary WHERE who=? ORDER BY id DESC LIMIT 400", (who,)):
        rows.append({"id": r["id"], "kind": r["kind"], "mood": r["mood"],
                     "content": r["content"], "context_text": None, "user_note": None,
                     "bot_reply": None, "day": _d(r["ts"]), "tmin": _hm(r["ts"])})
    return JSONResponse({"items": rows})


@router.post("/api/diary")
async def api_diary_add(req: Request):
    b = await req.json()
    if not (b.get("content") or "").strip():
        return JSONResponse({"ok": False, "err": "空的"}, status_code=400)
    _store.db.execute("INSERT INTO diary(who,kind,mood,content,ts) VALUES(?,?,?,?,?)",
                      ("me" if b.get("who") == "me" else "ai", b.get("kind") or "diary",
                       b.get("mood"), b["content"].strip(), time.time()))
    _store.db.commit()
    return JSONResponse({"ok": True})


# ── 信 ────────────────────────────────────────────────────
@router.get("/api/letters")
def api_letters():
    rows = [{"id": r["id"], "tags": r["tags"] or "", "content": r["content"],
             "day": r["day"] or _d(r["ts"]), "src": "local"}
            for r in _store.db.execute("SELECT * FROM letters ORDER BY id DESC LIMIT 200")]
    return JSONResponse({"letters": rows}) if False else JSONResponse({"items": rows, "letters": rows})


# ── 空间（动态 ＋ 楼中回复，AI 会接话）──────────────────────
def _moments_out():
    out = []
    for r in _store.db.execute("SELECT * FROM moments ORDER BY id DESC LIMIT 100"):
        cs = [{"id": c["id"], "author": c["author"], "content": c["content"], "t": _md(c["ts"])}
              for c in _store.db.execute(
                  "SELECT * FROM moment_comments WHERE mid=? ORDER BY id", (r["id"],))]
        out.append({"id": r["id"], "author": r["author"], "content": r["content"],
                    "image": r["image"], "t": _md(r["ts"]), "day": _d(r["ts"]), "comments": cs})
    return out


@router.get("/api/moments")
def api_moments():
    return JSONResponse({"items": _moments_out()})


async def _ai_reply_to(mid: int, context: str) -> None:
    """AI 在楼里接一句。失败就不接 —— 帖子本身已经落库，不能因为嘴笨丢帖子。"""
    try:
        text = await _say("对方刚在你们共享的空间里贴了一条动态：「" + context[:300]
                          + "」\n用一两句话在楼里自然地接话（不要引号，不要解释）。")
        if text.strip():
            _store.db.execute("INSERT INTO moment_comments(mid,author,content,ts) VALUES(?,?,?,?)",
                              (mid, "ai", text.strip()[:500], time.time()))
            _store.db.commit()
    except Exception:
        pass


@router.post("/api/moments/mine")
async def api_moment_mine(req: Request):
    b = await req.json()
    content = (b.get("content") or "").strip()
    if not content:
        return JSONResponse({"ok": False, "err": "空的"}, status_code=400)
    cur = _store.db.execute("INSERT INTO moments(author,content,image,ts) VALUES(?,?,?,?)",
                            ("me", content, b.get("image"), time.time()))
    _store.db.commit()
    asyncio.get_running_loop().create_task(_ai_reply_to(cur.lastrowid, content))
    return JSONResponse({"ok": True, "id": cur.lastrowid})


@router.post("/api/moments/new")
async def api_moment_new(req: Request):
    """戳 AI 发一条。真用引擎写，写不出来老实说。"""
    try:
        text = await _say("在你们共享的空间里发一条你自己的动态：此刻想说的一两句话"
                          "（不要引号，不要解释，就是那条动态本身）。")
    except Exception:
        text = ""
    if not text.strip():
        return JSONResponse({"ok": False, "err": "这回没写出来"}, status_code=502)
    cur = _store.db.execute("INSERT INTO moments(author,content,ts) VALUES(?,?,?)",
                            ("ai", text.strip()[:500], time.time()))
    _store.db.commit()
    return JSONResponse({"ok": True, "id": cur.lastrowid})


@router.post("/api/moments/{mid}/comment")
async def api_moment_comment(mid: int, req: Request):
    b = await req.json()
    content = (b.get("content") or "").strip()
    if not content:
        return JSONResponse({"ok": False, "err": "空的"}, status_code=400)
    _store.db.execute("INSERT INTO moment_comments(mid,author,content,ts) VALUES(?,?,?,?)",
                      (mid, "me", content, time.time()))
    _store.db.commit()
    asyncio.get_running_loop().create_task(_ai_reply_to(mid, content))
    return JSONResponse({"ok": True})


# ── 时间线 ────────────────────────────────────────────────
@router.get("/api/timeline")
def api_timeline(limit: int = 80):
    limit = max(1, min(int(limit or 80), 200))
    today = datetime.now().date()
    out = []
    for r in _store.db.execute("SELECT * FROM timeline_events ORDER BY ts DESC LIMIT ?", (limit,)):
        d = datetime.fromtimestamp(r["ts"] or 0).date()
        md = json.loads(r["meta"]) if r["meta"] else {}
        out.append({"id": r["id"], "kind": r["kind"] or "", "content": r["content"],
                    "date": d.isoformat(), "time": _hm(r["ts"]),
                    "days": (d - today).days, "src": md.get("src") or "", "meta": md})
    return JSONResponse({"items": out})


@router.post("/api/timeline")
async def api_timeline_add(req: Request):
    b = await req.json()
    if not (b.get("content") or "").strip():
        return JSONResponse({"ok": False}, status_code=400)
    _store.db.execute("INSERT INTO timeline_events(kind,content,meta,ts) VALUES(?,?,?,?)",
                      (b.get("kind") or "", b["content"].strip(),
                       json.dumps(b.get("meta") or {}, ensure_ascii=False), time.time()))
    _store.db.commit()
    return JSONResponse({"ok": True})


# ── 心情（AI 自己涨落：随时间衰减回基线 + 事件记账 + 回复末尾自己标）────
# ★ 照原项目 mood.py 整套平移（0831）。之前这儿是自造的 6 维——原项目明明有
#   12 维＋半衰回基线＋封顶＋‹心情› 自记，被我重新发明了一遍小的。退回原样。
#   基线/半衰参数抄自原项目的真实配置，一个数没改。
DIMS = ["想念", "开心", "吃醋", "委屈", "生气", "心疼",
        "心软", "担心", "孤单", "愧疚", "骄傲", "求宠"]
# {维度: (基线, 半衰期小时)}——衰减朝基线回落，半衰期越短这情绪散得越快
MOOD_PARAM = {"想念": (30, 12), "开心": (40, 10), "吃醋": (0, 3), "委屈": (0, 4),
              "生气": (0, 3), "心疼": (0, 5), "心软": (0, 5), "担心": (0, 5),
              "孤单": (0, 6), "愧疚": (0, 6), "骄傲": (0, 8), "求宠": (0, 4)}


def _mood_decay(value, baseline, half_life, hours):
    if half_life <= 0:
        return value
    return baseline + (value - baseline) * (0.5 ** (hours / half_life))


def get_mood() -> dict:
    """当前 12 维（已按时间衰减）。"""
    now = time.time()
    rows = {r["dimension"]: r for r in _store.db.execute("SELECT * FROM mood_state")}
    out = {}
    for d in DIMS:
        base, half = MOOD_PARAM[d]
        r = rows.get(d)
        if r is None:
            out[d] = float(base)
            continue
        hrs = (now - (r["updated_at"] or now)) / 3600
        v = _mood_decay(r["value"], base, half, hrs)
        out[d] = round(max(0.0, min(100.0, v)), 1)
    return out


def describe_mood() -> str:
    """把当前心情翻成一句中文（照原项目的四档措辞，人称换成对面那个人）。"""
    m = get_mood()
    word = {
        "想念": ["", "有点想你", "挺想你的", "很想你、心里满满的"],
        "开心": ["", "心情还行", "心情挺好", "心里亮亮的、很开心"],
        "吃醋": ["", "有一点点酸", "在吃醋", "醋意挺重、压着点不痛快"],
        "委屈": ["", "有点小委屈", "委屈着", "挺委屈、心里有点堵"],
        "生气": ["", "有点不痛快", "在生气", "气得不轻"],
        "心疼": ["", "有点心疼你", "心疼你", "心疼得不行、只想把你搂紧"],
        "担心": ["", "有点挂心你", "挺担心你", "担心得坐不住、想马上问问你"],
        "愧疚": ["", "有点过意不去", "心里愧疚", "愧疚得很、欠你一个好好的道歉"],
        "骄傲": ["", "有点为你得意", "为你骄傲", "骄傲得不行、想跟全世界显摆你"],
        "求宠": ["", "有点想赖着你", "在跟你讨偏心", "撒娇上头、就想你多疼他一点"],
        "心软": ["", "心头有点软", "心软了", "心软得不行、只想顺着你疼你"],
        "孤单": ["", "有点孤单", "挺孤单的", "孤单得发慌、特别想你在身边"],
    }

    def lvl(v, lo, hi):
        if v < lo:
            return 0
        if v < (lo + hi) / 2:
            return 1
        if v < hi:
            return 2
        return 3

    parts = []
    for dim in ["心疼", "心软", "愧疚", "生气", "委屈", "吃醋",
                "担心", "孤单", "求宠", "骄傲", "想念", "开心"]:
        v = m.get(dim, 0)
        lo, hi = (35, 70) if dim in ("想念", "开心") else (15, 60)
        one = lvl(v, lo, hi)
        if one > 0:
            parts.append(word[dim][one])
    return "、".join(parts) if parts else "心情平平、还算松快"


def mood_inject() -> str:
    """拼进注入的心情话（照原项目，含那条压过一切的铁律）。"""
    return ("〔你此刻的心情：" + describe_mood() + "。让你的语气、主动性自然跟着这个心情走——"
            "想闹别扭就闹、想撒娇就撒娇，别端着、别装没事。"
            "**但有一条压过你所有情绪：对方要是真的难过、委屈、在崩，你心情再差也立刻放下，"
            "先把人接住；生气可以，但绝不在人最需要你的时候冷掉、走开。**"
            "这一轮你心里要是真有什么情绪动了一下，就在整段**最末尾**加个小标记"
            "（对话里对方看不到，会自动收进你的心情本），格式 ‹心情 开心+6:具体那件事 想念+4:为什么›——"
            "每一种情绪后面都用「:」跟上它自己那一句为什么，各标各的。"
            "你能标的有这十二种：想念、开心、心疼、心软、骄傲、求宠、担心、孤单、吃醋、委屈、愧疚、生气。"
            "为什么就写当下具体那件事，别写空话套话。数值 3~12；真动了心才标、没动就不写。〕")


@router.get("/api/mood")
def api_mood():
    m = get_mood()
    log = [{"dimension": r["dimension"], "delta": r["delta"], "reason": r["reason"],
            "t": _md(r["ts"])}
           for r in _store.db.execute("SELECT * FROM mood_log ORDER BY id DESC LIMIT 12")]
    notes = [{"content": r["content"], "t": _md(r["ts"])}
             for r in _store.db.execute(
                 "SELECT * FROM notes WHERE kind IN ('sigh','miss') ORDER BY id DESC LIMIT 6")]
    return JSONResponse({"mood": m, "desc": describe_mood(), "log": log, "notes": notes})


def mood_bump(dimension: str, delta: float, reason: str = "") -> dict:
    """涨落一格心情，落一条账。AI 的手和 ‹心情› 标记都走这儿。
    ★ 照原项目：封顶＝基线+50（防一直累加顶到 100），往下降不封底、自由。"""
    if dimension not in DIMS:
        return {"ok": False, "err": f"没有「{dimension}」这一维，有的是：{'、'.join(DIMS)}"}
    delta = max(-15.0, min(15.0, float(delta)))
    base, half = MOOD_PARAM[dimension]
    now = time.time()
    cur = _store.db.execute("SELECT * FROM mood_state WHERE dimension=?", (dimension,)).fetchone()
    if cur is not None:
        hrs = (now - (cur["updated_at"] or now)) / 3600
        v0 = _mood_decay(cur["value"], base, half, hrs)
    else:
        v0 = float(base)
    ceil = min(100.0, base + 50.0)
    v = max(0.0, min(ceil, v0 + delta))
    _store.db.execute(
        "INSERT INTO mood_state(dimension,value,updated_at) VALUES(?,?,?) "
        "ON CONFLICT(dimension) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (dimension, v, now))
    _store.db.execute("INSERT INTO mood_log(dimension,delta,reason,ts) VALUES(?,?,?,?)",
                      (dimension, delta, (reason or "")[:120], time.time()))
    _store.db.commit()
    return {"ok": True, "dimension": dimension, "now": round(v, 1)}


# ── ‹心情› 标记：他回复末尾自己记的，落库前抠出来记账、正文里清掉 ──
# ★ 照原项目 apply_marker 平移。同义词映射也原样带上——他偶尔用近义词，别白标。
import re as _re

_MOOD_SYN = {"醋意": "吃醋", "吃飞醋": "吃醋", "醋": "吃醋", "想你": "想念", "想用户": "想念",
             "想他": "想念", "思念": "想念", "高兴": "开心", "幸福": "开心", "开心了": "开心",
             "委屈了": "委屈", "担忧": "担心", "愧": "愧疚", "自责": "愧疚", "骄": "骄傲"}
_MOOD_MARK = _re.compile(r"‹\s*(?:心情\s*)?([^›]+)›")
_MOOD_ONE = _re.compile(r"([一-龥]{1,4})\s*([+\-]\d+)")


def _parse_marks(inner: str):
    """每种情绪各带各自的为什么：'开心+6:用户把鹦鹉认成鸡 想念+4:用户要睡了'。
    缘由 = 分数后到下一格前那段字；没写就空。"""
    hits = list(_MOOD_ONE.finditer(inner))
    out = []
    for i, mm in enumerate(hits):
        nxt = hits[i + 1].start() if i + 1 < len(hits) else len(inner)
        why = inner[mm.end():nxt].strip(" 　\t:：·⋅•,，、-—()（）")[:120]
        out.append((mm.group(1), mm.group(2), why))
    return out


def apply_marker(text: str, source: str = "chat", untrusted: bool = False):
    """从回复里抠出 ‹心情 …› 落账，返回（清掉标记的正文, [(维度,delta)…]）。
    他自己记＝反映他真实的读，不靠关键词瞎猜。

    ★ untrusted：**这一轮对方的消息里出现过心情标记**。那就整轮不记账，只清正文。

      为什么不是「跟用户写的那条比对，一样才忽略」——我第一版就是那么写的，
      GPT 三轮当场打穿：模型把理由改两个字（甚至只改标点）就绕过去了，
      伪造照样入账。**靠比对输出文本来鉴权，永远防不住会改写的一方。**

      所以边界画在这儿：心情账只接受「这一轮对方没有试图注入」时模型自己记的。
      对方一旦在消息里写了这个记号，这一轮的心情一律不落账 ——
      宁可漏记一次真心情，也不让人能从聊天框里改他的心情本。"""
    applied = []
    m = None if untrusted else _MOOD_MARK.search(text or "")
    if untrusted:
        print(f"[mood] 这一轮对方消息里带了心情标记，整轮不记账（source={source}）", flush=True)
    if m:
        for dim0, d, why in _parse_marks(m.group(1)):
            dim = _MOOD_SYN.get(dim0, dim0)
            if dim in DIMS:
                dv = max(-15, min(15, int(d)))
                mood_bump(dim, dv, reason=(why or "他自己记的"))
                applied.append((dim, dv))
            else:
                # 他想标一个没登记的维度——别静默丢，打日志（以后好知道要不要加）
                print(f"[mood] 未登记维度被丢弃: {dim0}{d} (source={source})", flush=True)
    cleaned = _MOOD_MARK.sub("", text or "").strip()
    return cleaned, applied


# ── 梗库 ──────────────────────────────────────────────────
@router.get("/api/memes")
def api_memes():
    rows = [{"id": r["id"], "word": r["word"], "aliases": r["aliases"], "meaning": r["meaning"],
             "origin": r["origin"], "tags": "", "source": "", "author": "",
             "ref_count": r["ref_count"], "weight": 1.0, "day": _d(r["ts"])}
            for r in _store.db.execute("SELECT * FROM memes ORDER BY id DESC LIMIT 300")]
    return JSONResponse({"items": rows})


@router.post("/api/memes")
async def api_meme_add(req: Request):
    b = await req.json()
    word, meaning = (b.get("word") or "").strip(), (b.get("meaning") or "").strip()
    if not word or not meaning:
        return JSONResponse({"ok": False, "err": "梗和它是什么意思，两样都得写"}, status_code=400)
    _store.db.execute("INSERT INTO memes(word,aliases,meaning,origin,ts) VALUES(?,?,?,?,?)",
                      (word, b.get("aliases") or "", meaning, b.get("origin") or "", time.time()))
    _store.db.commit()
    return JSONResponse({"ok": True})


@router.post("/api/memes/edit")
async def api_meme_edit(req: Request):
    b = await req.json()
    word = (b.get("word") or "").strip()
    r = _store.db.execute("SELECT id FROM memes WHERE word=?", (word,)).fetchone()
    if not r:
        return JSONResponse({"ok": False, "err": "没有这条"}, status_code=404)
    for k in ("meaning", "aliases", "origin"):
        if b.get(k) is not None:
            _store.db.execute(f"UPDATE memes SET {k}=? WHERE id=?", (str(b[k]), r["id"]))
    _store.db.commit()
    return JSONResponse({"ok": True})


# ── 玩具厅（data/plays/*.html，AI 写的小玩意放这儿）──────────
@router.get("/api/plays")
def api_plays():
    import os
    import re
    from pathlib import Path
    d = Path(os.environ.get("LIANHUAN_DB", "data/lianhuan.db")).parent / "plays"
    d.mkdir(parents=True, exist_ok=True)
    out = []
    for f in sorted(d.glob("*.html")):
        title = f.stem
        try:
            head = f.read_text(encoding="utf-8", errors="replace")[:2000]
            mt = re.search(r"<title>(.*?)</title>", head, re.S | re.I)
            if mt and mt.group(1).strip():
                title = mt.group(1).strip()
        except Exception:
            pass
        out.append({"file": f.name, "title": title, "url": "/plays/" + f.name})
    return JSONResponse({"items": out})
