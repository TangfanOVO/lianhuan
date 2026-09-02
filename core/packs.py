"""功能包 —— 让「待接」能一键接上，而不是把人指向仓库让他自己想办法。

用户看了另一个项目的同类页得出的结论：每个选项都只指向仓库＝用户和 AI 都没有手。
所以这里的规矩：
  · 条件齐的包 → **「直接启用」真的启用**（挂路由、更新能力表），点完就能用
  · 缺东西的包 → 说清缺什么（哪个环境变量、哪个外部服务）
  · 只有契约的 → 老实标「只有契约」，选它就写一份装配单（要做什么、契约在哪），
    **不冒充能用**

新增不改旧：这个模块被 server 挂上，动态往 app 里 include 路由、往 WIRED 里添 key。
"""
from __future__ import annotations

import importlib
import inspect
import os
import subprocess
import sys
import time
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core import secrets

router = APIRouter()
_app = None
_wired: list = []
_store = None
_enabled: set = set()
_pick = None          # () -> Engine。由 server 在 bind 时传进来，**不许在这儿 import server**


def bind(app, wired: list, store=None, pick_engine=None) -> None:
    """★ `pick_engine` **必须从外面传进来**，包里绝不许 `from core.server import …`。

    为什么：`python -m core.server` 跑起来时，入口模块叫 `__main__`；包里再去
    import `core.server`，Python 会**再执行一遍整个 server.py**（那是第二份模块）。
    第二份执行时又会调一次这个 bind，把下面这个 `_app` 覆盖成**它自己那个 app** ——
    于是之后所有 `_mount_first` 都挂到了那个没人用的影子上：
    包显示「已接上」，接口却整片 404。

    这个坑这个项目踩过两次了（第二次是 0830 我自己，注释都在 server.py 里写着还是踩了）。
    """
    global _app, _wired, _store, _pick
    _app, _wired, _store = app, wired, store
    if pick_engine is not None:
        _pick = pick_engine
    # ★ 启动时把条件齐的真包直接挂上 —— 贴过 key 的人重启后不该再点一次「启用」
    for p in PACKS:
        if p["kind"] == "real" and p["id"] not in _enabled and not p["check"]():
            if inspect.iscoroutinefunction(p["enable"]):
                # Async adapters are brought up by the application's startup event.
                # Calling them here would create an un-awaited coroutine before an event loop exists.
                continue
            try:
                p["enable"]()
                _enabled.add(p["id"])
            except Exception as e:
                print(f"[packs] {p['id']} 自动挂载摔了：{e}", flush=True)


# ── 包注册表 ──────────────────────────────────────────────
def _qq_check():
    if not secrets.get("NAPCAT_WEBUI_TOKEN"):
        # ★ 0901：原来这句把环境变量名 `NAPCAT_WEBUI_TOKEN` 摆给用的人看 ——
        #   那是给写代码的人看的。名字该在下面的格子上，不该在「缺什么」里。
        return ["还差 NapCat 的登录口令 —— 你自己跑那个 NapCat 时，它的网页后台会让你设一个"]
    return []


def _call_check():
    if secrets.get("ELEVENLABS_API_KEY"):
        return []
    if secrets.get("VOLC_TTS_APPID") and secrets.get("VOLC_TTS_TOKEN"):
        return []      # 只有豆包＝能说不能听，enable 后 listen 会自己老实说缺哪半边
    # ★ 0901 逮到的：这句看不懂。原文是
    #   「贴一把 key：ElevenLabs 一把全有（能听能说），或豆包 appid+token（只能说）」——
    #   「只能说」三个字**没有主语**，读不出来是谁只能说、只能说什么；
    #   而且它把两条路并排摆着，也没说该选哪条。缺什么就直说缺什么。
    # ★ 0901 有人问过：中文不是归豆包、英文归 ElevenLabs 吗，为什么豆包听不见？——
    #   问得对，是这句话写窄了，而且写得像在怪豆包。查清楚的事实：
    #     · **说**那半这儿已经按语言分好了（`_tts_chain`：中文优先豆包、英文优先 ElevenLabs）
    #     · **听**那半这儿只接了 ElevenLabs 一家（`api_listen` 没 key 直接 501）
    #     · 所以不是「豆包听不见」，是**我们没给它接耳朵**（豆包有语音识别，只是没接）
    #     · 原项目那边听根本不用 ElevenLabs —— 用本机跑的 faster-whisper，免费
    #   缺口是我们的，话就得这么说。
    return ["还差一把 ElevenLabs 钥匙 —— 这一版只接了它一家做「听」，没有它就听不见你说话。"
            "（豆包那对 appid＋token 只接了「说」那半；豆包其实也能听，"
            "只是这一版还没接 —— 想自己接别家识别，契约在 docs/API.md。）"]


