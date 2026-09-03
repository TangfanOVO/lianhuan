"""蒸馏 —— 让记忆库自己长起来，并且不越长越脏。

## 为什么不是「聊完自动写进去」就完事

只写不管，库会用一个月就变成一堆重复、过期、越读越糊涂的东西 ——
召回是在主链路上的，脏记忆不是「多几条没用的」，是**每一轮都在污染上下文**。

所以这条流水线有四段，缺一段都会塌：

  ① 提取   拿最近的对话让模型提候选 —— **先落「潜在」，不直接进库**
  ② 审批   人点头才入库（也可以开自动，但默认关着）
  ③ 去重   新候选跟老记忆撞了要说出来；**只按字面算，不用向量**
  ④ 升层   被反复用到的往上升 L1 → L2 → L3；没人用的就沉在 L1

## ③ 为什么死活不用向量

原项目栽过一次，教训值钱：用向量做「兜底去重」，一条「熬通宵」把十二条
毫不相干的事实合并掉了（幸好那次是 dry-run）。语义近 ≠ 说的是同一件事，
而合并是**不可逆**的。字面重合笨，但它错得看得懂：两条 2-gram 重合七成五，
人一眼就能判断是不是一回事。

★ 而且这里**从不自动合并**：只把「疑似跟第几条重了」标在候选上，人自己定。

## ④ 升层不需要审批

升层不改内容，只改「召回时读多少」。内容没变的事不该打断人 —— 这跟入库不一样。
"""
from __future__ import annotations

import json
import re
import time

import contextlib

_store = None
_activity = None


@contextlib.contextmanager
def _nullctx(_what: str = ""):
    yield
_say = None          # async (prompt) -> str，由 server 注入

SCHEMA = """
-- 潜在记忆：提出来了，等人点头
CREATE TABLE IF NOT EXISTS latent (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  content TEXT NOT NULL,
  layer TEXT DEFAULT 'L1',
  why TEXT DEFAULT '',
  src_lo INTEGER, src_hi INTEGER,
  dup_of INTEGER, dup_score REAL DEFAULT 0,
  status TEXT DEFAULT 'new',          -- new | kept | dropped
  mem_id INTEGER,                     -- 入库之后是哪一条
  ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS latent_status ON latent(status, id DESC);

-- 召回计数：升层的依据
CREATE TABLE IF NOT EXISTS memory_hits (
  mid INTEGER PRIMARY KEY, hits INTEGER DEFAULT 0, last REAL
);
"""

#: 出厂阈值。★ 都能在设置里改 —— 每个人的用法差太远，写死一定有人不合适。
DEFAULTS = {
    "every_turns": 20,      # 攒够几轮跑一次（0 = 不自动跑）
    "max_per_run": 3,       # 一次最多提几条 —— 提太多人就懒得审了
    "auto_keep": False,     # 直接入库不用审？默认关
    "dup_at": 0.75,         # 2-gram 重合到几成算「疑似重复」
    "to_l2": 5,             # L1 被召回几次升 L2
    "to_l3": 15,            # L2 被召回几次升 L3
}


def bind(store, say, activity=None) -> None:
    """挂上。`say` 是 async (prompt) -> str；`activity` 是活动登记（让 import 看得见我）。"""
    global _store, _say, _activity
    _store, _say, _activity = store, say, activity
    store.db.executescript(SCHEMA)
    store.db.commit()
    # 召回的时候记一笔 —— 给 recall 用的钩子，没装这个模块时它压根不存在
    store.note_recall = note_recall


def cfg() -> dict:
    c = dict(DEFAULTS)
    c.update(_store.get_setting("distill", {}) or {})
    return c


def set_cfg(patch: dict) -> dict:
    c = {**(_store.get_setting("distill", {}) or {})}
    for k, v in (patch or {}).items():
        if k in DEFAULTS:
            c[k] = v
    _store.set_setting("distill", c)
    return cfg()


