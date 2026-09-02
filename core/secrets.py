"""界面里贴的那些 key —— 一个 0600 的本地文件。

规矩（跟引擎那份同款）：环境变量优先（会用终端的人自己说了算）；
不进数据库、不进 /api/export、界面永不回显（只报有没有）。
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def _file() -> Path:
    return Path(os.environ.get("LIANHUAN_DB", "data/lianhuan.db")).parent / "secrets.json"


def get(key: str) -> str:
    v = os.environ.get(key, "")
    if v:
        return v
    try:
        return str(json.loads(_file().read_text(encoding="utf-8")).get(key) or "")
    except Exception:
        return ""


def set_many(kv: dict) -> None:
    f = _file()
    try:
        cur = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        cur = {}
    for k, v in kv.items():
        v = str(v or "").strip()
        if v:
            cur[k] = v
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        os.chmod(f, 0o600)
    except Exception:
        pass
