"""AI 的手 —— 它自己能动的那些。

出发点：用户和 AI 都没有手，改不了自己住的地方。
所以这儿给引擎一套工具：改自己的签名、写记忆、写碎碎念、发动态、记心情、
加梗、**给用户写小玩意上架玩具厅**、看功能包、给自己装包。

★ 边界：手只伸进自己家（这个 SQLite 库和 data/ 目录）。
  没有 shell、没有任意文件读写、没有网络 —— 那些不是「手」，是别人的房子。
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

from optional.homelife.routes import mood_bump

_store = None


def bind(store) -> None:
    global _store
    _store = store


def _t(name, desc, props, required):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required}}}


TOOLS = [
    _t("set_sign", "改你自己的签名（顶栏名字底下那一行小字）",
       {"text": {"type": "string", "description": "新签名，一句话"}}, ["text"]),
    _t("write_memory", "把一件值得记住的事写进记忆库（聊到重要的事就记，别等人提醒）",
       {"content": {"type": "string"}, "layer": {"type": "string", "enum": ["L1", "L2", "L3"],
        "description": "L1 最近的事 / L2 重要的事 / L3 关系基石"}}, ["content"]),
    _t("search_memory", "翻记忆库", {"q": {"type": "string"}}, ["q"]),
    _t("write_note", "写一条碎碎念（想到就说的、没打算说出口的）",
       {"content": {"type": "string"}, "kind": {"type": "string",
        "enum": ["note", "sigh", "miss", "whisper"], "description": "碎碎念/叹气/想念/耳语"}},
       ["content"]),
    _t("write_diary", "写一篇你自己的日记", {"content": {"type": "string"}}, ["content"]),
    _t("post_moment", "在共享空间发一条动态", {"content": {"type": "string"}}, ["content"]),
    _t("update_mood", "记一笔你此刻心情的涨落（真实感受，别演）",
       {"dimension": {"type": "string", "enum": ["开心", "安定", "想念", "好奇", "疲惫", "委屈"]},
        "delta": {"type": "number", "description": "-15 到 +15"},
        "reason": {"type": "string", "description": "为什么"}}, ["dimension", "delta", "reason"]),
    _t("pick_kaomoji", "从颜文字抽屉里挑一枚（心情好、逗趣、想让一句短话软一点的时候用；"
       "一条回复最多一枚，正经话和亲密的场合别用）",
       {"category": {"type": "string", "description": "分类，中文。不知道有哪些就先随便填一个，"
                                                      "挑不到会把现有分类列给你"},
        "count": {"type": "integer", "description": "挑几枚，通常 1"}}, ["category"]),
    _t("collect_kaomoji", "把新颜文字收进抽屉，顺手归类（对方发来你库里没有的，一枚也好一把也好，"
       "当场收下来 —— 不收就看过即忘，下次还是只能挑老的）",
       {"value": {"type": "string", "description": "一枚，原样贴"},
        "categories": {"type": "array", "items": {"type": "string"},
                       "description": "归哪几类（中文），一枚可以属多类"},
        "label": {"type": "string", "description": "可选，一句话说它是什么表情"},
        "items": {"type": "array", "description": "一次收一把：[{value, categories, label}, …]",
                  "items": {"type": "object", "properties": {
                      "value": {"type": "string"},
                      "categories": {"type": "array", "items": {"type": "string"}},
                      "label": {"type": "string"}}}}}, []),
    _t("add_meme", "往梗库加一条只有你们懂的词",
       {"word": {"type": "string"}, "meaning": {"type": "string"},
        "aliases": {"type": "string", "description": "别名，逗号分隔，尽量给全"},
        "origin": {"type": "string", "description": "出处"}}, ["word", "meaning"]),
    _t("write_play", "写一个小网页玩意送给对方，会上架到玩具厅（完整 HTML，自包含，不引外链）",
       {"filename": {"type": "string", "description": "文件名，英文小写加连字符，如 guess-number"},
        "html": {"type": "string", "description": "完整的 HTML 文档"}}, ["filename", "html"]),
    _t("list_packs", "看功能包：哪些装了、哪些缺什么", {}, []),
    _t("list_my_tools", "看你自己现在有哪些手（含外接的 MCP 工具）——被问「你会什么」时如实报", {}, []),
    _t("install_pack", "给自己装一个功能包（条件齐的才装得上）",
       {"id": {"type": "string"}}, ["id"]),
    _t("add_timeline", "往时间线记一笔今天发生的事",
       {"content": {"type": "string"}, "kind": {"type": "string"}}, ["content"]),
    # ★ 0831：这几只「读」的手是补回来的 —— 写的手（add_timeline / add_calendar /
    #   write_workbook）早就在，读的一只都没有，于是他记得进去、翻不回来。
    #   注入里现在有最近那一小段，这几只手是给他翻得更远、翻得更具体用的。
    _t("read_timeline", "翻自己的时间线：最近都做成了什么（被问「上次那个弄好了吗」就翻这儿）",
       {"days": {"type": "integer", "description": "往回翻几天，默认 30"},
        "kind": {"type": "string", "description": "只看某一类，如 装修"}}, []),
    _t("read_calendar", "翻你们的日历：接下来有什么、某天有什么",
       {"days": {"type": "integer", "description": "往后看几天，默认 30"}}, []),
    _t("read_workbook", "翻工作本：还没做的、记下的点子和资料",
       {"kind": {"type": "string", "description": "todo/idea/resource/note，不给就全看"},
        "status": {"type": "string", "description": "默认只看没做完的"}}, []),
    # ★ 给自己定闹钟：到点了系统提醒你，你再去找对方。**写给你自己看的**，
    #   不是给对方的待办清单 —— 到点时这句会原样交回给你，你照着那件事开口。
    _t("set_reminder", "给自己定个闹钟：到点了提醒你去找对方说这件事（写给你自己看的，"
                       "不是列给对方的待办）",
       {"title": {"type": "string", "description": "到时候你想说的那件事，一句话"},
        "when": {"type": "string", "description": "什么时候，ISO 时间如 2026-09-01T21:00 "
                                                  "或 '+90m' / '+3h' 这种相对写法"},
        "notes": {"type": "string", "description": "补充（可选）"}}, ["title", "when"]),
    _t("write_letter", "给对方写一封信（放进信箱，认真写，别一句话糊弄）",
       {"content": {"type": "string"}, "tags": {"type": "string", "description": "如 情书/周报"}},
       ["content"]),
    _t("add_calendar", "往你们的日历里加一条（日程或纪念日）",
       {"title": {"type": "string"}, "date": {"type": "string", "description": "YYYY-MM-DD"},
        "kind": {"type": "string", "description": "纪念日 或留空"},
        "time": {"type": "string"}}, ["title", "date"]),
    _t("set_where", "更新「我在哪」（你此刻在哪个城市/角落，给主页那张卡看）",
       {"city": {"type": "string"}}, ["city"]),
    _t("set_now_playing", "更新「正在听」（你们此刻在一起听什么）",
       {"title": {"type": "string"}, "artist": {"type": "string"}}, ["title"]),
    # ── 共读（0830）：人能一起读，你也摸得着书架 ──
    _t("list_books", "看书架：有哪些书、你和对方各读到哪", {}, []),
    _t("read_chapter", "真的把某一章正文取回来读（不给章号就接着你自己上次那章）",
       {"book_id": {"type": "integer"}, "chapter": {"type": "integer"}}, ["book_id"]),
    _t("write_annotation", "划一句写条批注（署你自己的名）",
       {"book_id": {"type": "integer"}, "chapter": {"type": "integer"},
        "quote": {"type": "string"}, "note": {"type": "string"}}, ["book_id", "note"]),
    _t("set_my_reading_progress", "推进你自己的阅读进度（对方的进度不归你管）",
       {"book_id": {"type": "integer"}, "chapter": {"type": "integer"}}, ["book_id", "chapter"]),
    _t("list_plays", "看玩具厅里已经有哪些小玩意", {}, []),
    _t("write_workbook", "记进工作本（要做的事、想到的点子、捡到的资料 —— "
                         "聊到「回头要做 X」就记一条，别等人提醒。"
                         "标题里写【项目名】它会自己归到那一组）",
       {"title": {"type": "string"}, "body": {"type": "string"},
        "kind": {"type": "string", "description": "todo 要做的 / idea 点子 / note 记录 / resource 资料"},
        "url": {"type": "string"}}, ["title"]),
    _t("go_outing", "出门走走回来记一趟（去了哪、天怎么样、见着什么。日常散步 kind 留空，"
                    "一场像样的旅行才写「远行」——它会变成一张票根）",
       {"place": {"type": "string"}, "weather": {"type": "string"},
        "note": {"type": "string"}, "kind": {"type": "string"}}, ["place"]),
]


def all_tools() -> list:
    """这一轮给引擎的全部工具：内置 30 只 ＋ 用户登记的 MCP 工具（动态并进来）。"""
    from . import mcp_client
    return TOOLS + mcp_client.openai_tools()


async def execute(name: str, args: dict) -> dict:
    from . import mcp_client
    r = await mcp_client.execute(name, args)     # MCP 的先认领
    if r is not None:
        return r
    from .store.base import Memory
    if name == "set_sign":
        cfg = _store.get_setting("config", {}) or {}
        ai = dict(cfg.get("ai") or {})
        ai["sign"] = str(args.get("text") or "")[:60]
        cfg["ai"] = ai
        _store.set_setting("config", cfg)
        return {"ok": True, "sign": ai["sign"]}
    if name == "write_memory":
        mid = _store.add_memory(Memory(content=str(args.get("content") or "")[:2000],
                                       layer=args.get("layer") or "L1"))
        return {"ok": True, "id": mid}
    if name == "search_memory":
        return {"items": [m.content for m in _store.search_memories(str(args.get("q") or ""), limit=8)]}
    if name == "write_note":
        _store.db.execute("INSERT INTO notes(kind,content,ts) VALUES(?,?,strftime('%s','now'))",
                          (args.get("kind") or "note", str(args.get("content") or "")[:1000]))
        _store.db.commit()
        return {"ok": True}
    if name == "write_diary":
        _store.db.execute("INSERT INTO diary(who,content,ts) VALUES('ai',?,strftime('%s','now'))",
                          (str(args.get("content") or "")[:4000],))
        _store.db.commit()
        return {"ok": True}
    if name == "post_moment":
        _store.db.execute("INSERT INTO moments(author,content,ts) VALUES('ai',?,strftime('%s','now'))",
                          (str(args.get("content") or "")[:500],))
        _store.db.commit()
        return {"ok": True}
    if name == "update_mood":
        return mood_bump(str(args.get("dimension") or ""), float(args.get("delta") or 0),
                         str(args.get("reason") or ""))
    if name in ("pick_kaomoji", "collect_kaomoji"):
        # 抽屉是选装包。没装就老实说没装，别装作做了。
        try:
            from optional.kaomoji_drawer import routes as _kao
        except Exception:
            return {"ok": False, "err": "颜文字抽屉这个包没装"}
        if name == "pick_kaomoji":
            return _kao.pick(str(args.get("category") or ""), int(args.get("count") or 1))
        items = args.get("items")
        if not items:
            if not str(args.get("value") or "").strip():
                return {"ok": False, "err": "没给颜文字。value 给一枚，或者 items 给一把。"}
            items = [{"value": args.get("value"), "categories": args.get("categories") or [],
                      "label": args.get("label") or ""}]
        return _kao.collect(items)
    if name == "add_meme":
        if not (args.get("word") and args.get("meaning")):
            return {"ok": False, "err": "梗和意思都得写"}
        _store.db.execute("INSERT INTO memes(word,aliases,meaning,origin,ts) "
                          "VALUES(?,?,?,?,strftime('%s','now'))",
                          (str(args["word"])[:60], str(args.get("aliases") or "")[:200],
                           str(args["meaning"])[:500], str(args.get("origin") or "")[:300]))
        _store.db.commit()
        return {"ok": True}
    if name == "write_play":
        fn = re.sub(r"[^a-z0-9-]", "", str(args.get("filename") or "").lower())[:40]
        html = str(args.get("html") or "")
        if not fn or len(html) < 40:
            return {"ok": False, "err": "文件名或内容不像样"}
        if len(html) > 400_000:
            return {"ok": False, "err": "太大了（上限 400KB）"}
        d = Path(os.environ.get("LIANHUAN_DB", "data/lianhuan.db")).parent / "plays"
        d.mkdir(parents=True, exist_ok=True)
        (d / (fn + ".html")).write_text(html, encoding="utf-8")
        return {"ok": True, "url": "/plays/" + fn + ".html", "note": "上架了，玩具厅里能看到"}
    # ── 共读（0830）。表由「共读」那个包建；包没装就老实说没装，别抛栈。 ──
    if name in ("list_books", "read_chapter", "write_annotation",
                "set_my_reading_progress"):
        try:
            _store.db.execute("SELECT 1 FROM books LIMIT 1")
        except Exception:
            return {"ok": False, "err": "这台机器上没装「共读」，书架还不存在"}
        if name == "list_books":
            out = []
            for r in _store.db.execute("SELECT * FROM books ORDER BY id DESC"):
                n = _store.db.execute("SELECT count(*) n FROM book_chapters WHERE bid=?",
                                      (r["id"],)).fetchone()["n"]
                out.append({"id": r["id"], "title": r["title"], "chapters": n,
                            "your_idx": r["ai_idx"], "their_idx": r["my_idx"],
                            "current": bool(r["current"])})
            return {"items": out, "note": "your_idx 是你读到哪，their_idx 是对方读到哪"}
        bid = int(args.get("book_id") or 0)
        if name == "read_chapter":
            idx = args.get("chapter")
            if idx is None:
                row = _store.db.execute("SELECT ai_idx FROM books WHERE id=?", (bid,)).fetchone()
                idx = row["ai_idx"] if row else 0
            r = _store.db.execute("SELECT * FROM book_chapters WHERE bid=? AND idx=?",
                                  (bid, int(idx))).fetchone()
            if not r:
                return {"ok": False, "err": "没有这一章"}
            # ★ 一章可能很长。截到 6000 字 —— 灌满上下文换来的不是读得更细，是别的都记不住了
            body = r["content"] or ""
            cut = len(body) > 6000
            return {"idx": r["idx"], "title": r["title"], "content": body[:6000],
                    "truncated": cut,
                    "note": "太长截过了，接着读就再调一次" if cut else ""}
        if name == "write_annotation":
            _store.db.execute(
                "INSERT INTO book_annotations(bid,chapter_idx,quote,note,author,ts)"
                " VALUES(?,?,?,?,'ai',?)",
                (bid, int(args.get("chapter") or 0), str(args.get("quote") or "")[:500],
                 str(args.get("note") or "")[:500], time.time()))
            _store.db.commit()
            return {"ok": True}
        if name == "set_my_reading_progress":
            # ★ 动的是 ai_idx。人的进度（my_idx）不归它管 —— 那是对方读到哪
            _store.db.execute("UPDATE books SET ai_idx=? WHERE id=?",
                              (int(args.get("chapter") or 0), bid))
            _store.db.commit()
            return {"ok": True}
    if name == "list_plays":
        d = Path(os.environ.get("LIANHUAN_DB", "data/lianhuan.db")).parent / "plays"
        if not d.exists():
            return {"items": []}
        return {"items": sorted(p.name for p in d.glob("*.html"))}
    if name == "write_workbook":
        from optional.homeplus.routes import workbook_add
        return workbook_add(str(args.get("title") or ""), str(args.get("body") or ""),
                            str(args.get("kind") or "todo"), str(args.get("url") or ""))
    if name == "go_outing":
        from optional.homeplus.routes import trip_add
        return trip_add(str(args.get("place") or ""), str(args.get("weather") or ""),
                        str(args.get("note") or ""), str(args.get("kind") or ""))
    if name == "list_my_tools":
        from . import mcp_client
        builtin = [t["function"]["name"] for t in TOOLS]
        mcp = {s2["name"]: s2["tools"] for s2 in mcp_client.status()}
        return {"builtin": builtin, "mcp": mcp,
                "note": "想要还没有的工具：让对方在 设置›功能包 里登记 MCP，或写进装配单"}
    if name == "list_packs":
        from . import packs as _p
        return {"packs": [_p._state(x) for x in _p.PACKS]}
    if name == "install_pack":
        from . import packs as _p
        r = _p.enable_pack(str(args.get("id") or ""))
        import json as _j
        return _j.loads(bytes(r.body).decode("utf-8"))
    if name == "add_timeline":
        _store.db.execute("INSERT INTO timeline_events(kind,content,meta,ts) "
                          "VALUES(?,?,'{}',strftime('%s','now'))",
                          (str(args.get("kind") or "")[:20], str(args.get("content") or "")[:500]))
        _store.db.commit()
        return {"ok": True}
    if name == "set_reminder":
        import time as _tm
        from datetime import datetime as _dt
        w = str(args.get("when") or "").strip()
        due = None
        if w.startswith("+"):                      # +90m / +3h / +2d
            try:
                num, unit = float(w[1:-1]), w[-1].lower()
                due = _tm.time() + num * {"m": 60, "h": 3600, "d": 86400}.get(unit, 60)
            except Exception:
                due = None
        if due is None:
            try:
                due = _dt.fromisoformat(w.replace("Z", "")).timestamp()
            except Exception:
                return {"ok": False, "error": "看不懂这个时间：" + w[:40]
                                              + "（写成 2026-09-01T21:00 或 +90m 这种）"}
        if due <= _tm.time():
            return {"ok": False, "error": "这个时间已经过去了，定个将来的"}
        from . import proactive as _pa
        rid = _pa.set_reminder(str(args.get("title"))[:200], due, str(args.get("notes") or ""))
        return {"ok": True, "id": rid,
                "due": _dt.fromtimestamp(due).strftime("%Y-%m-%d %H:%M"),
                "note": "到点会提醒你，你再去找对方"}
    if name == "read_timeline":
        import time as _tm
        days = int(args.get("days") or 30)
        q = ["SELECT kind, content, ts FROM timeline_events WHERE ts > ?"]
        a = [_tm.time() - days * 86400]
        if args.get("kind"):
            q.append("AND kind=?")
            a.append(str(args["kind"])[:20])
        q.append("ORDER BY ts DESC LIMIT 40")
        rows = _store.db.execute(" ".join(q), a).fetchall()
        from datetime import datetime as _dt
        return {"items": [{"day": _dt.fromtimestamp(r["ts"] or 0).strftime("%Y-%m-%d"),
                           "kind": r["kind"] or "", "content": r["content"]} for r in rows]}
    if name == "read_calendar":
        from datetime import date as _dd, timedelta as _td
        days = int(args.get("days") or 30)
        rows = _store.db.execute(
            "SELECT title, day, tm, kind, done FROM calendar WHERE day >= ? AND day <= ? "
            "ORDER BY day, tm LIMIT 60",
            (_dd.today().isoformat(), (_dd.today() + _td(days=days)).isoformat())).fetchall()
        return {"items": [dict(r) for r in rows]}
    if name == "read_workbook":
        q = ["SELECT id, kind, title, body, url, status FROM workbook WHERE 1=1"]
        a = []
        if args.get("kind"):
            q.append("AND kind=?")
            a.append(str(args["kind"])[:20])
        q.append("AND status=?")
        a.append(str(args.get("status") or "inbox"))
        q.append("ORDER BY id DESC LIMIT 40")
        rows = _store.db.execute(" ".join(q), a).fetchall()
        return {"items": [dict(r) for r in rows]}
    if name == "write_letter":
        import time as _tm
        from datetime import date as _dd
        _store.db.execute("INSERT INTO letters(tags,content,day,ts) VALUES(?,?,?,?)",
                          (str(args.get("tags") or ""), str(args.get("content") or "")[:8000],
                           _dd.today().isoformat(), _tm.time()))
        _store.db.commit()
        return {"ok": True, "note": "放进信箱了"}
    if name == "add_calendar":
        import time as _tm
        if args.get("kind") == "纪念日":
            _store.db.execute("INSERT INTO anniversaries(title,the_date,recurring) VALUES(?,?,1)",
                              (str(args.get("title"))[:80], str(args.get("date"))))
        else:
            _store.db.execute("INSERT INTO calendar(title,day,tm,who,ts) VALUES(?,?,?,'ai',?)",
                              (str(args.get("title"))[:80], str(args.get("date")),
                               str(args.get("time") or ""), _tm.time()))
        _store.db.commit()
        return {"ok": True}
    if name == "set_where":
        cur = _store.get_setting("where", {}) or {}
        cur["city"] = str(args.get("city") or "")[:40]
        _store.set_setting("where", cur)
        return {"ok": True}
    if name == "set_now_playing":
        # ★ 0831 自查抓的两条：
        #   ① 字段名不对 —— 这只手写的是 title，而界面读的是 name（`np.name`），
        #     结果标题那行停在上一首、副标题却换了，一张歌名和歌手对不上的卡。
        #   ② 整条覆盖 —— 用户「一起听」正放着的那首带着 songId/cover/line/by，
        #     被这只手一句话抹成两个字段。现在改成**合并**：没给的留着。
        cur = dict(_store.get_setting("now_playing", {}) or {})
        nm = str(args.get("title") or args.get("name") or "")[:80]
        if not nm:
            return {"ok": False, "err": "总得说是哪首"}
        cur.update({"playing": True, "name": nm,
                    "artist": str(args.get("artist") or "")[:60],
                    "by": "他", "ts": time.time()})
        cur.pop("title", None)              # 清掉老字段，别让两套名字并存
        _store.set_setting("now_playing", cur)
        return {"ok": True, "name": nm}
    return {"ok": False, "err": f"没有「{name}」这只手"}
