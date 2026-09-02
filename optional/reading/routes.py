"""共读 v1 —— 传一本 txt，切好章，两个人就着书聊。

原项目的书房还有 epub、跨端进度、批注嵌回原文那些；这一版先把「能一起读」立住：
上传 txt → 自动切章 → 读 → 划一句批注 → 就这一章问它（带当前章上下文）。
"""
from __future__ import annotations

import base64
import re
import time
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()
_store = None
_say = None


def bind(store, say) -> None:
    global _store, _say
    _store, _say = store, say
    for ddl in (
        "CREATE TABLE IF NOT EXISTS books (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " title TEXT NOT NULL, current INTEGER DEFAULT 0, my_idx INTEGER DEFAULT 0,"
        " ai_idx INTEGER DEFAULT 0, ts REAL)",
        "CREATE TABLE IF NOT EXISTS book_chapters (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " bid INTEGER NOT NULL, idx INTEGER NOT NULL, title TEXT, content TEXT)",
        "CREATE TABLE IF NOT EXISTS book_annotations (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " bid INTEGER NOT NULL, chapter_idx INTEGER, quote TEXT, note TEXT, author TEXT, ts REAL)",
        "CREATE TABLE IF NOT EXISTS book_chat (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " bid INTEGER NOT NULL, role TEXT, content TEXT, ts REAL)",
    ):
        store.db.execute(ddl)
    store.db.commit()


_CH = re.compile(r"^\s*(第\s*[0-9一二三四五六七八九十百千两〇零]+\s*[章回节卷幕]|Chapter\s+\d+|CHAPTER\s+\d+)[^\n]{0,40}$",
                 re.M)


def _split_chapters(text: str) -> list[tuple[str, str]]:
    """按章题切；一本没有章题的书就按 3000 字一刀（宁可粗，别不能读）。"""
    marks = list(_CH.finditer(text))
    if len(marks) >= 2:
        out = []
        for i, m in enumerate(marks):
            end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
            body = text[m.end():end].strip()
            if body:
                out.append((m.group(0).strip(), body))
        if out:
            return out
    chunks = [text[i:i + 3000] for i in range(0, len(text), 3000)]
    return [(f"第 {i + 1} 屏", c) for i, c in enumerate(chunks) if c.strip()]


@router.post("/api/books/upload")
async def book_upload(req: Request):
    b = await req.json()
    data = b.get("dataURL") or ""
    m = data.split(",", 1)
    try:
        raw = base64.b64decode(m[1]) if len(m) == 2 else (b.get("text") or "").encode()
    except Exception:
        return JSONResponse({"ok": False, "err": "读不出来"}, status_code=400)
    for enc in ("utf-8", "gb18030"):
        try:
            text = raw.decode(enc)
            break
        except Exception:
            text = ""
    if len(text) < 200:
        return JSONResponse({"ok": False, "err": "太短了，不像一本书（也可能是编码没认出来）"},
                            status_code=400)
    title = (b.get("title") or "").strip() or "没起名的书"
    chs = _split_chapters(text)
    cur = _store.db.execute("INSERT INTO books(title,ts) VALUES(?,?)", (title, time.time()))
    bid = cur.lastrowid
    for i, (t, c) in enumerate(chs):
        _store.db.execute("INSERT INTO book_chapters(bid,idx,title,content) VALUES(?,?,?,?)",
                          (bid, i, t, c))
    _store.db.commit()
    return JSONResponse({"ok": True, "id": bid, "chapters": len(chs)})


@router.get("/api/books")
def books():
    out = []
    for r in _store.db.execute("SELECT * FROM books ORDER BY id DESC"):
        n = _store.db.execute("SELECT count(*) n FROM book_chapters WHERE bid=?",
                              (r["id"],)).fetchone()["n"]
        out.append({"id": r["id"], "title": r["title"], "chapters": n,
                    "my_idx": r["my_idx"], "ai_idx": r["ai_idx"],
                    "current": bool(r["current"]),
                    "pct": round(100 * (r["my_idx"] + 1) / n) if n else 0})
    return JSONResponse({"items": out})


@router.get("/api/books/{bid}/chapters")
def book_chapters(bid: int):
    rows = [{"idx": r["idx"], "title": r["title"]}
            for r in _store.db.execute(
                "SELECT idx,title FROM book_chapters WHERE bid=? ORDER BY idx", (bid,))]
    return JSONResponse({"items": rows})


