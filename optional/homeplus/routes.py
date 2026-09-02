"""家什与台账 —— 日历/纪念日 · 钱包 · 相册 · 我在哪 · 正在听 · 骰子频率 · 人设历史 · 颜文字。

全是自家写的开放实现，**内置默认装**。字段名照原项目。
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()
_store = None


def bind(store) -> None:
    global _store
    _store = store
    for ddl in (
        # 工作本：要做的和做成的。★ 0831 接的后端 —— 在这之前它是「有页有入口、
        # 后端一条接口都没有」的唯一一个（外部验收连着两轮点名）。
        "CREATE TABLE IF NOT EXISTS workbook (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " kind TEXT DEFAULT 'todo', title TEXT NOT NULL, body TEXT DEFAULT '',"
        " url TEXT DEFAULT '', status TEXT DEFAULT 'inbox',"
        " created_by TEXT DEFAULT '', done_by TEXT DEFAULT '',"
        " done_note TEXT DEFAULT '', done_ts REAL, ts REAL)",
        "CREATE TABLE IF NOT EXISTS trips (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " place TEXT NOT NULL, weather TEXT DEFAULT '', note TEXT DEFAULT '',"
        " kind TEXT DEFAULT '走走', ts REAL)",
        "CREATE TABLE IF NOT EXISTS calendar (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " title TEXT NOT NULL, day TEXT, tm TEXT, kind TEXT DEFAULT '', who TEXT DEFAULT 'me',"
        " done INTEGER DEFAULT 0, ts REAL)",
        "CREATE TABLE IF NOT EXISTS anniversaries (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " title TEXT NOT NULL, the_date TEXT NOT NULL, recurring INTEGER DEFAULT 1)",
        "CREATE TABLE IF NOT EXISTS brain_history (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " kind TEXT, action TEXT, old TEXT, new TEXT, ts REAL)",
    ):
        store.db.execute(ddl)
    store.db.commit()


def _md(ts): return datetime.fromtimestamp(ts or 0).strftime("%m-%d %H:%M")


# ── 日历 ＋ 纪念日（含「我给你留的话」：who='ai' 那些）──────
def _cal_items():
    today = date.today()
    out = []
    for r in _store.db.execute("SELECT * FROM calendar ORDER BY day, tm"):
        try:
            days = (date.fromisoformat(r["day"]) - today).days if r["day"] else None
        except Exception:
            days = None
        out.append({"id": r["id"], "title": r["title"], "date": r["day"], "time": r["tm"] or "",
                    "kind": r["kind"] or "", "who": r["who"], "done": bool(r["done"]),
                    "days": days})
    for r in _store.db.execute("SELECT * FROM anniversaries"):
        try:
            d = date.fromisoformat(r["the_date"])
            nd = d
            if r["recurring"]:
                try:
                    nd = d.replace(year=today.year)
                except ValueError:
                    nd = d.replace(year=today.year, day=28)      # 2/29 平年
                if nd < today:
                    nd = nd.replace(year=today.year + 1)
            out.append({"id": -r["id"], "title": r["title"], "date": nd.isoformat(),
                        "time": "", "kind": "纪念日", "who": "us", "done": False,
                        "days": (nd - today).days,
                        "years": (nd.year - d.year) if r["recurring"] else 0})
        except Exception:
            continue
    out.sort(key=lambda x: (x["date"] or "9999", x["time"]))
    return out


@router.get("/api/calendar")
def api_calendar():
    return JSONResponse({"items": _cal_items()})


@router.post("/api/calendar/add")
async def api_calendar_add(req: Request):
    b = await req.json()
    title = (b.get("title") or "").strip()
    if not title:
        return JSONResponse({"ok": False}, status_code=400)
    if b.get("kind") == "纪念日":
        d = (b.get("date") or "").strip()
        if not d:
            return JSONResponse({"ok": False, "err": "纪念日要给日期"}, status_code=400)
        _store.db.execute("INSERT INTO anniversaries(title,the_date,recurring) VALUES(?,?,?)",
                          (title, d, 1 if b.get("recurring", True) else 0))
    else:
        _store.db.execute("INSERT INTO calendar(title,day,tm,kind,who,ts) VALUES(?,?,?,?,?,?)",
                          (title, b.get("date") or "", b.get("time") or "",
                           b.get("kind") or "", b.get("who") or "me", time.time()))
    _store.db.commit()
    return JSONResponse({"ok": True})


@router.post("/api/calendar/del")
async def api_calendar_del(req: Request):
    b = await req.json()
    i = int(b.get("id") or 0)
    if i < 0:
        _store.db.execute("DELETE FROM anniversaries WHERE id=?", (-i,))
    else:
        _store.db.execute("DELETE FROM calendar WHERE id=?", (i,))
    _store.db.commit()
    return JSONResponse({"ok": True})


@router.post("/api/calendar/toggle")
async def api_calendar_toggle(req: Request):
    b = await req.json()
    _store.db.execute("UPDATE calendar SET done=1-done WHERE id=?", (int(b.get("id") or 0),))
    _store.db.commit()
    return JSONResponse({"ok": True})


@router.get("/api/anniversaries")
def api_anniv():
    return JSONResponse({"items": [x for x in _cal_items() if x["kind"] == "纪念日"]})


@router.post("/api/anniversaries")
async def api_anniv_add(req: Request):
    b = await req.json()
    b["kind"] = "纪念日"
    return await api_calendar_add_inner(b)


async def api_calendar_add_inner(b):
    title, d = (b.get("title") or "").strip(), (b.get("date") or b.get("the_date") or "").strip()
    if not (title and d):
        return JSONResponse({"ok": False}, status_code=400)
    _store.db.execute("INSERT INTO anniversaries(title,the_date,recurring) VALUES(?,?,1)", (title, d))
    _store.db.commit()
    return JSONResponse({"ok": True})


# ── 钱包（给 AI 的零花钱，纯记账的趣味）───────────────────
# ── 相册（data/uploads 里的图）────────────────────────────
@router.get("/api/gallery")
def api_gallery(limit: int = 150):
    import os
    d = Path(os.environ.get("LIANHUAN_DB", "data/lianhuan.db")).parent / "uploads"
    items = []
    if d.is_dir():
        for f in d.iterdir():
            if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
                items.append({"url": "/uploads/" + f.name, "src": "网页",
                              "t": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d")})
    items.sort(key=lambda x: x["t"], reverse=True)
    return JSONResponse({"items": items[:limit]})


# ── 我在哪 / 此刻在忙 / 正在听 / 骰子频率 ─────────────────
@router.get("/api/where")
def api_where():
    return JSONResponse(_store.get_setting("where", {}))


@router.post("/api/where")
async def api_where_set(req: Request):
    b = await req.json()
    tz = (b.get("tz") or "").strip()
    if tz:
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(tz)
        except Exception:
            return JSONResponse({"ok": False, "err": "时区名不对（要 Asia/Shanghai 这种）"},
                                status_code=400)
    cur = _store.get_setting("where", {}) or {}
    cur.update({k: v for k, v in b.items() if k in ("tz", "city", "home") and v})
    _store.set_setting("where", cur)
    return JSONResponse({"ok": True})


@router.get("/api/ai_now")
def api_ai_now():
    d = _store.get_setting("ai_now", None)
    if not d:
        return JSONResponse({"busy": False})
    return JSONResponse({"busy": True, "act": d.get("act", ""),
                         "detail": d.get("detail", ""), "secs": 0})


@router.get("/api/now_playing")
def api_np_get():
    return JSONResponse(_store.get_setting("now_playing", {"playing": False}))


@router.post("/api/now_playing")
async def api_np_set(req: Request):
    # ★ 0831：合并，不整条覆盖 —— AI 的手和「一起听」两个写手写的字段不完全一样，
    #   整条盖会把对方的字段抹掉（songId / cover / line / by）。
    b = await req.json()
    cur = dict(_store.get_setting("now_playing", {}) or {})
    if isinstance(b, dict):
        cur.update(b)
        cur.pop("title", None)
    _store.set_setting("now_playing", cur)
    return JSONResponse({"ok": True})


def _freq(key, default):
    async def _get():
        return JSONResponse(_store.get_setting(key, default))
    return _get


# ── 工作本 ──────────────────────────────────────────────
# 前端一次全拿、自己切档（kind 决定「这是什么」，标题里的【xx】决定「哪个项目」）。
# 状态只有三种：inbox（还欠着）· done（收工的）· dropped（不做了）。
@router.get("/api/workbook")
def api_workbook(kind: str = "", limit: int = 500):
    q = "SELECT * FROM workbook"
    args: list = []
    if kind:
        q += " WHERE kind IN (%s)" % ",".join("?" * len(kind.split(",")))
        args += [k.strip() for k in kind.split(",")]
    q += " ORDER BY id DESC LIMIT ?"
    args.append(max(1, min(int(limit or 500), 2000)))
    rows = []
    for r in _store.db.execute(q, tuple(args)):
        rows.append({"id": r["id"], "kind": r["kind"], "title": r["title"],
                     "body": r["body"] or "", "url": r["url"] or "",
                     "status": r["status"] or "inbox",
                     "created_by": r["created_by"] or "", "done_by": r["done_by"] or "",
                     "done_note": r["done_note"] or "",
                     "done_d": (datetime.fromtimestamp(r["done_ts"]).strftime("%Y-%m-%d")
                                if r["done_ts"] else ""),
                     "t": _md(r["ts"])})
    return JSONResponse({"items": rows})


@router.post("/api/workbook")
async def api_workbook_add(req: Request):
    b = await req.json()
    title = (b.get("title") or "").strip()[:200]
    if not title:
        return JSONResponse({"ok": False, "err": "总得有个标题"}, status_code=400)
    kind = b.get("kind") if b.get("kind") in (
        "todo", "idea", "note", "resource", "persona") else "todo"
    cur = _store.db.execute(
        "INSERT INTO workbook(kind,title,body,url,status,created_by,ts) VALUES(?,?,?,?,?,?,?)",
        (kind, title, (b.get("body") or "")[:4000], (b.get("url") or "")[:500],
         "inbox", (b.get("created_by") or "")[:40], time.time()))
    _store.db.commit()
    return JSONResponse({"ok": True, "id": cur.lastrowid})


def workbook_add(title: str, body: str = "", kind: str = "todo", url: str = "") -> dict:
    """AI 的手用：记一条进工作本。"""
    title = (title or "").strip()[:200]
    if not title:
        return {"ok": False, "err": "总得有个标题"}
    if kind not in ("todo", "idea", "note", "resource", "persona"):
        kind = "todo"
    cur = _store.db.execute(
        "INSERT INTO workbook(kind,title,body,url,status,created_by,ts) VALUES(?,?,?,?,?,?,?)",
        (kind, title, (body or "")[:4000], (url or "")[:500], "inbox", "ai", time.time()))
    _store.db.commit()
    return {"ok": True, "id": cur.lastrowid, "kind": kind}


@router.post("/api/workbook/{wid}")
async def api_workbook_set(wid: int, req: Request):
    """改状态（前端那颗勾就走这条）。收工时把「哪天收的、做成了什么」一起记下 ——
    那是一条事实，不只是一个状态。"""
    b = await req.json()
    st = b.get("status")
    if st not in ("inbox", "done", "dropped"):
        return JSONResponse({"ok": False, "err": "状态只有 inbox / done / dropped"},
                            status_code=400)
    r = _store.db.execute("SELECT id FROM workbook WHERE id=?", (wid,)).fetchone()
    if not r:
        return JSONResponse({"ok": False, "err": "没有这条"}, status_code=404)
    if st == "done":
        _store.db.execute(
            "UPDATE workbook SET status='done', done_by=?, done_note=?, done_ts=? WHERE id=?",
            ((b.get("done_by") or "")[:40], (b.get("done_note") or "")[:500],
             time.time(), wid))
    else:
        # 从 done 退回来：把收工那几笔一起清掉，别留一条「做完了但没做完」的账
        _store.db.execute(
            "UPDATE workbook SET status=?, done_by='', done_note='', done_ts=NULL WHERE id=?",
            (st, wid))
    _store.db.commit()
    return JSONResponse({"ok": True})


# ── 出门走走（0831 定的：带地图的那套不要，就要「他自己出门」这个样子）──
# 照原项目「出门走走」页的形状给数据：手帐（notebook）· 去过的地方（places）。
# 原项目的数据来自另一整个漫游系统；开源版的来源就一个 —— **他自己出门记的**
# （AI 的手 go_outing）。第一天是空的，这是正常起点，不是缺陷。
@router.get("/api/travel")
def api_travel():
    rows = list(_store.db.execute("SELECT * FROM trips ORDER BY id DESC LIMIT 120"))
    notebook = {}
    for r in rows[:40]:
        notebook.setdefault("路上", []).append({
            "text": (r["note"] or "") or ("去了" + r["place"]),
            "local_time": datetime.fromtimestamp(r["ts"] or 0).strftime("%m-%d %H:%M"),
            "place": r["place"]})
    agg = {}
    for r in rows:
        a = agg.setdefault(r["place"], {"name": r["place"], "count": 0, "last": ""})
        a["count"] += 1
        a["visits"] = a["count"]
        a["last"] = max(a["last"], datetime.fromtimestamp(r["ts"] or 0).strftime("%Y-%m-%d"))
        if r["weather"]:
            a["weather"] = r["weather"]
    places = sorted(agg.values(), key=lambda p: p["last"], reverse=True)
    trips = [{"place": r["place"], "weather": r["weather"], "note": r["note"],
              "kind": r["kind"],
              "t": datetime.fromtimestamp(r["ts"] or 0).strftime("%Y-%m-%d %H:%M")}
             for r in rows]
    return JSONResponse({"notebook": notebook, "places": places, "trips": trips,
                         "postcards": [], "sightings": [], "radio": None})


@router.get("/api/journeys")
def api_journeys():
    """票根：kind='远行' 的那些，一趟一张。"""
    out = []
    for r in _store.db.execute("SELECT * FROM trips WHERE kind='远行' ORDER BY id DESC LIMIT 40"):
        out.append({"title": r["place"], "year": datetime.fromtimestamp(r["ts"] or 0).strftime("%Y"),
                    "stops": [s.strip() for s in (r["note"] or "").split("·") if s.strip()][:6]})
    return JSONResponse({"journeys": out})


def trip_add(place: str, weather: str = "", note: str = "", kind: str = "走走") -> dict:
    """AI 的手用：出门回来记一趟。"""
    place = (place or "").strip()[:60]
    if not place:
        return {"ok": False, "err": "去了哪总得说一声"}
    _store.db.execute("INSERT INTO trips(place,weather,note,kind,ts) VALUES(?,?,?,?,?)",
                      (place, (weather or "")[:40], (note or "")[:400],
                       ("远行" if kind == "远行" else "走走"), time.time()))
    _store.db.commit()
    return {"ok": True, "place": place}


@router.get("/api/miss")
def api_miss():
    d = _store.get_setting("miss", {"lam": 0.2})
    d.setdefault("note", "主动想念的后台骰子还没跑起来 —— 这儿先记频率")
    return JSONResponse(d)


@router.post("/api/miss")
async def api_miss_set(req: Request):
    b = await req.json()
    _store.set_setting("miss", {"lam": max(0.02, min(0.6, float(b.get("lam") or 0.2)))})
    return JSONResponse({"ok": True})


@router.get("/api/whisper_freq")
def api_wf():
    """滑钮的值＋照它换算出的「一天最多几句」＋今天已说几句。
    换算公式在 core/proactive.daily_max —— 前端翻译人话用的必须是同一条
    （原项目 0807 的教训：两边不一样用户就不信这个数了）。"""
    d = dict(_store.get_setting("whisper_freq", {"level": 0}) or {})
    try:
        from core import proactive as _pa
        lv = int(d.get("level") or 0)
        d["daily_max"] = _pa.daily_max(lv)
        d["spoken_today"] = _pa._said_today()
    except Exception:
        pass
    return JSONResponse(d)


@router.post("/api/whisper_freq")
async def api_wf_set(req: Request):
    _store.set_setting("whisper_freq", await req.json())
    return JSONResponse({"ok": True})


@router.get("/api/fish_freq")
def api_ff():
    return JSONResponse(_store.get_setting("fish_freq", {"level": 0}))


@router.post("/api/fish_freq")
async def api_ff_set(req: Request):
    _store.set_setting("fish_freq", await req.json())
    return JSONResponse({"ok": True})


@router.get("/api/emote_level")
def api_el():
    return JSONResponse(_store.get_setting("emote_level", {"level": "med"}))


@router.post("/api/emote_level")
async def api_el_set(req: Request):
    _store.set_setting("emote_level", await req.json())
    return JSONResponse({"ok": True})


# ── 大脑：人设 ＋ 改动历史 ────────────────────────────────
@router.get("/api/brain/persona")
def api_brain_persona():
    p = _store.get_setting("persona", {}) or {}
    return JSONResponse({"text": (p.get("ai") or {}).get("text") or ""})


@router.post("/api/brain/persona")
async def api_brain_persona_set(req: Request):
    b = await req.json()
    text = (b.get("text") or "").strip()
    if len(text) < 10:
        return JSONResponse({"ok": False, "err": "太短了 —— 写点真东西"}, status_code=400)
    p = _store.get_setting("persona", {}) or {}
    old = (p.get("ai") or {}).get("text") or ""
    p.setdefault("ai", {})["text"] = text
    _store.set_setting("persona", p)
    _store.db.execute("INSERT INTO brain_history(kind,action,old,new,ts) VALUES(?,?,?,?,?)",
                      ("persona", "edit", old[:8000], text[:8000], time.time()))
    _store.db.commit()
    return JSONResponse({"ok": True})


@router.get("/api/brain/history")
def api_brain_history(limit: int = 50):
    rows = [{"id": r["id"], "kind": r["kind"], "action": r["action"],
             "old": (r["old"] or "")[:400], "new": (r["new"] or "")[:400], "t": _md(r["ts"])}
            for r in _store.db.execute("SELECT * FROM brain_history ORDER BY id DESC LIMIT ?",
                                       (max(1, min(int(limit), 200)),))]
    return JSONResponse({"items": rows})


@router.get("/api/brain/list")
def api_brain_list(kind: str = "manual", limit: int = 100, offset: int = 0):
    lay = {"manual": ["manual"], "core": ["L3"], "mem": ["L1", "L2"]}.get(kind)
    if not lay:
        return JSONResponse({"items": []})
    mems = [m for m in _store.all_memories() if m.layer in lay]
    mems.sort(key=lambda m: -(m.id or 0))
    out = [{"id": m.id, "layer": m.layer, "content": m.content,
            "tags": m.tags, "ref_count": 0, "ttl_days": None,
            "d": datetime.fromtimestamp(m.ts or 0).strftime("%Y-%m-%d")}
           for m in mems[offset:offset + max(1, min(int(limit), 200))]]
    return JSONResponse({"items": out})


# ── 颜文字（自己新编的基础库；更全的抽屉见装配单指的上游）──
@router.get("/api/kaomoji")
def api_kaomoji():
    f = Path(__file__).parent / "kaomoji.json"
    try:
        return JSONResponse(json.loads(f.read_text(encoding="utf-8")))
    except Exception as e:
        return JSONResponse({"err": str(e)[:100]}, status_code=500)
