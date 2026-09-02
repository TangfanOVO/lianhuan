"""颜文字抽屉 —— fuyue-kaomoji-drawer 的后端半边（那是这家自己发布的开源项目，MIT）。

前端组件整套在 web/vendor/（React 抽屉 + 数据层适配），后端就这一个状态文件：
`data/kaomoji_v2.json`。第一次打开用组件自带的默认库铺底。
op 协议照上游：upsert / remove / markUsed / setFavorite / setCategoryOrder。
"""
from __future__ import annotations

import datetime
import json
import os
import threading
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()
_LOCK = threading.Lock()


def _file() -> Path:
    return Path(os.environ.get("LIANHUAN_DB", "data/lianhuan.db")).parent / "kaomoji_v2.json"


def _read() -> dict:
    try:
        return json.loads(_file().read_text(encoding="utf-8"))
    except Exception:
        pass
    # 第一次：用组件自带的默认库铺底
    seed = Path(__file__).parent / "default_state.json"
    items = []
    try:
        for e in json.loads(seed.read_text(encoding="utf-8")):
            items.append({"value": e["value"], "categories": e.get("categories") or ["未分类"],
                          "favorite": False, "useCount": 0,
                          "compatibility": "stable", "compatibilityNotes": []})
    except Exception:
        pass
    return {"version": 4, "items": items, "removed": [], "categoryOrder": []}


def _write(st: dict) -> None:
    f = _file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def _find(st, value):
    return next((i for i in st["items"] if i.get("value") == value), None)


# ══ 给 AI 用的那两只手（挑 / 收）══════════════════════════════
# 抽屉本来只有人点得动：网页上收藏、删除、拖分类，全是手指的活。
# AI 这头一只手都没有 —— 它挑不了，也收不了：对方发来一枚新的，看过就没了。
# 下面这几个纯函数给 core/hands.py 用，走的还是上面那套 _LOCK ＋ _read/_write，
# 不另开写入口。
#
# 归一化和「会不会显示成豆腐块」的判定，是照上游组件里 analyzeKaomoji 那三条重写的：
# 控制字符传不过去、叠太多组合符号有些设备画成黑条、罕见字形缺字体会变方块。
# 按码点写而不是写进字符类 —— 控制字符直接落在源码里会带出 NUL，读都读不了。
_BAD_CP = set(range(0x00, 0x09)) | {0x0B, 0x0C} | set(range(0x0E, 0x20)) | {0xFFFD}
_BIDI_CP = {0x061C, 0x200E, 0x200F, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
            0x2066, 0x2067, 0x2068, 0x2069, 0xFEFF}
_RISKY = ((0x0980, 0x0DFF), (0x0F00, 0x0FFF), (0x1000, 0x109F), (0x1780, 0x17FF))
_MARKS = ("Mn", "Mc", "Me")


def normalize(value: str) -> str:
    import unicodedata
    return unicodedata.normalize(
        "NFC", "".join(c for c in (value or "") if ord(c) not in _BIDI_CP)).strip()


def _mark_run(s: str) -> int:
    import unicodedata
    best = run = 0
    for ch in s:
        run = run + 1 if unicodedata.category(ch) in _MARKS else 0
        best = max(best, run)
    return best


def analyze(value: str) -> dict:
    """这一枚在别人手机上会不会变成豆腐块。stable / limited / blocked。"""
    import unicodedata
    clean = normalize(value)
    notes = []
    if any(ord(c) in _BAD_CP for c in clean):
        notes.append("含有传不过去的字符")
    if _mark_run(unicodedata.normalize("NFD", clean)) >= 3:
        notes.append("叠加符号较多，有些设备会画成黑条")
    if any(any(lo <= ord(c) <= hi for lo, hi in _RISKY) for c in clean):
        notes.append("用了罕见字形，缺字体时会变方块")
    safe = "".join(c for c in unicodedata.normalize("NFD", clean)
                   if unicodedata.category(c) not in _MARKS
                   and ord(c) not in _BIDI_CP
                   and not any(lo <= ord(c) <= hi for lo, hi in _RISKY))
    out = {"value": clean,
           "compatibility": "blocked" if any(ord(c) in _BAD_CP for c in clean)
                            else ("limited" if notes else "stable"),
           "compatibilityNotes": notes}
    safe = unicodedata.normalize("NFC", safe).strip()
    if safe and safe != clean:
        out["safeValue"] = safe
    return out


def categories(st: dict | None = None) -> list:
    st = st or _read()
    out = [c for c in (st.get("categoryOrder") or []) if c]
    seen = set(out)
    for it in st["items"]:
        for c in it.get("categories") or []:
            if c not in seen:
                seen.add(c)
                out.append(c)
    return out