# ── ④ 召回计数与升层 ──────────────────────────────────────
def note_recall(ids) -> None:
    """这一轮召回用到了这几条。★ 只记数，别的什么都不做。"""
    if not ids:
        return
    now = time.time()
    for i in ids:
        if i is None:
            continue
        _store.db.execute(
            "INSERT INTO memory_hits(mid,hits,last) VALUES(?,1,?) "
            "ON CONFLICT(mid) DO UPDATE SET hits=hits+1, last=excluded.last", (i, now))
    _store.db.commit()


def promote() -> list[dict]:
    """够数的往上升一层。不改内容，所以不用问人。"""
    c = cfg()
    out = []
    rows = _store.db.execute(
        "SELECT m.id, m.layer, m.content, h.hits FROM memories m "
        "JOIN memory_hits h ON h.mid=m.id").fetchall()
    for r in rows:
        want = None
        if r["layer"] == "L1" and r["hits"] >= c["to_l2"]:
            want = "L2"
        elif r["layer"] == "L2" and r["hits"] >= c["to_l3"]:
            want = "L3"
        if want:
            _store.db.execute("UPDATE memories SET layer=? WHERE id=?", (want, r["id"]))
            out.append({"id": r["id"], "from": r["layer"], "to": want,
                        "hits": r["hits"], "content": r["content"][:60]})
    if out:
        _store.db.commit()
    return out


# ── ③ 去重（只按字面） ────────────────────────────────────
def _grams(s: str) -> set:
    s = s or ""
    words = set(re.findall(r"[A-Za-z0-9_]{2,}", s.lower()))
    han = re.sub(r"[^一-鿿]+", "", s)
    return words | {han[i:i + 2] for i in range(len(han) - 1)}


def similar(content: str):
    """跟库里最像的那条，返回 (id, 重合率)。没有就 (None, 0)。

    重合率 = 交集 / **较短那边**的片段数 —— 用较短的当分母，
    这样「他的猫叫豆子」和「他的猫叫豆子，橘色，六岁」也能认出来是一回事。
    """
    g = _grams(content)
    if not g:
        return None, 0.0
    best, score = None, 0.0
    for r in _store.db.execute("SELECT id, content FROM memories").fetchall():
        h = _grams(r["content"])
        if not h:
            continue
        inter = len(g & h)
        s = inter / max(1, min(len(g), len(h)))
        if s > score:
            best, score = r["id"], s
    return best, round(score, 3)


# ── ① 提取 ───────────────────────────────────────────────
PROMPT = """下面是一段对话。请从里面挑出**值得长期记住的事实**。

只挑这几类：
· 对方的习惯、喜好、忌口、身体状况
· 对方在意的人和事（名字、关系、日子）
· 明确说好的约定
· 对方纠正过你的地方

不要挑：
· 寒暄、情绪本身、你自己说的话
· 只在这一刻成立的事（「现在有点困」）
· 你推测的、对方没说过的

最多 {n} 条，宁可少也别凑数。一条一句话，写清楚是谁、什么事。
**只输出 JSON**，别的一个字都不要：

{{"items":[{{"content":"…","layer":"L1","why":"为什么值得记，半句话"}}]}}

layer 只用 L1 或 L2：L2 是长期不会变的事实（忌口、家人、习惯），别的都写 L1。
一条都没有就输出 {{"items":[]}}。

对话：
{dialog}"""