def _engawa_executable() -> Path:
    root = Path(__file__).resolve().parent.parent / ".runtime" / "engawa"
    choices = (root / "bin" / "engawa-mcp", root / "Scripts" / "engawa-mcp.exe")
    return next((path for path in choices if path.is_file()), choices[0])


def _engawa_check():
    if not _engawa_executable().is_file():
        return ["本机还没装 Engawa；点下面安装即可（MIT、免 key，运行时不进 Git）"]
    return []


async def _engawa_enable():
    from core import mcp_client
    command = _engawa_executable()
    if not command.is_file():
        raise RuntimeError("Engawa 运行时还没安装")
    cache = Path(os.environ.get("LIANHUAN_DB", "data/lianhuan.db")).parent / "engawa-cache"
    mcp_client.save_server("engawa", str(command), [], {"ENGAWA_CACHE_DIR": str(cache)})
    await mcp_client.start_all()
    state = next((item for item in mcp_client.status() if item["name"] == "engawa"), None)
    if not state or not state["ok"]:
        raise RuntimeError((state or {}).get("err") or "Engawa 没有成功启动")


def _engawa_connected() -> bool:
    from core import mcp_client
    return any(item["name"] == "engawa" and item["ok"] for item in mcp_client.status())


def _obsidian_check():
    from core import secrets
    from pathlib import Path
    v = secrets.get("OBSIDIAN_VAULT")
    if not v:
        return ["还差一个文件夹路径 —— 你放笔记的那个文件夹，"
                "从最开头那个 / 写起的完整路径（不是「我的文稿/笔记」这种半截的）"]
    if not Path(v).expanduser().is_dir():
        return [f"路径不存在或不是文件夹：{v}"]
    return []


def _obsidian_enable():
    """★ store 走 bind 注入，**绝不 `from core.server import store`** ——
    `python -m core.server` 下入口模块叫 `__main__`，再 import core.server 会加载出
    第二份模块（两个 app 两个 store），patch 打在影子上：enable 显示成功、
    新记忆却还写进 SQLite。真栽过，查了一轮才明白。"""
    from core import secrets
    from optional.obsidian_memory.store import enable as _en
    r = _en(_store, secrets.get("OBSIDIAN_VAULT"))
    if not r.get("ok"):
        raise RuntimeError(r.get("err") or "没接上")


def _call_enable():
    mod = importlib.import_module("optional.callkit.routes")
    # 能插话那条要两样东西：库（存这一通说了什么）和「去问哪个引擎」。
    # ★ 从外面注入，别在包里 import server —— `python -m core.server` 下会拿到第二份模块，
    #   补丁打在影子上（这个坑这个项目踩过一次，注释留在 core/server.py 里）。
    try:
        dx = importlib.import_module("optional.callkit.duplex")
        dx.bind(_store, _pick)          # ★ 用 bind 时传进来的那个，别去 import server
    except Exception as e:
        print("[packs] 能插话那条没接上：", e, flush=True)
    _mount_first(mod.router)
    for k in ("tts", "listen", "call", "语音输入", "callLang", "callDuplex"):
        if k not in _wired:
            _wired.append(k)


def _mount_first(r) -> None:
    """★ 运行时挂的路由要插到**队首**。
    server 里有一条兜底静态通配 `/{name:path}`，它注册得早；FastAPI 按顺序匹配，
    append 上去的新路由永远轮不到 —— enable 显示成功、接口却 404，查过一回。"""
    n0 = len(_app.router.routes)
    _app.include_router(r)
    new = _app.router.routes[n0:]
    del _app.router.routes[n0:]
    for x in reversed(new):
        _app.router.routes.insert(0, x)


def _qq_enable():
    mod = importlib.import_module("optional.qq_napcat.napcat")
    _mount_first(mod.router)
    for k in ("qqStatus", "qqRestart"):
        if k not in _wired:
            _wired.append(k)


