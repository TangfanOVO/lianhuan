"""聊天与记忆的「视图」接口 —— 同一份数据的另外几种看法。

聊天记录按天翻、收藏、热力图月历、全局搜索、记忆总览/分层 ——
这些都不是新数据，是 `store` 里那两张表的聚合。所以放在一个独立模块里，
**字段名照原项目一个不改**：前端就是按那些字段写的。

★ 时间统一用本地时区的日期字符串（YYYY-MM-DD）。用 UTC 的话，
  晚上八点之后说的话会被归到「明天」，热力图看着永远差一天。
"""
from __future__ import annotations

import json
import time
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()
_store = None          # server 启动时注入


def bind(store) -> None:
    global _store
    _store = store
    # 这几列是后加的：老库没有就补上（幂等）
    for ddl in ("ALTER TABLE turns ADD COLUMN starred INTEGER DEFAULT 0",
                "ALTER TABLE turns ADD COLUMN hidden INTEGER DEFAULT 0",
                "ALTER TABLE turns ADD COLUMN hidden_parts TEXT"):
        try:
            _store.db.execute(ddl)
            _store.db.commit()
        except Exception:
            pass


def _day(ts: float) -> str:
    return datetime.fromtimestamp(ts or 0).strftime("%Y-%m-%d")


def _hm(ts: float) -> str:
    return datetime.fromtimestamp(ts or 0).strftime("%H:%M")


LAYER_MAP = [
    ("L3", "核心", "关系基石"),
    ("L2", "长期", "重要的事"),
    ("L1", "短期", "最近的事"),
    ("manual", "校准", "你定的说话规矩 · 可改"),
]


# ── 聊天的三种看法 ────────────────────────────────────────
@router.get("/api/chat/heat")
def chat_heat(who: str = ""):
    """热力图：按天数对话条数。前端拿它画月历。"""
    heat: dict[str, int] = {}
    for r in _store.db.execute("SELECT ts FROM turns"):
        d = _day(r["ts"])
        heat[d] = heat.get(d, 0) + 1
    return JSONResponse({"heatmap": heat})


@router.get("/api/chat/day/{day}")
def chat_day(day: str, who: str = "", withhidden: int = 0):
    """某一天的完整记录。"""
    items = []
    for r in _store.db.execute("SELECT * FROM turns ORDER BY id"):
        if _day(r["ts"]) != day:
            continue
        items.append({"id": r["id"], "role": r["role"], "content": r["content"],
                      "think": r["think"] or "", "starred": bool(r["starred"]),
                      "src": "web", "audio_url": None, "hidden": False,
                      "hidden_parts": None, "t": _hm(r["ts"])})
    return JSONResponse({"items": items, "hidden_count": 0})


@router.get("/api/chat/starred")
def chat_starred(who: str = ""):
    """收藏。★ 每条带 `ask`：收藏他那句话时，你说了什么他才这样说 ——
    没有上文的一句话，过几个月再看会不知道当时在聊什么。"""
    rows = list(_store.db.execute(
        "SELECT * FROM turns WHERE starred=1 ORDER BY id DESC LIMIT 200"))
    items = []
    for r in rows:
        ask = None
        if r["role"] != "user":
            u = _store.db.execute(
                "SELECT content FROM turns WHERE role='user' AND id<? ORDER BY id DESC LIMIT 1",
                (r["id"],)).fetchone()
            ask = u["content"] if u else None
        items.append({"id": r["id"], "role": r["role"], "content": r["content"],
                      "think": r["think"] or "", "starred": True, "src": "web",
                      "audio_url": None,
                      "t": datetime.fromtimestamp(r["ts"] or 0).strftime("%Y-%m-%d %H:%M"),
                      "ask": ask})
    return JSONResponse({"items": items})


def _split_say(t: str) -> list[str]:
    """跟前端 splitSay 一模一样 —— 撤第几句按这个下标记，两边不一致会撤错句子。"""
    t = "" if t is None else str(t)
    if "|||" in t:
        return [x.strip() for x in t.split("|||") if x.strip()]
    return [t]