def _pick_json(text: str) -> dict:
    """模型爱在 JSON 外面裹一层话。把最外层那个 {...} 抠出来。"""
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?|```$", "", t, flags=re.M).strip()
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j <= i:
        return {}
    try:
        return json.loads(t[i:j + 1])
    except Exception:
        return {}


#: 这会儿有没有一趟正在跑。★ 0831 自查抓的：`behind` 是拿游标算的，
#: 而游标要等模型回来才推进 —— 第一趟还在等模型的那几十秒里，
#: 后面每一条聊天都会再起一趟，读到同一个旧游标、切到同一段 turns：
#: 同一件事在待审列表里重复 N 条、模型的钱花 N 份、auto_keep 开着时记忆库也重复 N 条。
_running = False


async def run(limit_turns: int = 40, force: bool = False) -> dict:
    """跑一趟：提候选 → 查重 → 落进 latent。**不入库。**"""
    global _running
    if _running:
        return {"ok": True, "picked": 0, "note": "已经有一趟在跑了，这次不重复起"}
    _running = True
    try:
        return await _run_once(limit_turns, force)
    finally:
        _running = False


async def _run_once(limit_turns: int, force: bool) -> dict:
    c = cfg()
    cur = int(_store.get_setting("distill_cursor", 0) or 0)
    rows = _store.db.execute(
        "SELECT id, role, content FROM turns WHERE id > ? ORDER BY id LIMIT ?",
        (cur, limit_turns)).fetchall()
    if len(rows) < 2 and not force:
        return {"ok": True, "picked": 0, "note": "没有新的话可提"}

    dialog = "\n".join(
        ("对方：" if r["role"] == "user" else "你：") + (r["content"] or "").replace("\n", " ")[:300]
        for r in rows)
    gen_at_start = getattr(_store, "generation", 0)   # ★ 这些候选是从哪一份档案里提的
    act = _activity or _nullctx
    with act("distill"):                              # ★ 让 import 的 409 看得见我
        raw = await _say(PROMPT.format(n=c["max_per_run"], dialog=dialog))
    items = (_pick_json(raw) or {}).get("items") or []
    if getattr(_store, "generation", 0) != gen_at_start:
        # ★ 0831（GPT 四轮 P0-03c）：提取期间档案被换掉了。这些候选是从**旧档案**里提的，
        #   而 src_lo/src_hi 那两个整数 ID 在新档案里会被复用 —— 来源会安静地指到
        #   毫不相干的新原文。整趟丢掉，游标也不推。
        print("[distill] 提取期间档案换了，这趟候选全丢（来源会指错）", flush=True)
        return {"ok": True, "picked": 0, "note": "提到一半档案被换了，这趟不算"}

    made = []
    for it in items[:c["max_per_run"]]:
        content = str(it.get("content") or "").strip()[:500]
        if not content:
            continue
        dup, score = similar(content)
        layer = it.get("layer") if it.get("layer") in ("L1", "L2") else "L1"
        cid = _store.db.execute(
            "INSERT INTO latent(content,layer,why,src_lo,src_hi,dup_of,dup_score,status,ts)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (content, layer, str(it.get("why") or "")[:200],
             rows[0]["id"], rows[-1]["id"],
             dup if score >= c["dup_at"] else None,
             score, "new", time.time())).lastrowid
        made.append(cid)
    _store.set_setting("distill_cursor", rows[-1]["id"])
    _store.db.commit()

    kept = []
    if c["auto_keep"]:
        for cid in made:
            r = keep(cid)
            if r.get("ok"):
                kept.append(r["mem_id"])

    return {"ok": True, "picked": len(made), "auto_kept": kept,
            "cursor": rows[-1]["id"], "read_turns": len(rows)}


# ── ② 审批 ───────────────────────────────────────────────
def pending(view: str = "new", limit: int = 50) -> dict:
    where = {"new": "status='new'", "kept": "status='kept'",
             "dropped": "status='dropped'"}.get(view, "1=1")
    rows = _store.db.execute(
        "SELECT * FROM latent WHERE " + where + " ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if r["dup_of"]:
            m = _store.db.execute("SELECT content FROM memories WHERE id=?", (r["dup_of"],)).fetchone()
            d["dup_content"] = m["content"] if m else None
        out.append(d)
    counts = {k: _store.db.execute(
        "SELECT count(*) n FROM latent WHERE status=?", (k,)).fetchone()["n"]
        for k in ("new", "kept", "dropped")}
    return {"items": out, "counts": counts}


def import_candidates(items: list[dict]) -> dict:
    """把用户亲自选的本机文件放进待审区；不自动写进记忆库。"""
    made = []
    skipped = 0
    existing = {row["content"] for row in _store.db.execute("SELECT content FROM latent").fetchall()}
    existing.update(memory.content for memory in _store.all_memories())
    for item in items[:50]:
        content = str(item.get("content") or "").strip()
        if not content or len(content) > 20_000:
            skipped += 1
            continue
        if content in existing:
            skipped += 1
            continue
        existing.add(content)
        dup, score = similar(content)
        layer = item.get("layer") if item.get("layer") in ("L1", "L2") else "L1"
        cid = _store.db.execute(
            "INSERT INTO latent(content,layer,why,src_lo,src_hi,dup_of,dup_score,status,ts)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (content, layer, str(item.get("why") or "从本机文件导入")[:200], None, None,
             dup if score >= cfg()["dup_at"] else None, score, "new", time.time()),
        ).lastrowid
        made.append(cid)
    _store.db.commit()
    return {"ok": True, "imported": len(made), "skipped": skipped, "ids": made}


def keep(lid: int) -> dict:
    """点头：落进记忆库。★ 就算标了疑似重复也照落 —— 合不合并是人的事，不是这儿替他决定。"""
    from .store.base import Memory
    r = _store.db.execute("SELECT * FROM latent WHERE id=?", (lid,)).fetchone()
    if not r or r["status"] != "new":
        return {"ok": False, "err": "没有这条，或者已经处理过了"}
    mid = _store.add_memory(Memory(content=r["content"], layer=r["layer"]))
    _store.db.execute("UPDATE latent SET status='kept', mem_id=? WHERE id=?", (mid, lid))
    _store.db.commit()
    return {"ok": True, "mem_id": mid}


def unkeep(lid: int) -> dict:
    """点错了，撤回来：把入库的那条删掉，候选退回「还没审」。

    ★ 敢做这个撤销，是因为 keep 只是「照抄一条进库」——没有合并、没有改写，
      所以撤回是干净的。（合并那种不可逆的事这条流水线里一件都没有。）
    """
    r = _store.db.execute("SELECT * FROM latent WHERE id=?", (lid,)).fetchone()
    if not r or r["status"] != "kept":
        return {"ok": False, "err": "这条不是「收下」的状态"}
    if r["mem_id"]:
        _store.delete_memory(r["mem_id"])
        _store.db.execute("DELETE FROM memory_hits WHERE mid=?", (r["mem_id"],))
    _store.db.execute("UPDATE latent SET status='new', mem_id=NULL WHERE id=?", (lid,))
    _store.db.commit()
    return {"ok": True}


def drop(lid: int) -> dict:
    n = _store.db.execute(
        "UPDATE latent SET status='dropped' WHERE id=? AND status='new'", (lid,)).rowcount
    _store.db.commit()
    return {"ok": bool(n)}


def status() -> dict:
    c = cfg()
    cur = int(_store.get_setting("distill_cursor", 0) or 0)
    total = _store.db.execute("SELECT count(*) n FROM turns").fetchone()["n"]
    behind = _store.db.execute("SELECT count(*) n FROM turns WHERE id > ?", (cur,)).fetchone()["n"]
    counts = {k: _store.db.execute(
        "SELECT count(*) n FROM latent WHERE status=?", (k,)).fetchone()["n"]
        for k in ("new", "kept", "dropped")}
    layers = {r["layer"]: r["n"] for r in _store.db.execute(
        "SELECT layer, count(*) n FROM memories GROUP BY layer").fetchall()}
    return {"config": c, "cursor": cur, "turns": total, "behind": behind,
            "latent": counts, "layers": layers}