PACKS = [
    {"id": "engawa", "name": "Engawa 阅读侧廊", "kind": "real",
     "desc": "网页、RSS、书架、今晚的天空、每日诗画、NASA 天文图和 arXiv。"
             "固定 MIT 上游版本装进本机隔离运行时，AI 和檐廊页面都能直接用；不要 key。",
     "check": _engawa_check, "enable": _engawa_enable,
     "connected": _engawa_connected,
     "setup": "scripts/setup-engawa.py", "setup_label": "安装 Engawa",
     "contract": "UPSTREAM.md（Engawa）· licenses/ENGAWA_MCP.txt"},
    {"id": "qq-napcat", "name": "QQ · 在岗吗", "kind": "real",
     "desc": "看他的 QQ 在不在线，掉线了扫个码救回来。\n"
             "要自己跑一个叫 NapCat 的东西（开源的，让程序能上 QQ）—— 用小号，别用你天天在用的那个。",
     "check": _qq_check, "enable": _qq_enable,
     "keys": [{"id": "NAPCAT_WEBUI_TOKEN", "label": "NapCat WebUI 口令"}],
     "contract": "optional/qq_napcat/README.md"},
    {"id": "call", "name": "通话", "kind": "real",
     # ★ 0901 逮到的：这段看不懂 —— 原来它把每把钥匙买到什么又讲了一遍，
     #   跟下面每个格子的说明**重复**——同一件事说两遍，人不知道该看哪句。
     #   这儿只说「这是什么」，「哪把钥匙买到什么」交给格子自己说。
     "desc": "跟他打电话。你说话，他听见了、想一想、开口回你 —— "
             "想什么用的是你自己配的那个引擎，所以他记得你、也还是你设定的那个他。\n"
             "语言只有中文和英文两个选择，用哪家的嗓子它自己挑。",
     "check": _call_check, "enable": _call_enable,
     # ★ 0901 逮到的：这几个格子看不懂。原来是五个一模一样的密码框排一列，
     #   唯一的区别写在 placeholder 里 —— 而 placeholder **一打字就没了**，
     #   填到第三个已经分不清哪个是哪个；`ELEVEN_MODEL` 填的是 `eleven_v3` 这种普通文字，
     #   却也做成密码框，**自己打了什么都看不见**。
     #   现在每个格子带上：group（这一组买到什么）· label（露在外面的名字）
     #   · hint（一句话说清是什么、从哪拿）· secret（要不要遮）· need（必填还是可选）。
     #   ★ 这几个字段都是**可选**的：别的包没写就照老样子画，一个字节不受影响。
     "keys": [{"id": "ELEVENLABS_API_KEY", "group": "① 让他听得见你说话",
                "label": "ElevenLabs 钥匙", "need": True, "secret": True,
                "hint": "他靠这把听你说话、也靠这把开口。没有它就只能打字。"},
              {"id": "ELEVEN_MODEL", "group": "① 让他听得见你说话",
                "label": "ElevenLabs 模型（可留空）", "secret": False,
                "hint": "填 eleven_v3 他才会叹气、会笑出声。留空就是普通语气。"},
              {"id": "VOLC_DUPLEX_KEY", "group": "② 一边说一边插话（全双工）",
                "label": "豆包「端到端实时语音」钥匙", "secret": True,
                "hint": "不用等他说完就能打断他。★ 要的是「新版控制台 › API Key 管理」里那把，跟下面那两个 appid/token 不是一回事，别混。"},
              # ★ 0901 有人问过：豆包的 appid 和 access token 到底是什么 —— 问得对，
              #   原来的说明没讲**从哪拿**，也没讲它跟上面那把豆包钥匙是两回事。
              {"id": "VOLC_TTS_APPID", "group": "③ 换一把嗓子（可留空 · 今晚用不上）",
                "label": "豆包 appid", "secret": False,
                "hint": "这一组只管「他说」，跟「他听」无关，不填也能打电话。"
                        "★ 跟上面那把豆包钥匙**不是同一样东西**：那把是「端到端实时语音」，"
                        "这一对是「语音合成」。在火山引擎控制台 › 语音技术 › 语音合成 里，"
                        "开通之后会给你一对 appid ＋ access token。"
                        "填了他就用豆包的中文嗓子（比 ElevenLabs 自然些），不填就用 ElevenLabs。"},
              {"id": "VOLC_TTS_TOKEN", "group": "③ 换一把嗓子（可留空 · 今晚用不上）",
                "label": "豆包 access token", "secret": True,
                "hint": "跟上面那个 appid 成对出现，同一个页面上就有。两个要一起填才生效。"}],
     "contract": "docs/API.md（listen / tts 的形状）· 原项目那条端到端全双工见 UPSTREAM.md"},
    {"id": "reading", "name": "共读", "kind": "builtin",
     "desc": "传一本 txt 进来，它自己切成一章一章，你们就着书读、划句子、聊这一章。\n"
             "装好就能用，不用配什么。（epub 和多设备同步进度还没做）",
     "contract": "docs/API.md（books 一族）"},
    {"id": "obsidian", "name": "记忆存成 markdown", "kind": "real",
     "desc": "把记忆存成一个文件夹里的 md 笔记 —— 你看得见、也改得动，他照样记得。\n"
             "存的是「标准 markdown ＋ YAML frontmatter」，所以吃本地 md 文件夹的软件都认：\n"
             "Obsidian · Logseq · Foam · Zettlr · Joplin（md 模式）· 甚至就用 VS Code。\n"
             "贴一个文件夹路径就行，记忆会放进里面的「连环记忆/」，别的东西一个不碰。\n"
             "不贴也没关系，默认那套一样好使（就是只能在这儿看）。",
     "check": _obsidian_check, "enable": _obsidian_enable,
     "keys": [{"id": "OBSIDIAN_VAULT",
                "label": "那个文件夹的绝对路径（Obsidian 叫 vault，别家就是个普通文件夹）"}],
     "contract": "docs/MEMORY.md（记忆的实现本来就可换，这是第一个真示范）"},
    {"id": "homeplus", "name": "家什与台账", "kind": "builtin",
     "desc": "日历与纪念日、相册、我在哪、正在听、人设改动历史、"
             "一抽屉基础颜文字。内置实现，装好就在用。",
     "contract": "docs/API.md。更全的颜文字抽屉见装配单（那是另一个人的开源项目）"},
    {"id": "writings", "name": "记事四件套", "kind": "builtin",
     "desc": "信、日记、碎碎念、空间（动态与楼中回复，AI 会在楼里接话）。内置实现，装好就在用。",
     "contract": "docs/API.md（letters / diary / notes / moments）—— 不想用内置的，照契约换成自己的"},
    {"id": "mood", "name": "心情", "kind": "builtin",
     "desc": "六维心情值，AI 自己一笔一笔记涨落和原因。内置实现，装好就在用。",
     "contract": "docs/API.md（mood）。原项目那套 12 维引擎见 UPSTREAM.md 心潮那条"},
    {"id": "fish", "name": "钓鱼", "kind": "stub",
     "desc": "钓鱼的鱼篓和图鉴 —— 这儿只有壳子，玩法要自己接。\n"
             "想让他自己去钓鱼：找个钓鱼小游戏，按上面「他的外接工具」那一节接进来。",
     "contract": "docs/API.md（fish）· UPSTREAM.md（外部小游戏那条）"},
    {"id": "memes", "name": "梗库", "kind": "builtin",
     "desc": "只有你们懂的词条：加梗、改梗、翻梗。内置实现，装好就在用。",
     "contract": "docs/API.md（memes）。颜文字抽屉见 UPSTREAM.md（那是另一个人的开源项目，接它的 MCP）"},
    {"id": "play", "name": "玩具厅", "kind": "builtin",
     "desc": "AI 写的小网页丢进 data/plays/ 就上架。内置实现，装好就在用。",
     "contract": "docs/API.md（plays）"},
]