def collect(items) -> dict:
    """收一枚或一把进抽屉，按分类归好。

    ★ 两条不肯让的：**对方亲手删过的不许再塞回来**（`removed` 那张名单就是为这个存在的）；
      传不过去的字符（blocked）一律不收 —— 收进去等于往库里埋一颗以后必炸的雷。
      叠加符号多的（limited）照收，抽屉自己会标出来，因为很多好看的颜文字本来就带组合符号。
    """
    if isinstance(items, (str, dict)):
        items = [items]
    items = [i for i in (items or []) if i]
    if not items:
        return {"ok": False, "err": "没给颜文字"}
    收了, 补了分类, 本来就有, 删过的, 没收 = [], [], [], [], []
    缺分类 = False
    with _LOCK:
        st = _read()
        removed = set(st.get("removed") or [])
        for one in items[:80]:
            if isinstance(one, str):
                one = {"value": one}
            val = normalize(one.get("value") or "")
            if not val:
                continue
            cats = [c.strip() for c in (one.get("categories") or []) if (c or "").strip()]
            if not cats:
                缺分类 = True
            if val in removed:
                删过的.append(val)
                continue
            a = analyze(val)
            if a["compatibility"] == "blocked":
                没收.append({"颜文字": val, "为什么": "；".join(a["compatibilityNotes"])})
                continue
            it = _find(st, val)
            if it:
                新加的 = [c for c in cats if c not in (it.get("categories") or [])]
                if not 新加的:
                    本来就有.append(val)
                    continue
                it["categories"].extend(新加的)
                补了分类.append(val)
            else:
                it = {"value": val, "categories": cats or ["未分类"],
                      "favorite": False, "useCount": 0,
                      "compatibility": a["compatibility"],
                      "compatibilityNotes": a["compatibilityNotes"]}
                if a.get("safeValue"):
                    it["safeValue"] = a["safeValue"]
                if (one.get("label") or "").strip():
                    it["label"] = one["label"].strip()
                st["items"].append(it)
                收了.append(val)
            st["removed"] = [r for r in st["removed"] if r != val]
        _write(st)
        cats_now = categories(st)
    out = {"ok": True, "收了": 收了, "给旧的补了分类": 补了分类,
           "本来就有": 本来就有, "现有分类": cats_now}
    if 删过的:
        out["删过所以没收"] = 删过的
    if 没收:
        out["没收进去"] = 没收
    if 缺分类:
        out["提醒"] = "有几枚没给分类，先放「未分类」了 —— 分类你自己看着定，不够用就起个新的。"
    return out


def pick(category: str, count: int = 1) -> dict:
    """挑几枚。收藏的、常用的更容易被挑到；刚用过的先歇一会儿；易乱码的少出。"""
    import datetime as _dt
    import random
    with _LOCK:
        st = _read()
        cat = (category or "").strip()
        pool = [i for i in st["items"] if cat in (i.get("categories") or [])]
        if not pool:
            return {"err": f"没有「{cat}」这一类", "现有分类": categories(st)}
        now = _dt.datetime.now(_dt.timezone.utc)

        def w(it):
            x = 1.0 + (2.5 if it.get("favorite") else 0)
            x += min(int(it.get("useCount") or 0), 8) * 0.35     # 封顶，别让一枚吃掉整池
            if it.get("compatibility") != "stable":
                x *= 0.45
            last = it.get("lastUsedAt")
            if last:
                try:
                    t = _dt.datetime.fromisoformat(str(last).replace("Z", "+00:00"))
                    if (now - t).total_seconds() < 1200:
                        x *= 0.15                                 # 刚用过，别连着来第二回
                except Exception:
                    pass
            return max(x, 0.05)

        got, left = [], list(pool)
        for _ in range(max(1, min(int(count or 1), len(left)))):
            c = random.choices(left, weights=[w(i) for i in left], k=1)[0]
            got.append(c)
            left.remove(c)
        stamp = now.isoformat()
        for g in got:
            g["useCount"] = int(g.get("useCount") or 0) + 1
            g["lastUsedAt"] = stamp
        _write(st)
    return {"分类": cat, "颜文字": [g["value"] for g in got]}


@router.get("/api/kaomoji/v2")
def v2_get():
    return JSONResponse(_read())


@router.post("/api/kaomoji/v2")
async def v2_update(req: Request):
    b = await req.json()
    op, value = (b.get("op") or "").strip(), b.get("value") or ""
    with _LOCK:
        st = _read()
        if op == "upsert":
            if not value.strip():
                return JSONResponse({"err": "空的存不了"}, status_code=400)
            cats = [c for c in (b.get("categories") or []) if c and c.strip()]
            it = _find(st, value)
            if it:
                for c in cats:
                    if c not in it["categories"]:
                        it["categories"].append(c)
                if b.get("label"):
                    it["label"] = b["label"]
            else:
                it = {"value": value, "categories": cats or ["未分类"], "favorite": False,
                      "useCount": 0, "compatibility": b.get("compatibility") or "stable",
                      "compatibilityNotes": b.get("compatibilityNotes") or []}
                for k in ("safeValue", "label"):
                    if b.get(k):
                        it[k] = b[k]
                st["items"].append(it)
            st["removed"] = [r for r in st["removed"] if r != value]
            _write(st)
            return JSONResponse({"ok": True, "item": it})
        if op == "remove":
            st["items"] = [i for i in st["items"] if i.get("value") != value]
            if value and value not in st["removed"]:
                st["removed"].append(value)
            _write(st)
            return JSONResponse({"ok": True})
        if op == "markUsed":
            it = _find(st, value)
            if not it:
                return JSONResponse({"ok": False, "err": "库里没有"}, status_code=404)
            it["useCount"] = int(it.get("useCount") or 0) + 1
            it["lastUsedAt"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            _write(st)
            return JSONResponse({"ok": True, "useCount": it["useCount"]})
        if op == "setFavorite":
            it = _find(st, value)
            if not it:
                return JSONResponse({"ok": False, "err": "库里没有"}, status_code=404)
            it["favorite"] = bool(b.get("favorite"))
            _write(st)
            return JSONResponse({"ok": True, "favorite": it["favorite"]})
        if op == "setCategoryOrder":
            st["categoryOrder"] = [c for c in (b.get("categories") or []) if c and c.strip()]
            _write(st)
            return JSONResponse({"ok": True})
        return JSONResponse({"err": f"不认识的 op: {op[:40]}"}, status_code=400)
