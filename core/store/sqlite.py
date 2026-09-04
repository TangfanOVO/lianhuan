"""SQLite 实现 —— 默认就是它。

一个文件，零配置，标准库自带。想搬家就把那个 `.db` 文件拷走。

★ 为什么不默认上 PostgreSQL：一键装起来的人不该先去装个数据库。
  等你真需要多设备同步了，再换 `postgres.py`，接口一样，换一行配置的事。
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from .base import Memory, Store, Turn

SCHEMA = """
CREATE TABLE IF NOT EXISTS turns (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  role TEXT NOT NULL, content TEXT NOT NULL, think TEXT DEFAULT '',
  tools TEXT DEFAULT '',
  -- ★ 0831 自查：这一列原来**不在这儿** —— 是 `core/views.py` 的 bind() 用 ALTER
  --   顺手建出来的副作用。于是谁不经过 server 直接建 store（测试、脚本、第二个实例），
  --   /chat 那句 `UPDATE turns SET hidden=1` 就炸。列该由 schema 自己负责。
  hidden INTEGER DEFAULT 0,
  -- 这句是不是人真说出口的。0 = 机器拼给模型看的指令，永远不算「原话」。
  spoken INTEGER DEFAULT 1,
  channel TEXT DEFAULT 'text',        -- text | call
  call_id TEXT,                       -- 每通电话一个
  session_id TEXT, ts REAL NOT NULL
);
-- ★ turns_ctx 那条索引**不能写在这儿**：老库走的是 `CREATE TABLE IF NOT EXISTS`，
--   表已存在就整段跳过、三个新列一个都不会加，而索引照跑 → `no such column: channel`，
--   **老库当场打不开**。所以它挪到下面 ALTER 迁移跑完之后再建。（0831 我自己栽的。）
CREATE INDEX IF NOT EXISTS turns_ts ON turns(ts DESC);