def _state(p) -> dict:
    out = {"id": p["id"], "name": p["name"], "desc": p["desc"], "kind": p["kind"],
           "contract": p.get("contract", ""),
           "keys": [{**k, "set": bool(secrets.get(k["id"]))} for k in p.get("keys", [])]}
    if p.get("setup"):
        out["setup"] = True
        out["setup_label"] = p.get("setup_label") or "安装"
    if p.get("connected") and p["connected"]():
        out["state"] = "on"
    elif p["kind"] == "builtin":
        out["state"] = "on"
        out["builtin"] = True
    elif p["kind"] == "stub":
        out["state"] = "stub"
    elif p["id"] in _enabled:
        # ★ 挂上了 ≠ 还能用:key 事后被清掉的话,卡上不许继续写「已接上」。
        #   (0830 真发生过:验证用的假 key 清了,_enabled 还记着,五把钥匙全空却显示 on)
        missing = p["check"]()
        out["state"] = "on" if not missing else "missing"
        if missing:
            out["missing"] = missing
    else:
        missing = p["check"]()
        out["state"] = "ready" if not missing else "missing"
        out["missing"] = missing
    return out


@router.get("/api/packs")
def list_packs():
    return JSONResponse({"packs": [_state(p) for p in PACKS]})


@router.post("/api/packs/{pid}/enable")
async def enable_pack(pid: str):
    p = next((x for x in PACKS if x["id"] == pid), None)
    if p is None:
        return JSONResponse({"error": "没有这个包"}, status_code=404)
    if p["kind"] == "stub":
        return JSONResponse({"error": "这个包目前只有契约 —— 选「写进装配单」那条路"},
                            status_code=409)
    if pid in _enabled or (p.get("connected") and p["connected"]()):
        return JSONResponse({"ok": True, "state": "on", "note": "本来就开着"})
    missing = p["check"]()
    if missing:
        return JSONResponse({"error": "还缺东西", "missing": missing}, status_code=428)
    try:
        result = p["enable"]()
        if inspect.isawaitable(result):
            await result
    except Exception as e:
        return JSONResponse({"error": f"启用时摔了一跤：{type(e).__name__}: {e}"[:200]},
                            status_code=500)
    _enabled.add(pid)
    return JSONResponse({"ok": True, "state": "on"})


