"""灌一份虚构的演示数据 —— 想先看看「满了是什么样」的时候用。

    python -m core.seed              往里加（不删现有的）
    python -m core.seed --replace    先清空再灌
    python -m core.seed --clear      只清空

★ `seed/demo.json` 里的人、话、事**全是编的**，不对应任何真人，
  也不是任何真实资料脱敏来的 —— 脱敏过的真实资料还是真实资料。

★ 正常安装**不会**灌这个。新装的人第一天就该看到空的界面：
  记忆是从零长起来的，那是起点，不是缺陷。
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .store.sqlite import SqliteStore

SEED = Path(__file__).resolve().parent.parent / "seed" / "demo.json"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--replace", action="store_true", help="先清空再灌")
    ap.add_argument("--clear", action="store_true", help="只清空，不灌")
    a = ap.parse_args()

    store = SqliteStore(os.environ.get("LIANHUAN_DB", "data/lianhuan.db"))

    if a.clear:
        store.import_all({"turns": [], "memories": []}, mode="replace")
        print("  清空了。")
        return

    if not SEED.is_file():
        print(f"  找不到 {SEED}")
        return

    data = json.loads(SEED.read_text(encoding="utf-8"))
    n = store.import_all(data, mode="replace" if a.replace else "merge")
    print(f"""
  灌好了：{n['memories']} 条记忆 · {n['turns']} 轮对话 · 一份人设（{data['persona']['ai']['name']} 和 {data['persona']['human']['name']}）

  ★ 全是编的。想看真正的空态就跑 `python -m core.seed --clear`。
""")


if __name__ == "__main__":
    main()
