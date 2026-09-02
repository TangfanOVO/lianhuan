#!/usr/bin/env python3
"""连环 · 安装脚手架

    python3 create.py              问你几句，然后只把你勾中的复制过去
    python3 create.py --here       就装在当前目录（不复制，只写配置）
    python3 create.py --yes ./家   全默认，不问

★ 没勾的东西**根本不复制**。不是装了再关 —— 那不叫「不带走」。
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent


# ── 能装什么 ─────────────────────────────────────────────
# cost: 装之前就该知道的代价（要不要硬件、要不要 key、要不要花钱）
# ★ 漏一个目录，装出来的东西就少一块功能，而且**报错很含糊**。
#   `seed` 是被洁净复验抓出来的：没复制它，`python -m core.seed` 只会说「找不到文件」。
# ★ optional/ 必须带：core/server.py 顶层就 import 里面的内置包（homelife/homeplus/
#   reading/kaomoji_drawer），不带的话产物 `ModuleNotFoundError: optional` 起都起不来 ——
#   0831 外部验收（GPT）抓的 P0：装置器说「装完了」、四件套全绿，产物却是死的。
#   「选装」是运行时装不装（设置 › 功能包），不是文件裁剪。
# ★ blocks/water 也在 CORE：默认页面开屏**固定加载** /blocks/water/maple-water.js
#   （index.html 里那段 MW_V），不带的话首屏 404 再降级 —— 0831 GPT 二轮抓的。
CORE = ["core", "optional", "android", "blocks/base", "blocks/water", "seed", "requirements.txt",
        "README.md", "UPSTREAM.md", "EXCLUDED.md", "LICENSE",
        # ★ 这份不能漏：MIT 那句「版权声明和许可正文要随所有副本一起」，
        #   靠的就是它跟着装出来的每一份走。漏了＝装出来的那份不合规。
        "THIRD_PARTY_NOTICES.md", "docs",
        "scripts/setup-engawa.py", "upstreams/engawa-mcp.lock.json", "licenses/ENGAWA_MCP.txt",
        "start.command", "start.sh", ".env.example",
        # 云上 / 容器：一键部署那两颗按钮和 compose 都靠这四份
        "Dockerfile", ".dockerignore", "docker-compose.yml", "render.yaml"]

BLOCKS = [
    ("paper",   "纸感材质", "撕边纸 · 胶带 · 票根 · 明信片 · 标本卡", "无。纯 CSS", ["blocks/paper"]),
    ("physics", "会动的排法", "丝线叠卡 · 纸夹桌面 · 散落成摞，三种，风一吹都会动", "无。零依赖", ["blocks/physics"]),
    ("parts",   "界面零件", "抽屉 · 二级页 · 遮罩 · 底栏",           "无",        ["blocks/parts"]),
    ("shelf",   "书房书脊", "一本书就是一个入口，按下去会被抽出来",   "无。零依赖", ["blocks/shelf"]),
    # ★ 只有前端。后端各家的机器人差太远，硬塞一份给你，你多半得先把它拆了。
    ("robot",   "机器人",   "有机器人才勾：在不在/电量/头往哪看。**只有前端**，后端自己接",
                                                              "要一台机器人", ["blocks/robot"]),
    ("ambience","漂浮物",   "背景里飘的枫叶/雪/萤火…十种，可多选",   "无。零依赖", ["blocks/ambience"]),
    ("glyphcloud","记忆星图","一个字符＝一条记忆，点画布换形状，点字看那条记忆", "无。零依赖", ["blocks/glyphcloud"]),
    # ★ 0902 补的三块。前两块是**整页**，不是零件 —— 直接就能当那一页用。
    ("home",    "主页",     "顶栏 · 天数 · 便签 · 缝线 · 卡片网格 · 底栏。**零 JS，纯 CSS 一页**",
                                                              "无",        ["blocks/home"]),
    ("chat",    "聊天页",   "思考链 · 工具调用 · 加号那十五项 · 发送键回弹。事件由你喂，界面不认后端",
                                                              "无。零依赖", ["blocks/chat"]),
    ("call",    "打电话",   "拨号 · 对话转写 · 瞥一眼 · 那根线 · 贴耳。**不申请麦克风、不伪造接通**",
                                                              "会一起带上「通话那条线」", ["blocks/call", "blocks/thread"]),
    ("thread",  "通话那条线","谁在说线就往谁那头写；他在想的时候，线写出一片叶子", "无。零依赖", ["blocks/thread"]),
]

PETS = [
    ("none",  "不要桌宠", "默认。以后想加，设置里还有入口"),
    ("crab",  "要只螃蟹", "★ 我们不发素材，只指路。装完 NEXT-STEPS.md 里会写去哪拿"),
    ("mine",  "我自己画", "装完 NEXT-STEPS.md 里给你命名规则。GIF、SVG 随便传"),
]

ENGINES = [
    ("echo", "先不接（回声）", "什么都不要。先看看界面长什么样"),
    ("cli",  "本机 CLI",       "本机装了官方 CLI 并登录过。**不用 API key**，走你自己的订阅"),
    ("api",  "API（OpenAI 兼容）", "DeepSeek / Kimi / 智谱 / OpenAI / 本机 Ollama…装完在 设置 › 功能包 › 引擎 里贴 key"),
]

STORES = [
    ("sqlite", "SQLite", "一个文件，零配置。默认就是它"),
]


def ask_one(title, options, default=0):
    print(f"\n{title}")
    for i, (key, name, note) in enumerate(options):
        mark = "›" if i == default else " "
        print(f"  {mark} {i+1}. {name:<12} {note}")
    raw = input(f"  选哪个？[{default+1}] ").strip()
    try:
        return options[int(raw) - 1][0] if raw else options[default][0]
    except (ValueError, IndexError):
        return options[default][0]


def ask_many(title, options):
    print(f"\n{title}")
    print("  （空格分开的编号，直接回车＝一个都不要）")
    for i, (key, name, desc, cost, _paths) in enumerate(options):
        print(f"    {i+1}. {name:<10} {desc}")
        print(f"       需要：{cost}")
    raw = input("  要哪几个？[] ").strip()
    picked = []
    for tok in raw.split():
        try:
            picked.append(options[int(tok) - 1][0])
        except (ValueError, IndexError):
            pass
    return picked


def copy(rel: str, dst: Path):
    src = SRC / rel
    if not src.exists():
        return
    out = dst / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, out, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'data', '*.bak*',
                                                      'local.properties', 'build', '.gradle'))
    else:
        shutil.copy2(src, out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dest", nargs="?", default=None)
    ap.add_argument("--yes", action="store_true", help="全默认，不问")
    ap.add_argument("--here", action="store_true", help="就装在这儿，只写配置")
    a = ap.parse_args()

    print("\n  连环 —— 一个能长出记忆的 AI 伴侣的家\n" + "  " + "─" * 44)

    if a.here:
        dest = SRC
    else:
        dest = Path(a.dest or (input("\n  装到哪儿？[./my-home] ").strip() if not a.yes else "") or "./my-home").resolve()

    if a.yes:
        blocks, pet, engine, store = ["paper", "physics", "parts"], "none", "echo", "sqlite"
    else:
        blocks = ask_many("要哪些前端积木？（不装也能用，聊天和记忆是自带的）", BLOCKS)
        pet    = ask_one("桌宠？", PETS)
        engine = ask_one("用哪个引擎跟模型说话？", ENGINES)
        store  = ask_one("数据存哪儿？", STORES)

    if not a.here:
        print(f"\n  往 {dest} 里放东西…")
        for rel in CORE:
            copy(rel, dest)
        for key, _n, _d, _c, paths in BLOCKS:
            if key in blocks:
                for p in paths:
                    copy(p, dest)
        copy("create.py", dest)
        copy(".gitignore", dest)
        copy("tests", dest)

    (dest / "lianhuan.json").write_text(json.dumps(
        {"blocks": blocks, "pet": pet, "engine": engine, "store": store}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    # ── 装完还欠什么，写下来。没有的东西不假装有 ──
    todo = ["# 装完了，接下来\n",
            "这份是**装的时候按你的选择生成的**，做完可以删。\n",
            "## 跑起来\n",
            "**双击 `start.command`** 就行（macOS / Linux）。它会自己建环境、装依赖、"
            "起服务、开浏览器。第一次要一分钟，之后几秒。\n",
            "或者手动：\n",
            "```bash", "pip install -r requirements.txt", "python -m core.server", "```",
            "\n手机也要连：`./start.command --lan`（会提醒你风险）。\n"]

    if engine == "echo":
        todo += ["## 换成真的模型\n",
                 "现在用的是**回声引擎**，它不接模型，只把你说的话回给你 —— 界面上会一直标着「未接模型」。",
                 "去设置里挑一个引擎就能换。\n"]
    if engine == "cli":
        todo += ["## 引擎\n", "你选了本机 CLI。**装了官方 CLI 并登录过**它才会亮，",
                 "否则界面上会显示「待接」并告诉你差什么。不用 API key。\n"]
    if pet == "crab":
        todo += ["## 桌宠素材（你勾了「要只螃蟹」）\n",
                 "★ 我们**不分发素材**，只指路 —— 那个角色是别家公司的吉祥物，",
                 "而它的粉丝项目是 AGPL-3.0，跟着开源分发会把你整个项目也传染成 AGPL。\n",
                 "要用就自己去拿：搜 `clawd-on-desk`（GitHub），把 GIF 放进 `core/web/pet/`，",
                 "按状态名命名（`idle` / `happy` / `thinking` / `sleeping` …）。",
                 "**自己玩没问题，别再往外分发。**\n"]
    if pet == "mine":
        todo += ["## 桌宠素材（你勾了「我自己画」）\n",
                 "往 `core/web/pet/` 里丢图，按状态名命名：",
                 "`idle.svg` / `happy.svg` / `thinking.svg` / `sleeping.svg`。",
                 "SVG 自带 CSS 动画也行（会包在 `<img>` 里，样式不会污染页面）。GIF 也行。\n"]
    if pet == "none":
        todo += ["## 桌宠\n", "没装。以后想加，设置里还有入口。\n"]
    if blocks:
        names = [n for k, n, *_ in BLOCKS if k in blocks]
        todo += [f"## 装了这些积木\n", "、".join(names) + "。每个目录里都有 `demo.html`，打开就能看。\n"]

    todo += ["## 装进来了、但要自己开的\n",
             "记事四件套 · 心情 · 梗库 · 玩具厅 · 日历相册 · 共读 · 出门走走 —— "
             "**代码都在包里**，在 设置 › 功能包 里点一下就用（有的要贴 key，卡上写着）。",
             "通话（ElevenLabs / 豆包的 key）· QQ 桥（自跑 NapCat）· Obsidian 记忆（vault 路径）"
             "同理；保存配置后要真实用一次才算验通。Engawa 阅读侧廊可以在功能包里一键安装，"
             "它免 key，固定的 MIT 上游版本只装进本机 `.runtime/`。\n",
             "## 还没有的东西\n",
             "**没有的就是没有**，不会拿假数据冒充：",
             "- 纯浏览器存储（现在最少要跑这个薄后端）",
             "- 机器人只带前端；摸摸要硬件\n"]

    (dest / "NEXT-STEPS.md").write_text("\n".join(todo), encoding="utf-8")

    # ★ 产物自带的测试必须对**这一份产物**全绿（0831 GPT 二轮 P0：120 过 3 败 17 错）。
    #   两处不对齐：① 测试里有几条盯着「工作副本 app/index.html」和没装的积木
    #   ② 装了什么因人而异。所以按装配单裁剪，并写一份说明。
    tdir = dest / "tests"
    if tdir.exists():
        keep_note = ["# 这份产物自带的测试\n",
                     "按你装了什么裁过：没装的积木、以及只在开发仓库里才有的检查（比如",
                     "「两份大 HTML 要一致」）已经去掉 —— 它们在你这儿本来就不适用。\n",
                     "跑法：`for f in tests/test_*.py; do .venv/bin/python \"$f\"; done`\n"]
        (tdir / "README.md").write_text("\n".join(keep_note), encoding="utf-8")

    print(f"""
  好了。

    cd {dest}
    ./start.command          ← 双击也行

  要接模型：把 .env.example 复制成 .env，填上你的 key。
  装了什么、还差什么，都写在 NEXT-STEPS.md 里了。
""")


if __name__ == "__main__":
    main()