@router.post("/api/chat/{cid}/hide")
async def chat_hide(cid: int, req: Request):
    """藏一句 / 藏一轮 / 放回去。

    形状照原项目：{hidden:bool, part?:int, seg?:str}。
    · 带 part = 只撤那一个泡泡（seg 是那句正文，用来核对下标 —— 流式刚上屏的
      下标是前端自己数的，不核会撤错句子）
    · 不带 part 且 hidden=true = 整轮
    · hidden=false 不带 part = 放回去，两个标记一起清
    ★ 藏只管界面。记忆召回读同一张表，不看这两列。"""
    b = await req.json()
    r = _store.db.execute("SELECT content, hidden_parts FROM turns WHERE id=?", (cid,)).fetchone()
    if r is None:
        return JSONResponse({"ok": False, "error": "没有这条"}, status_code=404)
    hidden = bool(b.get("hidden", True))
    part = b.get("part")
    if not hidden and part is None:
        _store.db.execute("UPDATE turns SET hidden=0, hidden_parts=NULL WHERE id=?", (cid,))
    elif part is None:
        _store.db.execute("UPDATE turns SET hidden=1 WHERE id=?", (cid,))
    else:
        segs = _split_say(r["content"])
        part = int(part)
        seg = (b.get("seg") or "").strip()
        if seg and not (0 <= part < len(segs) and segs[part].strip() == seg):
            # 下标对不上就按正文找 —— 宁可多找一步，不撤错句子
            hits = [i for i, x in enumerate(segs) if x.strip() == seg]
            if not hits:
                return JSONResponse({"ok": False, "error": "对不上是哪一句"}, status_code=409)
            part = hits[0]
        parts = set(json.loads(r["hidden_parts"]) if r["hidden_parts"] else [])
        parts.add(part) if hidden else parts.discard(part)
        if len(parts) >= len(segs):
            _store.db.execute("UPDATE turns SET hidden=1, hidden_parts=NULL WHERE id=?", (cid,))
        else:
            _store.db.execute("UPDATE turns SET hidden_parts=? WHERE id=?",
                              (json.dumps(sorted(parts)), cid))
    _store.db.commit()
    return JSONResponse({"ok": True})


@router.post("/api/chat/{cid}/del")
async def chat_del(cid: int):
    """真删。人说删就是删。"""
    _store.db.execute("DELETE FROM turns WHERE id=?", (cid,))
    _store.db.commit()
    return JSONResponse({"ok": True})


@router.post("/api/chat/{cid}/star")
async def chat_star(cid: int):
    """按一下切换。返回按完的状态，前端要拿它把星点亮/熄灭。"""
    r = _store.db.execute("SELECT starred FROM turns WHERE id=?", (cid,)).fetchone()
    if r is None:
        return JSONResponse({"error": "没有这条"}, status_code=404)
    now = 0 if r["starred"] else 1
    _store.db.execute("UPDATE turns SET starred=? WHERE id=?", (now, cid))
    _store.db.commit()
    return JSONResponse({"ok": True, "starred": bool(now)})


# ── 搜索 ──────────────────────────────────────────────────
@router.get("/api/search")
def search(q: str = "", who: str = ""):
    """一个词翻遍聊天和记忆，结果带类型标签（前端按标签分组）。"""
    q = (q or "").strip()
    if not q:
        return JSONResponse({"items": []})
    out = []
    pat = f"%{q}%"
    for r in _store.db.execute(
            "SELECT * FROM turns WHERE content LIKE ? ORDER BY id DESC LIMIT 40", (pat,)):
        out.append({"id": r["id"], "kind": "聊天·" + ("你" if r["role"] == "user" else "他"),
                    "content": (r["content"] or "")[:200], "think": r["think"] or "",
                    "t": _day(r["ts"]), "starred": bool(r["starred"]), "src": "web"})
    labs = {k: lab for k, lab, _ in LAYER_MAP}
    for m in _store.search_memories(q, limit=40):
        out.append({"kind": labs.get(m.layer, m.layer),
                    "content": m.content[:200], "t": _day(m.ts)})
    return JSONResponse({"items": out})


