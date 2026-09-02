#!/usr/bin/env python3
"""发布前的闸 —— 挡住「把候选目录原样发出去」。

为什么要有这个：`create.py` 生成的产物是干净的，但那只是**约定**里唯一正确的路径。
候选目录本身躺着测试库、密钥、私钥、上传的图、改前的备份和外部验收报告；
只要有人 `git init && git add -A && git push`，或者把目录打个包发出去，
上面每一样都会跟着走。约定挡不住手滑，检查才行。

用法：
    python3 tools/preflight.py            # 查这个目录能不能发（不能就退出码 1）
    python3 tools/preflight.py --staged   # 只查 git 暂存区里的（给 pre-commit 用）

装成 git 钩子（可选，但推荐）：
    ln -sf ../../tools/preflight.py .git/hooks/pre-commit
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: 一律不许进仓库/不许发的（按路径判）
FORBIDDEN_PATHS = [
    (re.compile(r"(^|/)data/"), "运行数据（测试库、上传的图、密钥、私钥都在里头）"),
    (re.compile(r"\.bak"), "改前的备份 —— 里面是没清洗过的旧版本"),
    (re.compile(r"(^|/)secrets\.json$"), "贴进去的 API key"),
    (re.compile(r"\.pem$|\.key$|\.keystore$|\.jks$"), "私钥"),
    # ★ .env.example 是**该发的**模板（README 教人复制它），别误杀
    (re.compile(r"(^|/)\.env$|(^|/)\.env\.(?!example)"), "环境变量文件"),
    (re.compile(r"(^|/)local\.properties$"), "本机 SDK 路径"),
    (re.compile(r"(^|/)REVIEW-.*\.md$"), "外部验收报告 —— 发布前删"),
    (re.compile(r"(^|/)AGENTS\.md$"), "给验收 agent 的交接 —— 发布前删"),
    (re.compile(r"(^|/)__pycache__/|\.pyc$"), "编译缓存"),
    (re.compile(r"(^|/)android/(app/)?build/|(^|/)\.gradle/"), "安卓构建产物（里面有 APK）"),
]

#: 每条路径规则的危险程度（数字小的先打）。★ 只影响**打印顺序**，不影响判定 ——
#: 判定还是走 FORBIDDEN_PATHS 的原顺序（那里有 break，动顺序会改判定）。
_SEV = {
    2: 1,   # secrets.json —— 贴进去的 key
    3: 1,   # .pem/.key/.keystore/.jks —— 私钥
    4: 1,   # .env
    0: 2,   # data/ —— 测试库、上传的图，-wal 里是真聊天
    5: 3,   # local.properties
    1: 4,   # .bak
    6: 5,   # REVIEW-*.md
    7: 5,   # AGENTS.md
    8: 6,   # __pycache__/.pyc
    9: 6,   # android/build
}

#: 内容里出现就算命中（形状级，不列具体的人名词表 —— 那份留在私人工作区）
FORBIDDEN_CONTENT = [
    (re.compile(r"sk-[A-Za-z0-9_-]{16,}"), "看着像 API key"),
    (re.compile(r"sk-ant-[A-Za-z0-9_-]{16,}"), "看着像 Anthropic key"),
    (re.compile(r"ghp_[A-Za-z0-9]{20,}"), "看着像 GitHub token"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY"), "私钥正文"),
    (re.compile(r"postgres(ql)?://[^\s'\"]+:[^\s'\"]+@"), "带密码的数据库连接串"),
]

#: ★ 0831 自查（病灶 9）：这里原来是一份 15 项的**扩展名白名单** —— 白名单之外
#:   一律静默不读。实测漏掉的有：`.env.example`（README 教人复制的模板，路径上还
#:   专门开了豁免）、`start.command`（发行脚本本体）、`LICENSE`、`.gitignore`、
#:   `.svg`（纯文本，能藏任意内容），以及所有位图。
#:   改成**黑名单 + 兜底**：不认识的扩展名一律当文本读一遍。
#:   真二进制也不再静默跳过 —— 按 latin-1 读进来跑一遍内容规则，
#:   PNG 的 tEXt/JPEG 的 EXIF 里塞的明文 key 就藏不住了（找不回中文，但形状级规则够用）。
BINARY_SUFFIX = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".tiff",
                 ".woff", ".woff2", ".ttf", ".otf", ".eot",
                 ".jar", ".apk", ".dex", ".aab", ".so", ".dylib", ".dll", ".class",
                 ".zip", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar",
                 ".pdf", ".mp3", ".mp4", ".wav", ".m4a", ".mov", ".pyc"}


def _files(staged: bool) -> tuple[list[str], str]:
    """返回（文件清单，这一趟是怎么点出来的）。

    ★ 0831 自查（病灶 9）：原来 `--staged` 那条**不看 git 的退出码** ——
      在非 git 目录里跑，`git diff --cached` 报错、stdout 是空的，
      于是清单为空、一条规则都不命中，闸门打印「✓ 暂存区干净 —— 查了 0 个文件」
      并 return 0。装成 pre-commit 钩子之后，只要 git 因为任何原因调不动，
      这个闸就是**常绿**的。工作本自己写着：「永远说『干净』的扫描器比没有更糟。」
      现在：git 调不动一律 return None → 上面按「查不了」退 2，绝不冒充干净。
    """
    if staged:
        out = subprocess.run(["git", "diff", "--cached", "--name-only"],
                             cwd=ROOT, capture_output=True, text=True)
        if out.returncode != 0:
            return ([], "")           # ← 空来源标记「查不了」，main 会退 2
        return ([f for f in out.stdout.splitlines() if f.strip()], "git 暂存区")
    out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"],
                         cwd=ROOT, capture_output=True, text=True)
    if out.returncode == 0 and out.stdout.strip():
        return ([f for f in out.stdout.splitlines() if f.strip()], "git ls-files（已按 .gitignore 排除）")
    # 不是 git 仓库：退回走文件系统
    return ([str(p.relative_to(ROOT)) for p in ROOT.rglob("*")
             if p.is_file() and not (set(p.relative_to(ROOT).parts) & _SKIP_DIRS)],
            "文件系统（不是 git 仓库）")


#: 走文件系统那条路时跳过的目录。
#: ★ `data`/`build`/`.gradle`/`__pycache__` 留在这里是**故意**的：git 那条路
#:   .gitignore 已经排除了它们，不必重复劳动。但代价是 FORBIDDEN_PATHS 里
#:   专为它们写的那几条规则在这一趟里恒不命中 —— 所以下面 `_skipped_note()`
#:   会把「跳过了什么、里面有多少东西」打出来，让「没报」和「没看」分得开。
#:   要连它们一起查（打包发出去那条路），加 `--packaging`。
_SKIP_DIRS = {".venv", "node_modules", "__pycache__", ".git", "data", "build", ".gradle"}


def _skipped_note() -> list[str]:
    """把「这一趟没看的东西」数出来。别让沉默冒充干净。"""
    lines = []
    for d in sorted(_SKIP_DIRS - {".git", ".venv", "node_modules"}):
        hits = [p for p in ROOT.rglob(d) if p.is_dir()]
        n = sum(1 for h in hits for p in h.rglob("*") if p.is_file())
        if n:
            lines.append(f"{d}/ {n} 个文件")
    return lines


def main() -> int:
    staged = "--staged" in sys.argv
    packaging = "--packaging" in sys.argv
    if packaging:
        _SKIP_DIRS.difference_update({"data", "build", ".gradle", "__pycache__"})
    files, how = _files(staged)
    if not how:
        print("✗ 查不了暂存区 —— git 调不动（这儿不是 git 仓库？）。")
        print("  ★ 闸门查不了就得说查不了，不许打印「干净」。")
        return 2

    bad: list[tuple[int, str, str]] = []
    read_fail = 0

    for rel in files:
        # ★ 取**最严重**的那条匹配，不是第一条：`data/secrets.json` 既中宽的 `data/`
        #   也中 `secrets\.json$`，原来的 first-match+break 会把它报成「运行数据」，
        #   私钥报成「运行数据」比报成「私钥」难引起注意。判定不变，只是理由说得准。
        hit = [(_SEV.get(i, 50), why) for i, (pat, why) in enumerate(FORBIDDEN_PATHS)
               if pat.search(rel)]
        if hit:
            sev, why = min(hit)
            bad.append((sev, rel, why))
            continue

        p = ROOT / rel
        if not p.is_file():
            continue
        binary = p.suffix.lower() in BINARY_SUFFIX
        try:
            # 二进制按 latin-1 读 —— 中文找不回来，但 key/私钥那类形状规则照样命中
            text = p.read_text(encoding="latin-1" if binary else "utf-8", errors="ignore")
        except Exception:
            read_fail += 1
            continue
        for pat, why in FORBIDDEN_CONTENT:
            if pat.search(text):
                # 内容里真出现了 key/私钥的形状 —— 最要命的一档，永远打在最上面
                bad.append((0, rel, why + ("（藏在二进制里）" if binary else "")))
                break

    where = "暂存区" if staged else "这个目录"
    print(f"来源：{how} —— {len(files)} 个文件" + (f"，{read_fail} 个读不出来" if read_fail else ""))
    if not staged and not packaging:
        skipped = _skipped_note()
        if skipped:
            print("没看的：" + "、".join(skipped) + "  ← 走 git 的话 .gitignore 已排除；")
            print("        要连它们一起查（打包整个目录发出去那条路），加 --packaging")

    if not bad:
        print(f"✓ {where}干净 —— 查了 {len(files)} 个文件。")
        print("  （★ 发布仍然只走 `python3 create.py <目标目录>`：")
        print("    这个闸只保证「没混进不该有的东西」，不代表目录本身就是发行包。）")
        return 0

    # ★ 0831 自查：原来是按遍历顺序打前 40 条 —— 命中一多（--packaging 下 190+），
    #   私钥和 secrets.json 就被一堆 .pyc 挤到截断线后面，**闸抓到了，人看不见**。
    #   跟今天修的一整类是同一个毛病。按危险程度排，最要命的永远在最上面。
    bad.sort(key=lambda t: (t[0], t[1]))
    print(f"✗ {where}里有 {len(bad)} 样不该发的东西：\n")
    for _sev, rel, why in bad[:40]:
        print(f"  · {rel}\n      {why}")
    if len(bad) > 40:
        rest: dict[str, int] = {}
        for _sev, _rel, why in bad[40:]:
            rest[why] = rest.get(why, 0) + 1
        print(f"  …… 还有 {len(bad) - 40} 个（" +
              "、".join(f"{w} ×{n}" for w, n in sorted(rest.items(), key=lambda kv: -kv[1])) + "）")
    print("\n发布只从 `python3 create.py <目标目录>` 的产物出发。")
    print("这些文件要么加进 .gitignore，要么发布前删掉。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