CREATE TABLE IF NOT EXISTS memories (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  content TEXT NOT NULL, layer TEXT DEFAULT 'L1', tags TEXT DEFAULT '[]', ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS memories_ts ON memories(ts DESC);

CREATE TABLE IF NOT EXISTS settings (k TEXT PRIMARY KEY, v TEXT NOT NULL);

-- 每轮烧了多少 token。★ 0904 新建的表，老表一个字没动。
-- 她要的：「链接里这个『用量』，本意是 token，用了多少 token 的计数有做吗」——没做，这是补的。
-- ★ 只记数，不记内容：这张表拿去看账，不该在里面读到说过什么。
CREATE TABLE IF NOT EXISTS token_usage (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL NOT NULL,
  engine TEXT NOT NULL DEFAULT '',
  model TEXT NOT NULL DEFAULT '',
  tin INTEGER NOT NULL DEFAULT 0,      -- 进去的
  tout INTEGER NOT NULL DEFAULT 0,     -- 出来的
  tcache_r INTEGER NOT NULL DEFAULT 0, -- 缓存读到的（便宜那部分）
  tcache_w INTEGER NOT NULL DEFAULT 0  -- 写进缓存的
);
CREATE INDEX IF NOT EXISTS token_usage_ts ON token_usage(ts DESC);
"""

#: 全文检索的影子表。★ 从 SCHEMA 里拆出来单独建，因为**不是每个 SQLite 都带 FTS5**：
#  安卓完整体用的 Chaquopy 自带的那个就没编，`CREATE VIRTUAL TABLE … USING fts5`
#  会抛 `no such module: fts5`，整个后端当场起不来（0903 真机上抓到的，完整体从第一版起就没起来过）。
#  ★ 现在没有任何地方**读**这张表 —— `search_memories` 走的是 2-gram ＋ LIKE
#    （测试就叫 test_chinese_search_without_fts）。所以建不出来就不建，功能一点不少。
#  ★ 表和这两个触发器必须同生共死：只建触发器的话，往 memories 写一条就报错。
FTS_SCHEMA = """
-- 全文检索。★ SQLite 的 FTS5 默认按空格分词，对中文基本等于没分 ——
-- 所以下面的 search 是 FTS 和 LIKE 两条腿走路，别只信 FTS 的结果。
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(content, content=memories, content_rowid=id);
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
  INSERT INTO memories_fts(rowid, content) VALUES (new.id, new.content);
END;
CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
  INSERT INTO memories_fts(memories_fts, rowid, content) VALUES('delete', old.id, old.content);
END;
"""


def _fts5_works(conn) -> bool:
    """这个 SQLite 编了 FTS5 没有。★ 先拿一张临时表探一下，不要靠「跑 FTS_SCHEMA 失败再回滚」——
    `executescript` 会先隐式提交，中途失败就留下一个建了一半的库。"""
    try:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_probe USING fts5(x)")
        conn.execute("DROP TABLE IF EXISTS _fts5_probe")
        return True
    except sqlite3.OperationalError:
        return False

# 跟着「搬家」走的用户账本。设备订阅、密钥、缓存和本机文件故意不在这里：
# `push_subs` 绑具体浏览器，`secrets.json` 根本不在数据库，上传文件另行搬。
# 名单写死而不是遍历 sqlite_master，避免将来某个临时表悄悄混进导出。
PORTABLE_TABLES = (
    "notes", "diary", "letters", "moments", "moment_comments", "timeline_events",
    "mood_state", "mood_log", "memes", "workbook", "trips", "calendar",
    "anniversaries", "brain_history", "books", "book_chapters", "book_annotations",
    "book_chat", "latent", "memory_hits", "reminders", "speak_log",
)

# 设置也属于这份家，但仍用白名单：密钥、设备订阅和本机路径将来即使进了 settings 也不会外带。
PORTABLE_SETTINGS = (
    "engine", "store", "pet", "blocks", "config", "prefs", "theme", "where",
    "ai_now", "now_playing", "miss", "whisper_freq", "fish_freq", "emote_level",
    "distill", "think", "persona_extra",
)


class SqliteStore(Store):
    def __init__(self, path: str | Path = "data/lianhuan.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        #: ★ 0831（GPT 四轮 P0-02，数据破坏级）：原来全进程共用**一把连接**，
        #: 而写锁只包住 import ——「别人的 commit() 会把我这个没写完的事务一起提交掉」。
        #: 实测：replace 导入中途来一次普通 add_turn()，旧库被清、留下 179 条半截。
        #: 光加锁堵不住（optional 包直接 `_store.db.execute(...)` 写，绕过所有入口）。
        #: → **每个线程一把自己的连接**：事务各在各的连接上，谁也提交不了谁。
        #:   `db` 是个 property，所以 `_store.db.execute(...)` 那些老写法自动就对了。
        self._local = threading.local()
        boot = self._connect()
        boot.executescript(SCHEMA)
        boot.commit()
        #: 这台机器的 SQLite 有没有 FTS5。没有就不建那张影子表 —— 谁都不读它，功能不受影响。
        self.fts = _fts5_works(boot)
        if self.fts:
            boot.executescript(FTS_SCHEMA)
            boot.commit()
        # 老库迁移：这两列都是后加的（见 base.Turn）。CREATE TABLE 只管新库，老库靠这儿补。
        # ★ 老库迁移只补列、**不回填** —— 老行一律 spoken=1 / channel='text'。
        #   宁可让几条旧的机器指令继续被读到，也不能靠猜把用户真说过的话判成「没说过」。
        for col, ddl in (("tools",   "ALTER TABLE turns ADD COLUMN tools TEXT DEFAULT ''"),
                         ("hidden",  "ALTER TABLE turns ADD COLUMN hidden INTEGER DEFAULT 0"),
                         ("spoken",  "ALTER TABLE turns ADD COLUMN spoken INTEGER DEFAULT 1"),
                         ("channel", "ALTER TABLE turns ADD COLUMN channel TEXT DEFAULT 'text'"),
                         ("call_id", "ALTER TABLE turns ADD COLUMN call_id TEXT")):
            try:
                cols = [r[1] for r in boot.execute("PRAGMA table_info(turns)")]
                if col not in cols:
                    boot.execute(ddl)
                    boot.commit()
            except Exception as e:
                print(f"[store] turns.{col} 迁移失败:", e, flush=True)
        # ★ 必须在上面几条 ALTER 之后 —— 它引用的就是那几列
        try:
            boot.execute("CREATE INDEX IF NOT EXISTS turns_ctx "
                         "ON turns(channel, call_id, spoken, ts DESC)")
            boot.commit()
        except Exception as e:
            print("[store] turns_ctx 索引没建上（不致命）:", e, flush=True)
        #: WAL：读不挡写、写不挡读，多连接下才不会动不动 "database is locked"。
        #: （它是**数据库属性**，设一次就永久，不用每条连接都设。）
        try:
            boot.execute("PRAGMA journal_mode=WAL")
            boot.commit()
        except Exception as e:
            print("[store] WAL 开不了（不致命，继续）:", e, flush=True)
        #: 仍然留一把写锁：不为正确性（那靠连接隔离），是为了少撞 busy、让并发导入排队
        self._wlock = threading.Lock()
        #: 档案世代。每换一次档案（replace 导入）+1 —— 所有异步写回落库前都要核它，
        #: 世代变了就不落（不然旧问答会接到新档案上，配错原文，两边还都 HTTP 成功）。
        self.generation = 0

    def _connect(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path, check_same_thread=False)
        c.row_factory = sqlite3.Row
        #: 撞上别人在写就等一会儿，别当场抛 "database is locked"
        c.execute("PRAGMA busy_timeout=8000")
        c.execute("PRAGMA foreign_keys=ON")
        self._local.conn = c
        return c

    @property
    def db(self) -> sqlite3.Connection:
        """这个线程自己的那把连接。★ 别把它存成变量跨线程用。"""
        c = getattr(self._local, "conn", None)
        return c if c is not None else self._connect()
        #: 档案世代。每换一次档案（replace 导入）+1 —— 在途的聊天任务落库前会核它，
        #: 世代变了就不落（不然旧问答会接到新档案上，配错原文，而且两边 HTTP 都成功）。
        self.generation = 0

    # ── 对话 ──
    def add_turn(self, turn: Turn) -> int:
        cur = self.db.execute(
            "INSERT INTO turns(role, content, think, tools, hidden, spoken, channel, call_id, "
            "session_id, ts) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (turn.role, turn.content, turn.think, turn.tools or "", int(turn.hidden or 0),
             int(turn.spoken if turn.spoken is not None else 1), turn.channel or "text",
             turn.call_id, turn.session_id, turn.ts or time.time()))
        self.db.commit()
        return int(cur.lastrowid)

    def _turn(self, r: sqlite3.Row) -> Turn:
        keys = r.keys()
        return Turn(id=r["id"], role=r["role"], content=r["content"],
                    think=r["think"] or "",
                    tools=(r["tools"] or "") if "tools" in keys else "",
                    hidden=int(r["hidden"] or 0) if "hidden" in keys else 0,
                    spoken=int(r["spoken"] if r["spoken"] is not None else 1) if "spoken" in keys else 1,
                    channel=(r["channel"] or "text") if "channel" in keys else "text",
                    call_id=(r["call_id"] if "call_id" in keys else None),
                    session_id=r["session_id"], ts=r["ts"])

    def recent_turns(self, limit: int = 24) -> list[Turn]:
        rows = self.db.execute("SELECT * FROM turns ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [self._turn(r) for r in reversed(rows)]     # 还原成时间正序，模型才读得顺

    def context_turns(self, *, channel: str = "text", call_id: str | None = None,
                      limit: int = 24, exclude_id: int | None = None,
                      since: float | None = None) -> list[Turn]:
        """给模型看的那几句 —— **只有人真说出口的**，而且分频道。

        ★ 0831 自查（GPT 上下文专项 P0-01/02/03，真捕获 EngineTurn 复现过）：
          原来所有入口都调 `recent_turns(N)`，那是一条光秃秃的
          `ORDER BY id DESC LIMIT ?` —— 没有频道、没有 spoken、什么都没有。
          实测后果：**打电话时读得到三天前的文字聊天，和机器拼给模型的场景指令**，
          而且它们还被当成「用户说过的话」。这是在替用户编话。

        · `spoken=0` 的一律不要 —— 那是机器拼的指令，不是原话
        · 文字只读文字；电话只读**本通**电话（`call_id` 对得上的那些）
        · 老行没有 call_id（迁移不回填），所以电话那条路老数据自然读不到 —— 正好
        """
        sql = ["SELECT * FROM turns WHERE spoken=1 AND channel=?"]
        args: list = [channel]
        if channel == "call":
            # ★ 没给 call_id = 一通全新的电话，什么都不该读到（而不是读全部）
            sql.append("AND call_id IS NOT NULL AND call_id=?")
            args.append(call_id or "")
        if exclude_id is not None:
            sql.append("AND id<>?")
            args.append(exclude_id)
        if since is not None:
            # ★ 主动消息那条路用它：按**时间**取，不按条数 ——
            #   「这两天说过什么」比「最近 N 条」更能回答「这事是不是已经聊完了」。
            sql.append("AND ts>=?")
            args.append(since)
        sql.append("ORDER BY id DESC LIMIT ?")
        args.append(limit)
        rows = self.db.execute(" ".join(sql), args).fetchall()
        return [self._turn(r) for r in reversed(rows)]

    def all_turns(self) -> list[Turn]:
        return [self._turn(r) for r in self.db.execute("SELECT * FROM turns ORDER BY id")]

    # ── 记忆 ──
    def add_memory(self, mem: Memory) -> int:
        cur = self.db.execute(
            "INSERT INTO memories(content, layer, tags, ts) VALUES(?,?,?,?)",
            (mem.content, mem.layer, json.dumps(mem.tags, ensure_ascii=False), mem.ts or time.time()))
        self.db.commit()
        return int(cur.lastrowid)

    def _mem(self, r: sqlite3.Row) -> Memory:
        return Memory(id=r["id"], content=r["content"], layer=r["layer"],
                      tags=json.loads(r["tags"] or "[]"), ts=r["ts"])

    @staticmethod
    def _terms(query: str) -> list[str]:
        """把一句话切成能拿去匹配的片段。

        ★★ 这是整条记忆链路上最容易坏、又最难发现的一处。
          人问的是**一整句**（「豆子最近怎么样」），而记忆里存的是
          「他的猫叫豆子…」。拿整句去 LIKE 永远匹配不到 —— 于是召回永远为空，
          而界面上一切正常：AI 只是「什么都不记得」，看起来像模型笨，
          不像检索坏了。真栽过，就是这个句子。

        办法：中文按 **2-gram** 切（豆子/子最/最近/…），英文数字按词切。
        再要求至少命中一段。粗糙，但不漏 —— 对个人规模的记忆库够用，
        而且**永远不会因为分词器不认识某个词就整句失灵**。
        """
        q = (query or "").strip()
        if not q:
            return []
        words = re.findall(r"[A-Za-z0-9_]{2,}", q)
        han = re.sub(r"[^\u4e00-\u9fff]+", "", q)
        grams = [han[i:i + 2] for i in range(len(han) - 1)] if len(han) >= 2 else ([han] if han else [])
        return list(dict.fromkeys(words + grams))[:24]     # 去重、留个上限

    def search_memories(self, query: str, limit: int = 12) -> list[Memory]:
        """按片段命中数排序。命中得越多的排越前。"""
        terms = self._terms(query)
        if not terms:
            return []
        score: dict[int, int] = {}
        got: dict[int, Memory] = {}
        for t in terms:
            for r in self.db.execute(
                    "SELECT * FROM memories WHERE content LIKE ? LIMIT 60", (f"%{t}%",)):
                score[r["id"]] = score.get(r["id"], 0) + 1
                got.setdefault(r["id"], self._mem(r))
        ranked = sorted(score.items(), key=lambda kv: (-kv[1], -got[kv[0]].ts))
        return [got[i] for i, _ in ranked[:limit]]

    def delete_memory(self, mid: int) -> None:
        """真删。★ 不做软删 —— 人说删就是删，偷偷留着才是背叛。
        （FTS 那张影子表靠触发器同步，这里不用管。）"""
        self.db.execute("DELETE FROM memories WHERE id=?", (mid,))
        self.db.commit()

    def all_memories(self) -> list[Memory]:
        return [self._mem(r) for r in self.db.execute("SELECT * FROM memories ORDER BY id")]

    # ── 用量（0904 新增）──
    def add_usage(self, engine: str = "", model: str = "",
                  tin: int = 0, tout: int = 0, tcache_r: int = 0, tcache_w: int = 0) -> None:
        """记一笔。★ 只记数，不记内容 —— 这张表拿去看账，不该在里面读到说过什么。"""
        import time as _t
        self.db.execute(
            "INSERT INTO token_usage (ts, engine, model, tin, tout, tcache_r, tcache_w) "
            "VALUES (?,?,?,?,?,?,?)",
            (_t.time(), engine or "", model or "", int(tin), int(tout), int(tcache_r), int(tcache_w)))
        self.db.commit()

    def usage_stats(self, days: int = 30) -> dict:
        """看账：总数、今天、按天、按模型。★ 没有的日子就是没有，不补 0 装作有。"""
        import time as _t
        since = _t.time() - days * 86400
        day0 = _t.mktime(_t.localtime()[:3] + (0, 0, 0, 0, 0, -1))
        def _row(sql, args=()):
            r = self.db.execute(sql, args).fetchone()
            return {k: int(r[k] or 0) for k in ("tin", "tout", "tcache_r", "tcache_w")} if r else {}
        cols = "SUM(tin) tin, SUM(tout) tout, SUM(tcache_r) tcache_r, SUM(tcache_w) tcache_w"
        return {
            "days": days,
            "total": _row(f"SELECT {cols} FROM token_usage"),
            "window": _row(f"SELECT {cols} FROM token_usage WHERE ts > ?", (since,)),
            "today": _row(f"SELECT {cols} FROM token_usage WHERE ts >= ?", (day0,)),
            "turns": int(self.db.execute("SELECT count(*) n FROM token_usage").fetchone()["n"] or 0),
            "by_model": [
                {"model": r["model"] or "?", "engine": r["engine"] or "",
                 "turns": int(r["n"] or 0), "tin": int(r["tin"] or 0), "tout": int(r["tout"] or 0),
                 "tcache_r": int(r["tcache_r"] or 0)}
                for r in self.db.execute(
                    f"SELECT model, engine, count(*) n, {cols} FROM token_usage "
                    "WHERE ts > ? GROUP BY model, engine ORDER BY (SUM(tin)+SUM(tout)) DESC LIMIT 20",
                    (since,))],
            "by_day": [
                {"day": r["d"], "tin": int(r["tin"] or 0), "tout": int(r["tout"] or 0)}
                for r in self.db.execute(
                    f"SELECT date(ts,'unixepoch','localtime') d, {cols} FROM token_usage "
                    "WHERE ts > ? GROUP BY d ORDER BY d DESC LIMIT 31", (since,))],
        }

    # ── 设置 ──
    def get_setting(self, key: str, default: Any = None) -> Any:
        r = self.db.execute("SELECT v FROM settings WHERE k=?", (key,)).fetchone()
        return json.loads(r["v"]) if r else default

    def set_setting(self, key: str, value: Any) -> None:
        self.db.execute("INSERT INTO settings(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                        (key, json.dumps(value, ensure_ascii=False)))
        self.db.commit()

    def export_all(self) -> dict:
        """导出能跨设备复原的全部账本；不带密钥、推送订阅和本机缓存。"""
        out = super().export_all()
        out["lianhuan"] = 3
        house = {}
        known = {r["name"] for r in self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        for table in PORTABLE_TABLES:
            if table in known:
                house[table] = [dict(r) for r in self.db.execute(f'SELECT * FROM "{table}"')]
        out["house"] = house
        rows = self.db.execute(
            f'SELECT k,v FROM settings WHERE k IN ({",".join("?" for _ in PORTABLE_SETTINGS)})',
            PORTABLE_SETTINGS).fetchall()
        out["settings"] = {r["k"]: json.loads(r["v"]) for r in rows}
        out["not_included"] = ["provider_keys", "push_subscriptions", "uploaded_files"]
        return out

    # ── 搬家 ──
    def import_all(self, data: dict, mode: str = "merge") -> dict:
        """导入。★ 0831（GPT 二轮 P0）重写成**先全量预校验、再单事务**：
        原来 replace 先 DELETE、逐条各自提交 —— 一条坏记录就把库留在
        「旧的清了、新的插了一半」的死地。现在坏记录=整批一个字不动。

        replace 的语义也说清：turns/memories/persona **整体换成导入的内容**
        （导入里没有 persona 就清成空 —— 替换就是替换，不是挑着换）。"""
        if mode not in ("merge", "replace"):
            raise ValueError("mode 只能是 merge 或 replace")

        # ── 预校验：任何一条不像话，整批拒收，库一个字不动 ──
        mems = data.get("memories") or []
        turns = data.get("turns") or []
        house = data.get("house") or {}
        settings = data.get("settings") or {}
        if not isinstance(house, dict):
            raise ValueError("house 要是一个对象")
        if not isinstance(settings, dict):
            raise ValueError("settings 要是一个对象")
        settings = {k: v for k, v in settings.items() if k in PORTABLE_SETTINGS}
        unknown = sorted(set(house) - set(PORTABLE_TABLES))
        if unknown:
            raise ValueError("house 里有不认识的表：" + "、".join(unknown[:5]))
        for table, rows in house.items():
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise ValueError(f"house.{table} 要是一组对象")
        for i, m in enumerate(mems):
            if not isinstance(m, dict) or not str(m.get("content") or "").strip():
                raise ValueError(f"memories[{i}] 不像一条记忆（要 dict、content 非空）")
        for i, t in enumerate(turns):
            if not isinstance(t, dict) or not str(t.get("content") or "").strip():
                raise ValueError(f"turns[{i}] 不像一条对话（要 dict、content 非空）")

        have_m = {(r["content"], r["ts"]) for r in self.db.execute("SELECT content, ts FROM memories")}
        have_t = {(r["content"], r["ts"]) for r in self.db.execute("SELECT content, ts FROM turns")}

        # ── 单事务：中途任何异常整体回滚。★ 用写锁串起来，并发导入不再互相撞 BEGIN ──
        n_m = n_t = skip = 0
        with self._wlock:
            return self._do_import(mode, mems, turns, house, settings, data, have_m, have_t)

    def _do_import(self, mode, mems, turns, house, settings, data, have_m, have_t) -> dict:
        n_m = n_t = skip = n_house = n_settings = 0
        self.db.execute("BEGIN")
        try:
            if mode == "replace":
                self.db.execute("DELETE FROM turns")
                self.db.execute("DELETE FROM memories")   # fts 由触发器跟着删
                for table in reversed(PORTABLE_TABLES):
                    if table in house:
                        self.db.execute(f'DELETE FROM "{table}"')
                self.db.execute(
                    f'DELETE FROM settings WHERE k IN ({",".join("?" for _ in PORTABLE_SETTINGS)})',
                    PORTABLE_SETTINGS)
                have_m = set()
                have_t = set()
            for m in mems:
                key = (m.get("content", ""), m.get("ts"))
                if mode == "merge" and key in have_m:
                    skip += 1
                    continue
                self.db.execute(
                    "INSERT INTO memories(content, layer, tags, ts) VALUES(?,?,?,?)",
                    (m.get("content", ""), m.get("layer", "L1"),
                     json.dumps(m.get("tags") or [], ensure_ascii=False),
                     m.get("ts") or time.time()))
                n_m += 1
            for t in turns:
                key = (t.get("content", ""), t.get("ts"))
                if mode == "merge" and key in have_t:
                    skip += 1
                    continue
                # ★ 0831 自查（GPT 上下文专项 P0-05 后半段，真跑复现过）：
                #   这条 INSERT 原来只有 5 列 —— `tools` 导得出去、导不回来。
                #   后果具体：0831 P0-04 刚做的「工具失败刷新后仍可审计」，
                #   被一次「导出→导入」整个抹平；`hidden` 同理归 0，
                #   那些机器拼的指令重新变成人的假气泡。
                #   ★ 用 .get() 带默认值 —— 老的导出文件没有这两个字段也照样能导。
                self.db.execute(
                    "INSERT INTO turns(role, content, think, tools, hidden, spoken, "
                    "channel, call_id, session_id, ts) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (t.get("role", "user"), t.get("content", ""), t.get("think", ""),
                     t.get("tools") or "", int(t.get("hidden") or 0),
                     int(t.get("spoken", 1) if t.get("spoken") is not None else 1),
                     t.get("channel") or "text", t.get("call_id"),
                     t.get("session_id"), t.get("ts") or time.time()))
                n_t += 1
            for table in PORTABLE_TABLES:
                rows = house.get(table)
                if not rows:
                    continue
                cols = [r["name"] for r in self.db.execute(f'PRAGMA table_info("{table}")')]
                if not cols:
                    raise ValueError(f"当前版本没有 house.{table}")
                for row in rows:
                    use = [c for c in cols if c in row]
                    if not use:
                        raise ValueError(f"house.{table} 有一条没有可导入字段")
                    marks = ",".join("?" for _ in use)
                    names = ",".join(f'"{c}"' for c in use)
                    verb = "INSERT OR IGNORE" if mode == "merge" else "INSERT"
                    cur = self.db.execute(
                        f'{verb} INTO "{table}" ({names}) VALUES ({marks})',
                        [row[c] for c in use])
                    if cur.rowcount:
                        n_house += 1
                    else:
                        skip += 1
            # ★ 这儿不能用 self.set_setting —— 它内部 commit，会把事务提前落定
            for key, value in settings.items():
                self.db.execute(
                    "INSERT INTO settings(k,v) VALUES(?,?) "
                    "ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                    (key, json.dumps(value, ensure_ascii=False)))
                n_settings += 1
            if mode == "replace" or data.get("persona"):
                self.db.execute(
                    "INSERT INTO settings(k,v) VALUES(?,?) "
                    "ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                    ("persona", json.dumps(data.get("persona") or {}, ensure_ascii=False)))
            self.db.commit()
            if mode == "replace":
                self.generation += 1      # 换档案了：在途任务的回复不该再落到新档案上
        except Exception:
            self.db.rollback()
            raise
        return {"memories": n_m, "turns": n_t, "house": n_house, "settings": n_settings,
                "skipped": skip, "mode": mode,
                "generation": self.generation}