# ── 记忆字云的数据 ────────────────────────────────────────
@router.get("/api/memories/cloud")
def memories_cloud(limit: int = 1600, cut: int = 100):
    """★ 口径跟 /api/memory/overview 完全一致 —— 字云就摆在总览四栏上头，
    两个数字必须对得上（原项目逮到过一次差 57 条的账）。"""
    cut = max(40, min(400, cut))
    mems = _store.all_memories()
    mems.sort(key=lambda m: (m.ts or 0))
    mem, by = [], {}
    for i, m in enumerate(mems[:limit]):
        by[m.layer] = by.get(m.layer, 0) + 1
        mem.append({"i": i, "id": m.id, "text": m.content[:cut], "len": len(m.content),
                    "layer": m.layer, "day": _day(m.ts), "ref": 0, "str": 1.0,
                    "tags": ",".join(m.tags or [])})
    return JSONResponse({"n": len(mem), "layers": by, "memories": mem})


@router.get("/api/memories/cloud/{mid}")
def memories_cloud_one(mid: int):
    m = next((x for x in _store.all_memories() if x.id == mid), None)
    if not m:
        return JSONResponse({"ok": False}, status_code=404)
    return JSONResponse({"ok": True, "id": m.id, "text": m.content, "layer": m.layer,
                         "day": _day(m.ts),
                         "t": datetime.fromtimestamp(m.ts or 0).strftime("%Y-%m-%d %H:%M"),
                         "ring": "", "tags": m.tags or []})


@router.get("/api/memories/cloud/{mid}/near")
def memories_cloud_near(mid: int, k: int = 6):
    """选中一条时找「跟它有关的」画连线。原项目用向量近邻；
    开源版没有向量，用同一套 2-gram 重合度顶上 —— 形状一致，规模小时效果够。"""
    mems = _store.all_memories()
    me = next((x for x in mems if x.id == mid), None)
    if not me:
        return JSONResponse({"items": []})
    terms = set(_store._terms(me.content))
    scored = []
    for m in mems:
        if m.id == mid or not m.content:
            continue
        n = sum(1 for t in _store._terms(m.content) if t in terms)
        if n:
            scored.append((n, m))
    scored.sort(key=lambda x: -x[0])
    return JSONResponse({"items": [{"id": m.id, "sim": round(min(0.99, n / 8), 3)}
                                   for n, m in scored[:max(1, min(int(k), 12))]]})


# ── 记忆的两种看法 ────────────────────────────────────────
@router.get("/api/memory/overview")
def memory_overview():
    mems = _store.all_memories()
    counts: dict[str, int] = {}
    for m in mems:
        counts[m.layer] = counts.get(m.layer, 0) + 1
    layers = [{"key": k, "label": lab, "sub": sub, "count": counts.get(k, 0)}
              for k, lab, sub in LAYER_MAP]
    heat: dict[str, int] = {}
    for m in mems:
        d = _day(m.ts)
        heat[d] = heat.get(d, 0) + 1
    for r in _store.db.execute("SELECT ts FROM turns"):
        d = _day(r["ts"])
        heat[d] = heat.get(d, 0) + 1
    return JSONResponse({"total": len(mems), "layers": layers, "heatmap": heat})


def _mem_row(m) -> dict:
    return {"id": m.id, "layer": m.layer, "tags": ",".join(m.tags or []),
            "content": m.content, "day": _day(m.ts), "my_note": None}


@router.get("/api/memory/all")
def memory_all(layer: str = "", limit: int = 300):
    mems = _store.all_memories()
    if layer:
        mems = [m for m in mems if m.layer == layer]
    mems.sort(key=lambda m: (-(m.ts or 0), -(m.id or 0)))
    return JSONResponse({"items": [_mem_row(m) for m in mems[:min(int(limit), 500)]]})


@router.get("/api/memory/layer/{layer}")
def memory_layer(layer: str):
    mems = [m for m in _store.all_memories() if m.layer == layer]
    mems.sort(key=lambda m: (-(m.ts or 0), -(m.id or 0)))
    return JSONResponse({"items": [_mem_row(m) for m in mems[:200]]})
