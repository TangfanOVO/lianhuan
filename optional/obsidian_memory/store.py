"""记忆存成 markdown —— 「记忆的实现可换」的第一个真示范。

贴一个文件夹路径，记忆层就从 SQLite 切到 **markdown 文件**：
一条记忆一个 md（YAML frontmatter 记层级/时间，标签走行内 #tag），
AI 的召回照常走（同一套中文 2-gram）。

★ **不绑任何一家**：写的是标准 md ＋ frontmatter，所以吃本地 md 文件夹的软件都认 ——
  Obsidian（vault）· Logseq · Foam · Zettlr · Joplin 的 md 模式 · 甚至就用 VS Code。
  环境变量名沿用 OBSIDIAN_VAULT 只是为了不破坏已经贴过路径的人。
★ 跟这些软件不是竞争是互补：它们管看和编，这边管「每次说话前灌给模型」。
★ 只写进 vault 下自己的子文件夹「连环记忆/」，不碰 vault 里别的任何东西。
★ 启用时把 SQLite 里已有的记忆搬过去（原库留着不删 —— 反悔就关掉这个包）。
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from core.store.base import Memory

_DIR: Path | None = None
_orig: dict = {}


def _slug(text: str) -> str:
    s = re.sub(r"[^\w一-鿿]+", "-", text[:24]).strip("-")
    return s or "memo"


def _write_md(d: Path, m: Memory) -> Path:
    mid = m.id or int(time.time() * 1000) % 10**9
    f = d / f"{mid}-{_slug(m.content)}.md"
    tags = " ".join("#" + t for t in (m.tags or []))
    f.write_text(f"""---
layer: {m.layer}
ts: {m.ts or time.time():.0f}
id: {mid}
---
{m.content}
{tags}
""", encoding="utf-8")
    return f


def _read_all(d: Path) -> list[Memory]:
    out = []
    for f in sorted(d.glob("*.md")):
        try:
            t = f.read_text(encoding="utf-8")
        except Exception:
            continue
        layer, ts, mid = "L1", 0.0, None
        body = t
        if t.startswith("---"):
            head, _, body = t[3:].partition("---")
            for line in head.splitlines():
                k, _, v = line.partition(":")
                k, v = k.strip(), v.strip()
                if k == "layer":
                    layer = v or "L1"
                elif k == "ts":
                    try:
                        ts = float(v)
                    except Exception:
                        pass
                elif k == "id":
                    try:
                        mid = int(v)
                    except Exception:
                        pass
        body = body.strip()
        tags = re.findall(r"(?:^|\s)#([\w一-鿿-]+)", body)
        body = re.sub(r"(?:^|\s)#[\w一-鿿-]+\s*$", "", body).strip()
        if body:
            out.append(Memory(id=mid, content=body, layer=layer, tags=tags, ts=ts))
    return out


def enable(store, vault: str) -> dict:
    """把 store 的记忆四法换成 md 实现。turns（聊天）照旧在 SQLite。"""
    global _DIR
    v = Path(vault).expanduser()
    if not v.is_dir():
        return {"ok": False, "err": f"路径不存在或不是文件夹：{v}"}
    d = v / "连环记忆"
    d.mkdir(exist_ok=True)
    _DIR = d

    migrated = 0
    have = {m.id for m in _read_all(d)}
    for m in store.all_memories():
        if m.id not in have:
            _write_md(d, m)
            migrated += 1

    if not _orig:
        _orig.update(add=store.add_memory, search=store.search_memories,
                     all=store.all_memories, delete=store.delete_memory)

    terms = store._terms          # 复用同一套中文 2-gram

    def add_memory(m: Memory) -> int:
        m.ts = m.ts or time.time()
        m.id = int(time.time() * 1000) % 10**9
        _write_md(_DIR, m)
        return m.id

    def all_memories() -> list[Memory]:
        return _read_all(_DIR)

    def search_memories(query: str, limit: int = 12) -> list[Memory]:
        ts_ = terms(query)
        if not ts_:
            return []
        scored = []
        for m in _read_all(_DIR):
            n = sum(1 for t in ts_ if t in m.content)
            if n:
                scored.append((n, m))
        scored.sort(key=lambda x: (-x[0], -(x[1].ts or 0)))
        return [m for _, m in scored[:limit]]

    def delete_memory(mid: int) -> None:
        for f in _DIR.glob(f"{mid}-*.md"):
            f.unlink()

    store.add_memory = add_memory
    store.all_memories = all_memories
    store.search_memories = search_memories
    store.delete_memory = delete_memory
    return {"ok": True, "migrated": migrated, "dir": str(d)}


def disable(store) -> None:
    if _orig:
        store.add_memory = _orig["add"]
        store.search_memories = _orig["search"]
        store.all_memories = _orig["all"]
        store.delete_memory = _orig["delete"]