@router.post("/api/packs/{pid}/setup")
async def setup_pack(pid: str):
    """Run one repository-owned pinned installer.  Gate middleware makes this local-only."""
    p = next((x for x in PACKS if x["id"] == pid), None)
    if p is None or not p.get("setup"):
        return JSONResponse({"error": "这个包没有一键安装器"}, status_code=404)
    script = Path(__file__).resolve().parent.parent / p["setup"]
    try:
        done = await __import__("asyncio").to_thread(
            subprocess.run, [sys.executable, str(script)], cwd=str(script.parent.parent),
            capture_output=True, text=True, timeout=600,
        )
        if done.returncode:
            return JSONResponse({"error": "安装没有完成；请在终端运行 python3 scripts/setup-engawa.py 看详情"},
                                status_code=500)
        result = p["enable"]()
        if inspect.isawaitable(result):
            await result
        _enabled.add(pid)
        return JSONResponse({"ok": True, "state": "on"})
    except subprocess.TimeoutExpired:
        return JSONResponse({"error": "安装超过十分钟，已停止等待；可以在终端重试"}, status_code=504)
    except Exception as e:
        return JSONResponse({"error": f"安装后没能接上：{type(e).__name__}: {e}"[:200]}, status_code=500)


@router.post("/api/packs/{pid}/keys")
async def pack_keys(pid: str, req: Request):
    """贴 key。存 secrets（0600），不进库不进导出；存完顺手试着启用。"""
    p = next((x for x in PACKS if x["id"] == pid), None)
    if p is None or not p.get("keys"):
        return JSONResponse({"error": "这个包不收 key"}, status_code=404)
    b = await req.json()
    allow = {k["id"] for k in p["keys"]}
    secrets.set_many({k: v for k, v in (b or {}).items() if k in allow})
    missing = p["check"]() if p.get("check") else []
    if not missing and p["kind"] == "real" and pid not in _enabled:
        try:
            p["enable"]()
            _enabled.add(pid)
            return JSONResponse({"ok": True, "state": "on"})
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)[:200]}, status_code=500)
    return JSONResponse({"ok": True, "state": "ready" if not missing else "missing",
                         "missing": missing})


@router.post("/api/packs/{pid}/plan")
def plan_pack(pid: str):
    """「不用内置的」那条路：写一份装配单，说清要做什么、契约在哪。"""
    p = next((x for x in PACKS if x["id"] == pid), None)
    if p is None:
        return JSONResponse({"error": "没有这个包"}, status_code=404)
    plans = Path(os.environ.get("LIANHUAN_DB", "data/lianhuan.db")).parent / "plans"
    plans.mkdir(parents=True, exist_ok=True)
    f = plans / f"{pid}.md"
    body = (f"# 装配单 · {p['name']}\n\n"
            f"记于 {time.strftime('%Y-%m-%d %H:%M')}。你选了**自己接**这个包。\n\n"
            f"要做的：照契约把接口实现出来，挂到这个后端（或你自己的后端）上。\n\n"
            f"契约在：{p.get('contract') or 'docs/API.md'}\n\n"
            f"接好之后把对应的 key 加进 core/server.py 的 WIRED，界面上的「待接」自己会消失。\n")
    f.write_text(body, encoding="utf-8")
    return JSONResponse({"ok": True, "plan": str(f), "body": body})