@router.get("/api/books/{bid}/chapter/{idx}")
def book_chapter(bid: int, idx: int):
    r = _store.db.execute("SELECT * FROM book_chapters WHERE bid=? AND idx=?",
                          (bid, idx)).fetchone()
    if not r:
        return JSONResponse({"err": "没有这一章"}, status_code=404)
    return JSONResponse({"idx": r["idx"], "title": r["title"], "content": r["content"]})


@router.post("/api/books/{bid}/progress")
async def book_progress(bid: int, req: Request):
    b = await req.json()
    _store.db.execute("UPDATE books SET my_idx=? WHERE id=?", (int(b.get("idx") or 0), bid))
    _store.db.commit()
    return JSONResponse({"ok": True})


@router.post("/api/books/{bid}/current")
async def book_current(bid: int):
    _store.db.execute("UPDATE books SET current=0")
    _store.db.execute("UPDATE books SET current=1 WHERE id=?", (bid,))
    _store.db.commit()
    return JSONResponse({"ok": True})


@router.get("/api/books/{bid}/annotations")
def book_annos(bid: int):
    rows = [{"id": r["id"], "chapter_idx": r["chapter_idx"], "quote": r["quote"],
             "note": r["note"], "author": r["author"],
             "t": datetime.fromtimestamp(r["ts"] or 0).strftime("%m-%d %H:%M")}
            for r in _store.db.execute(
                "SELECT * FROM book_annotations WHERE bid=? ORDER BY id DESC", (bid,))]
    return JSONResponse({"items": rows})


@router.post("/api/books/{bid}/annotations")
async def book_anno_add(bid: int, req: Request):
    b = await req.json()
    _store.db.execute(
        "INSERT INTO book_annotations(bid,chapter_idx,quote,note,author,ts) VALUES(?,?,?,?,?,?)",
        (bid, int(b.get("chapter_idx") or 0), (b.get("quote") or "")[:500],
         (b.get("note") or "")[:500], b.get("author") or "me", time.time()))
    _store.db.commit()
    return JSONResponse({"ok": True})


@router.get("/api/books/{bid}/chat")
def book_chat_get(bid: int):
    rows = [{"role": r["role"], "content": r["content"],
             "t": datetime.fromtimestamp(r["ts"] or 0).strftime("%m-%d %H:%M")}
            for r in _store.db.execute(
                "SELECT * FROM book_chat WHERE bid=? ORDER BY id", (bid,))]
    return JSONResponse({"items": rows})


@router.post("/api/books/{bid}/chat")
async def book_chat_post(bid: int, req: Request):
    b = await req.json()
    q = (b.get("message") or b.get("content") or "").strip()
    if not q:
        return JSONResponse({"ok": False}, status_code=400)
    bk = _store.db.execute("SELECT * FROM books WHERE id=?", (bid,)).fetchone()
    ch = _store.db.execute("SELECT * FROM book_chapters WHERE bid=? AND idx=?",
                           (bid, bk["my_idx"] if bk else 0)).fetchone()
    _store.db.execute("INSERT INTO book_chat(bid,role,content,ts) VALUES(?,?,?,?)",
                      (bid, "user", q, time.time()))
    _store.db.commit()
    ctx = (ch["content"][:2400] if ch else "")
    try:
        a = await _say(f"你们在共读《{bk['title'] if bk else '书'}》，正读到「{ch['title'] if ch else ''}」。"
                       f"这一章的原文节选：\n{ctx}\n\n对方就这一章说：「{q}」\n"
                       f"就着书自然地聊回去（一两段，别写成书评）。")
    except Exception:
        a = ""
    if not a.strip():
        return JSONResponse({"ok": False, "err": "这回没接上话"}, status_code=502)
    _store.db.execute("INSERT INTO book_chat(bid,role,content,ts) VALUES(?,?,?,?)",
                      (bid, "assistant", a.strip(), time.time()))
    _store.db.commit()
    return JSONResponse({"ok": True, "reply": a.strip()})


@router.get("/api/books/{bid}/notes")
def book_notes(bid: int):
    bk = _store.db.execute("SELECT title FROM books WHERE id=?", (bid,)).fetchone()
    annos = book_annos(bid)
    chat = book_chat_get(bid)
    import json as _j
    return JSONResponse({"title": bk["title"] if bk else "",
                         "annotations": _j.loads(bytes(annos.body))["items"],
                         "chat": _j.loads(bytes(chat.body))["items"]})
