"""最小后端 —— 一条命令起来就能开聊。

    python -m core.server              # 只有本机能连
    python -m core.server --lan        # 同一个 wifi 的手机也能连（会提醒你风险）

## 它为什么存在（而不是纯前端直连模型）

因为**密钥不该进浏览器**。浏览器里的东西，装了扩展的人、共用设备的人、
甚至一个粗心的截图都能带出去。所以哪怕你只是自己一个人用，
也让这个薄薄的一层替你拿着 key —— 它只做转发，不上任何云。

不想要服务器？那就跑本机模型（Ollama / LM Studio），或者用 CLI 引擎 ——
那两种本来就没有 key 要藏。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse, RedirectResponse,
                               Response, StreamingResponse)

from .engines.base import Turn as EngineTurn
from .engines.echo import EchoEngine
from .jobs import JobRegistry
from .memory import build_injection
from .protocol import DONE, SAY, SEP, THINK, sse, split_say
from .store.base import Memory as StoredMemory, Turn as StoredTurn
from .store.sqlite import SqliteStore

HERE = Path(__file__).parent
WEB = HERE / "web"
#: 横向积木。★ 内核和积木共用**同一份**底座 —— 各存一份迟早会漂移，
#: 到时候「只拿走底座」的人和用整个应用的人看到的会是两套东西。
BLOCKS = HERE.parent / "blocks"

app = FastAPI(title="连环 · 开源版")
store = SqliteStore(os.environ.get("LIANHUAN_DB", "data/lianhuan.db"))
jobs = JobRegistry()

# ── 门（0830 加的，默认整个不生效）────────────────────────────
# 只听 127.0.0.1 的时候一行都不拦；开了 --lan 才装上（见 core/gate.py 里那张表）。
# ★ 会起进程的接口：纯本机可用；开门后默认全关，明确声明直连本机时才开。
from . import gate as _gate   # noqa: E402

_CSP = "; ".join((
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline'",
    "script-src-attr 'none'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob: http: https:",
    "media-src 'self' data: blob: http: https:",
    "font-src 'self' data:",
    "connect-src 'self'",
    "worker-src 'self' blob:",
    "frame-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
))
_SECURITY_HEADERS = {
    "Content-Security-Policy": _CSP,
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), geolocation=(), microphone=(self)",
}


def _secured(response: Response) -> Response:
    for key, value in _SECURITY_HEADERS.items():
        response.headers[key] = value
    return response


def _same_origin(request: Request) -> bool:
    """浏览器的写请求只收同源；Host 由真实目标决定，反代也通常原样保留。"""
    origin = request.headers.get("origin")
    if not origin:
        return request.headers.get("sec-fetch-site", "").lower() != "cross-site"
    try:
        return origin != "null" and urlsplit(origin).netloc.lower() == request.headers.get("host", "").lower()
    except ValueError:
        return False


def _secure_cookie(request: Request) -> bool:
    value = os.environ.get("LIANHUAN_COOKIE_SECURE", "").strip().lower()
    if value in {"1", "true", "yes"}:
        return True
    if value in {"0", "false", "no"}:
        return False
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip() == "https"


@app.middleware("http")
async def _gate_mw(request: Request, call_next):
    peer = request.client.host if request.client else ""
    addr = _gate.client_addr(peer, request.headers.get("x-forwarded-for", ""))
    here = _gate.local_addr(addr)
    path = request.url.path

    # 浏览器跨站写入和 text/plain JSON 都拒绝。后者本来能绕过 CORS 预检。
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        if not _same_origin(request):
            return _secured(JSONResponse({"error": "只收来自连环自己页面的写请求"}, status_code=403))
        if request.headers.get("content-type", "").lower().startswith("text/plain"):
            return _secured(JSONResponse({"error": "JSON 请求要用 application/json"}, status_code=415))

    # 安卓完整体虽只听回环，回环不是应用沙箱；每次启动的随机票要护住页面和全部 API。
    if os.environ.get("LIANHUAN_ANDROID_TOKEN"):
        if not _gate.check_android_cookie(request.cookies.get(_gate.ANDROID_COOKIE) or ""):
            return _secured(JSONResponse({"error": "这份本机服务只给当前完整体使用"}, status_code=401))
        return _secured(await call_next(request))

    # ① 命令执行类：认证过也不给外面用。密码会泄，起进程不给第二次机会。
    if _gate.command_path(path) and (not here or (_gate.on() and not _gate.allow_local_commands())):
        return _secured(JSONResponse({"error": "这条只能在明确允许的本机页面使用 —— 它会起一个进程。"},
                                     status_code=403))

    # ② 没开 --lan → 照旧；开了之后连 127.0.0.1 也必须报门（它可能是反代）。
    if not _gate.on():
        return _secured(await call_next(request))

    # ③ 开到网络上了：先报门
    if _gate.check_cookie(request.cookies.get(_gate.COOKIE) or ""):
        return _secured(await call_next(request))
    if path == "/api/login":
        return _secured(await call_next(request))
    if path == "/login":
        return _secured(HTMLResponse(_gate.LOGIN_HTML))
    if path.startswith("/api/") or path in ("/chat", "/chat/attach"):
        return _secured(JSONResponse({"error": "要先登录"}, status_code=401))
    return _secured(RedirectResponse("/login"))


@app.post("/api/login")
async def api_login(req: Request):
    """报门。只有 --lan 起来的时候才有意义；没开的时候直接说不需要。"""
    if not _gate.on():
        return {"ok": True, "note": "这台机器只听本机，不需要口令"}
    #: ★ 默认按 socket 对端算；只有显式可信反代能提供 X-Forwarded-For。
    peer = req.client.host if req.client else ""
    addr = _gate.client_addr(peer, req.headers.get("x-forwarded-for", ""))
    wait = _gate.locked(addr)
    if wait:
        return JSONResponse({"ok": False, "locked": wait,
                             "error": f"错太多次了，等 {wait // 60 + 1} 分钟再试"}, status_code=429)
    b = await req.json()
    tok = _gate.check_password((b.get("password") or "").strip())
    if not tok:
        wait = _gate.note_fail(addr)
        if wait:
            return JSONResponse({"ok": False, "locked": wait,
                                 "error": f"错太多次了，等 {wait // 60 + 1} 分钟再试"}, status_code=429)
        return JSONResponse({"ok": False}, status_code=401)
    _gate.note_ok(addr)
    r = JSONResponse({"ok": True})
    # httponly：页面上的脚本读不到它（万一哪天有个 XSS，至少偷不走这一张票）
    r.set_cookie(_gate.COOKIE, tok, max_age=_gate.MAXAGE, httponly=True,
                 samesite="lax", secure=_secure_cookie(req))
    return r


# 聊天/记忆的视图接口（按天翻、收藏、热力图、搜索、总览）——独立模块，新增不动旧
from .views import bind as _views_bind, router as _views_router   # noqa: E402
_views_bind(store)
app.include_router(_views_router)

async def engine_say(prompt: str) -> str:
    """用当前引擎说一句（给空间楼中接话、替用户发动态那类小事用）。
    带人设不带历史 —— 一句话的事，别把整个上下文的钱花进去。"""
    from .engines.base import Turn as ET
    persona = store.get_setting("persona", {}) or {}
    sysp = (persona.get("ai") or {}).get("text") or ""
    eng = pick_engine()
    outs = []
    async for ev in eng.stream(ET(message=prompt, system=sysp)):
        try:
            d = json.loads(ev[6:])
        except Exception:
            continue
        if d.get("type") == SAY:
            outs.append(d.get("text") or "")
    return " ".join(outs).strip()


# 过日子那一套（记事四件套/心情/梗库/玩具厅）：**内置实现，默认就装上** ——
# 定的：想偷懒直接用我们的；不喜欢魔改再去 UPSTREAM 找原文献
from optional.homelife.routes import bind as _home_bind, mood_bump, router as _home_router   # noqa: E402
from optional.homelife.routes import apply_marker as _home_mood_marker, mood_inject as _home_mood_inject   # noqa: E402
_home_bind(store, engine_say)
app.include_router(_home_router)


@app.get("/plays/{name}")
def get_play(name: str):
    p = _safe(Path(os.environ.get("LIANHUAN_DB", "data/lianhuan.db")).parent / "plays", name)
    return FileResponse(p) if p else JSONResponse({"error": "没有这个小玩意"}, status_code=404)


# 家什与台账（日历/钱包/相册/在哪/正在听/人设历史/颜文字）＋ 共读：内置默认装
from optional.homeplus.routes import bind as _hp_bind, router as _hp_router   # noqa: E402
_hp_bind(store)
app.include_router(_hp_router)
from optional.reading.routes import bind as _rd_bind, router as _rd_router   # noqa: E402
_rd_bind(store, engine_say)
app.include_router(_rd_router)


# 颜文字抽屉（这家自己发布的开源组件，MIT）：前端 vendor + v2 状态接口，内置默认装
from optional.kaomoji_drawer.routes import router as _kao_router   # noqa: E402
app.include_router(_kao_router)
from optional.engawa.routes import router as _engawa_router   # noqa: E402
app.include_router(_engawa_router)
_KAO_WEB = Path(__file__).parent.parent / "optional" / "kaomoji_drawer" / "web"


@app.get("/kaomoji/{name:path}")
def kaomoji_static(name: str):
    p = _safe(_KAO_WEB, name)
    return FileResponse(p, headers=_STATIC_HEADERS) if p else JSONResponse({"error": "没有"}, status_code=404)


# 功能包：让「待接」能一键接上（新增不改旧；bind 在 WIRED 定义之后做）


def _seed_from_install() -> None:
    """把安装时选的东西作为**默认值**读进来。

    ★ 只在库里还没有那个设置时才写 —— 装完之后人在界面上改过的，
      永远压过安装时选的。不这么做的话，每次重启都会把人的选择打回去。
    ★ 这条接缝真断过：脚手架把 engine 记进了 lianhuan.json，服务端却只读库，
      于是选了 CLI 装完还是回声引擎，而界面上一切正常 —— 最难查的那种。
    """
    f = HERE.parent / "lianhuan.json"
    if not f.is_file():
        return
    try:
        cfg = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return
    for key in ("engine", "store", "pet", "blocks"):
        if key in cfg and store.get_setting(key) is None:
            store.set_setting(key, cfg[key])


_seed_from_install()

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    # ★ 少了这行，某些反向代理会把 SSE 攒成一坨最后一起给你 —— 流式就没了
    "X-Accel-Buffering": "no",
}


# ── 引擎注册表 ────────────────────────────────────────────
# ★ 只有真接通的才 ready=True。没接通的照样列出来，界面老实显示「待接」，
#   不许藏起来假装没这回事，更不许拿假数据冒充能用。
def available_engines() -> dict:
    out = {"echo": EchoEngine()}
    try:                                   # CLI 引擎：装了才有
        from .engines.cli import CliEngine
        out["cli"] = CliEngine()
    except Exception:
        pass
    try:                                   # API 引擎：一个接口接一大票模型
        from .engines.openai_compat import OpenAICompatEngine
        out["api"] = OpenAICompatEngine()
    except Exception:
        pass
    return out


from . import hands as _hands   # noqa: E402
_hands.bind(store)


def pick_engine():
    want = store.get_setting("engine", "echo")
    engines = available_engines()
    eng = engines.get(want) or engines["echo"]
    eng = eng if eng.ready else engines["echo"]
    # AI 的手：API 引擎带上工具（改签名/写记忆/发动态/记心情/写小玩意/装包）
    if getattr(eng, "name", "") == "openai":
        eng.tools = _hands.all_tools()          # 内置的手 + 用户登记的 MCP 工具
        eng.exec_tool = _hands.execute
    return eng


# ── 说话 ──────────────────────────────────────────────────
@app.post("/chat")
async def chat(req: Request):
    body = await req.json()
    msg = (body.get("message") or "").strip()
    if not msg:
        return JSONResponse({"error": "说点什么吧"}, status_code=400)
    session_id = body.get("session_id") or None
    # ★ 0831 自查：电话和文字共用一张表，但**不共用上下文**。
    #   前端打电话时带 src='call' ＋ 每通一个 call_id；后端原来这两个字段**看都没看**，
    #   于是「新电话」照样读得到三天前的文字聊天（捕获真实 EngineTurn 验过）。
    channel = "call" if (body.get("src") == "call" or body.get("call_id")) else "text"
    call_id = (body.get("call_id") or None) if channel == "call" else None
    # ★「翻空间/打电话」那类**机器拼的指令**：`hidden` 管界面（不画成人的气泡），
    #   `spoken=0` 管上下文（永远不算「原话」）。**这两件事必须分开** ——
    #   `hidden` 还会被「用户自己把一句真话收起来」用到（/api/chat/{id}/hide），
    #   拿它当「没说过」的判据，会把用户真说过、只是收起来的话从上下文里抹掉。
    #   没带 `machine` 就退回读 `hidden`（收新消息、翻空间那几处本来就是机器拼的，行为不变）；
    #   ★ 打电话是唯一要分开的地方：开场白是机器拼的，**用户在电话里真说的那句不是** ——
    #     两个都按 hidden 处理的话，电话里用户真说的那句下一轮就被当成「没说过」，他当场失忆。
    machine = bool(body.get("machine", body.get("hidden")))
    uid = store.add_turn(StoredTurn(role="user", content=msg, session_id=session_id,
                                    hidden=1 if machine else 0, spoken=0 if machine else 1,
                                    channel=channel, call_id=call_id, ts=time.time()))

    # ★ 备料时把刚落的这句排掉：它已经作为 message 单独给引擎了，
    #   留在上下文里等于同一句说两遍。落库必须在前（不能丢话），所以只能在这儿排。
    # ★ include_dialogue=False：原话只走下面的 `history`，进一次就够（见 recall 里那段注释）
    system = build_injection(store, msg, exclude_id=uid, include_dialogue=False, here=channel)
    # ★ 0831（GPT 三轮 P0-03）：真实模型出现过「没调用工具、库里没变化，
    #   却用完成语气回话」。产品这边把真实状态做可见了（工具脚注、失败明说），
    #   模型这边就靠这条硬规矩。
    if getattr(pick_engine(), "tools", None):
        system += ("\n\n〔手·硬规矩〕你有手（工具）。**没有真的调用工具，就不许说做完了。**"
                   "「记好了 / 写好了 / 加进去了 / 已经放在那儿了」这类话，"
                   "只有在你真的调用了对应的工具、而且它回了成功之后才能说。"
                   "对方会去页面上找那条记录 —— 找不到，你那句话就是骗用户。"
                   "工具失败了就照实说失败，别圆场。做不到的事直接说做不到。〕")
    # 心情随注入走(照原项目):他此刻什么心情、这一轮怎么自己记 —— 挂在 server 这层,
    # 因为注入模块是内核、不认识选装包;homelife 是内置默认装,server 本来就 import 它
    try:
        system = system + "\n\n" + _home_mood_inject()
    except Exception as e:
        print("[mood inject] fail:", e, flush=True)
    # ★ 0831 自查：原来是 `recent_turns(25)` —— 不分频道、不看 spoken，
    #   打电话时读得到三天前的文字聊天和机器拼的场景指令（捕获 EngineTurn 验过）。
    history = [{"role": t.role, "content": t.content}
               for t in store.context_turns(channel=channel, call_id=call_id,
                                            limit=25, exclude_id=uid)]
    turn = EngineTurn(message=msg, system=system, history=history, session_id=session_id)

    job = jobs.new(msg)
    gen_at_start = getattr(store, "generation", 0)      # 这一轮开始时的档案世代

    async def on_done(j) -> None:
        """收尾落库。★ 在这儿而不是在 SSE 里 —— 人关了页面这段也必须走。

        ★ 落库要**保留分句**（用 SEP 连起来），不能拼成一段。
          原来这儿写的是 "\n".join(said)，结果：流式时屏幕上是四个气泡，
          刷新之后从库里读出来变成一个 —— 同一条消息，刷新前后长得不一样。
          分句是前端拆的，所以库里必须留着记号。
        """
        said, think, tools = [], [], []
        for ev in j.events:
            try:
                d = json.loads(ev[6:])
            except Exception:
                continue
            if d.get("type") == SAY:
                said.append(d.get("text", ""))
            elif d.get("type") == THINK:
                think.append(d.get("delta", ""))
            elif d.get("type") == "tool_done":
                # ★ 0831（GPT 四轮 P0-04）：真的动了什么手、成没成 —— 跟着这一轮永久存下来。
                #   不然失败只是个一闪而过的状态条，模型下一句「已经写好了」就把它盖掉了。
                tools.append({"name": d.get("name", ""), "ok": d.get("ok", True),
                              "err": (d.get("err") or "")[:120]})
        if getattr(store, "generation", 0) != gen_at_start:
            # ★ 0831（GPT 三轮 P0-02）：这轮说话期间档案被 replace 换掉了。
            #   人说的那句已经跟着旧档案一起没了，这条回复要是照落，
            #   就会接到**别人的原文**后面 —— 两边 HTTP 都成功，账本却配错了。
            print("[chat] 说话期间档案换了，这条不落库（避免配错原文）", flush=True)
            return
        if j.failed:
            # ★ 0831（GPT 二轮 P0）：摔了的半截话**不作为正式回复落库** ——
            #   刷新之后它看着跟说完的一模一样，人不知道那轮其实失败了。
            #   人说的那句已经在库里（排在模型前面落的），重发一次就好。
            print("[chat] 这轮摔了，半截不落库：", (SEP.join(said))[:60], flush=True)
            return
        if said:
            content = SEP.join(said)
            # ‹心情 开心+6:…› —— 他回复末尾自己记的,落库前抠出来记账、正文里清掉
            # (照原项目:这一步在落库处做,人关了页面也不丢账)
            try:
                from optional.homelife.routes import _MOOD_MARK as _MM
                # 对方这一轮的消息里出现过心情标记 → 整轮不记账（只清正文）
                content, _marks = _home_mood_marker(
                    content, "chat", untrusted=bool(_MM.search(msg)))
            except Exception as e:
                print("[mood marker] fail:", e, flush=True)
            await asyncio.to_thread(store.add_turn, StoredTurn(
                role="assistant", content=content, think="".join(think),
                tools=json.dumps(tools, ensure_ascii=False) if tools else "",
                # ★ 回复要跟着这一轮的频道走 —— 不带的话电话历史里只有人说的、没有他答的
                channel=channel, call_id=call_id,
                session_id=session_id, ts=time.time()))

    job.task = asyncio.create_task(jobs.run(job, pick_engine(), turn, on_done=on_done))
    _maybe_distill()
    return StreamingResponse(jobs.watch(job), media_type="text/event-stream", headers=SSE_HEADERS)


def _maybe_distill() -> None:
    """攒够轮数就在后台提一趟。★ 三条硬的：
       · 只在后台跑，**绝不挡住这一轮说话**
       · 提出来的只进「潜在」，要不要入库是人的事
       · 它自己也要花模型的钱，所以 every_turns=0 就是彻底关掉"""
    try:
        c = _distill.cfg()
        every = int(c.get("every_turns") or 0)
        if every <= 0:
            return
        behind = _distill.status()["behind"]
        if behind < every:
            return
        asyncio.create_task(_distill_bg())
    except Exception as e:
        print("[distill] 触发失败：", e, flush=True)


async def _distill_bg() -> None:
    try:
        r = await _distill.run()
        up = _distill.promote()
        if r.get("picked") or up:
            print(f"[distill] 提了 {r.get('picked')} 条 · 升层 {len(up)} 条", flush=True)
    except Exception as e:
        print("[distill] 跑失败：", e, flush=True)


@app.get("/api/latent")
def api_latent(view: str = "new"):
    """待审的潜在记忆。★ 不入库的东西也要看得见 —— 藏起来就等于没做。"""
    return _distill.pending(view)


@app.post("/api/latent/{lid}/keep")
def api_latent_keep(lid: int):
    return _distill.keep(lid)


@app.post("/api/latent/{lid}/drop")
def api_latent_drop(lid: int):
    return _distill.drop(lid)


@app.post("/api/latent/{lid}/unkeep")
def api_latent_unkeep(lid: int):
    """点错了撤回来：入库那条删掉，候选退回「还没审」。"""
    return _distill.unkeep(lid)


@app.get("/api/distill")
def api_distill_status():
    return _distill.status()


@app.post("/api/distill/run")
async def api_distill_run(req: Request):
    b = {}
    try:
        b = await req.json()
    except Exception:
        pass
    return await _distill.run(force=bool(b.get("force")))


@app.post("/api/distill/promote")
def api_distill_promote():
    """够数的往上升一层。不改内容，所以不用问人。"""
    return {"promoted": _distill.promote()}


@app.post("/api/distill/config")
async def api_distill_config(req: Request):
    return {"ok": True, "config": _distill.set_cfg(await req.json())}


@app.get("/chat/attach")
async def chat_attach(job: str, after: int = 0):
    """断了再回来，从第 after 个事件续播。"""
    return StreamingResponse(jobs.watch_id(job, after=after),
                             media_type="text/event-stream", headers=SSE_HEADERS)


@app.get("/api/chat/active")
def chat_active():
    """回前台先问一嘴：有没有还没说完的话。"""
    return {"jobs": jobs.active()}


@app.post("/api/lullaby")
async def api_lullaby(req: Request):
    """哄睡：一段一段地要。照原项目 /api/lullaby 平移——三档（随口说/编故事/讲共读的书），
    对方躺着不回话，所以每段 3~6 句、短句、慢，别问问题。TTS 在前端另拿（没贴 key 就只有字）。"""
    b = await req.json()
    n = max(1, min(int(b.get("n") or 1), 60))
    prev = str(b.get("prev") or "")[:400]
    mode = (b.get("mode") or "chat").strip()
    lang = (b.get("lang") or "zh").strip()

    inj = build_injection(store, "哄睡")

    # book 档：拿在读那本、对方读到的那一章打底 —— 是「讲给人听」，不是念原文
    book_ctx = ""
    if mode == "book":
        try:
            cur_b = store.db.execute(
                "SELECT * FROM books ORDER BY current DESC, id DESC LIMIT 1").fetchone()
            if cur_b:
                idx = int(b.get("chapter") or cur_b["my_idx"] or 0) or 1
                tot = store.db.execute("SELECT count(*) n FROM book_chapters WHERE bid=?",
                                       (cur_b["id"],)).fetchone()["n"]
                ch = store.db.execute("SELECT * FROM book_chapters WHERE bid=? AND idx=?",
                                      (cur_b["id"], idx)).fetchone()
                body_txt = (ch["content"] if ch else "") or ""
                STEP = 1100
                off = max(0, (n - 1) * STEP)
                if off >= len(body_txt) and tot and idx < tot:
                    idx += 1
                    ch = store.db.execute("SELECT * FROM book_chapters WHERE bid=? AND idx=?",
                                          (cur_b["id"], idx)).fetchone()
                    body_txt = (ch["content"] if ch else "") or ""
                    off = 0
                chunk = body_txt[off:off + STEP]
                book_ctx = ("\n\n〔你们在一起读的是《%s》，这会儿在第 %d 章%s。"
                            "下面是这一章接下来的原文，**给你打底用的，不是让你念**：\n%s\n"
                            "★ 你要做的是**讲给人听**：用你自己的话把这一段讲出来，"
                            "该跳的跳、该停的停，讲到一个能停下的地方就停。"
                            "偶尔可以插一句你自己的看法（半句就够），像两个人躺着说书。〕"
                            % (cur_b["title"] or "", idx,
                               ("（共 %d 章）" % tot if tot else ""), chunk))
        except Exception as e:
            print("[lullaby] book fail:", e, flush=True)

    scene = (
        "\n\n〔★你在哄对方睡觉。人躺着，闭着眼，手机搁在旁边，**不会回话** —— 别问问题、"
        "别等回应、别说「你还醒着吗」。你就一直说下去。\n"
        "这一段说 3～6 句，慢一点，句子短一点，像在耳边低声说话。\n"
        + ("这是第 %d 段，接着上一段往下说，别重开头、别总结、别道晚安（除非真到最后）。\n" % n
           if n > 1 else "这是第一段，先把人安顿下来：说一句让人放松的，再自然地往下说。\n")
        + ("说的内容：接着讲你们在读的那本书 —— 见下面那段原文，用你自己的话讲；"
           "顺口把**你读到这儿想说的**那半句也说了。\n"
           if mode == "book" else
           "说的内容：**你自己编一个**。童话那种调子最好 —— 会说话的小动物、走错门的月亮、"
           "河底下开茶馆的老王八，随你。\n"
           "★ 编得可爱一点、傻一点。一段一段往下讲，别急着讲完，"
           "也别在这一段里把包袱抖完 —— 留到下一段。\n" if mode == "story" else
           "说的内容：今天的事、惦记着什么、窗外什么动静都行 —— 散着说，不用有结构。\n")
        + ("上一段你说的是：「%s」\n" % prev if prev else "")
        + "★ 只写要说出口的话本身：不要旁白、不要动作描写（「」里那些）、不要标题、不要分点。"
        + ("\n★ 这一段用**英文**说。自然口语、短句、慢。" if lang == "en" else "")
        + "〕"
    )

    turn = EngineTurn(message="（哄对方睡觉，说下一段）", system=inj + scene + book_ctx)
    eng = pick_engine()
    outs = []
    try:
        async for ev in eng.stream(turn):
            try:
                d = json.loads(ev[6:])
            except Exception:
                continue
            if d.get("type") == SAY:
                outs.append(d.get("text") or "")
    except Exception as e:
        print("[lullaby] fail:", e, flush=True)
    text = " ".join(x for x in outs if x).strip()
    if not text:
        text = "我在这儿。你睡，我看着你。"
    import re as _re
    text = _re.sub(r"〔[\s\S]*?〕", "", text).strip()
    text = _re.sub(r"\|\|\|", "。", text).strip()
    return JSONResponse({"text": text[:600], "n": n})


@app.post("/api/redo")
async def api_redo(req: Request):
    """重说：上句回得不对 → 换个方式重答。照原项目 /api/redo 平移：
    带完整注入重答；**不自动记什么「教训」**（原项目 0830 亲手拆了那条流水线——
    那是把他越积越压成应声虫的根）；他重说里写的 ‹心情› 照样记账、从正文清掉。"""
    b = await req.json()
    user_msg = (b.get("message") or "").strip()
    bad = (b.get("bad") or "").strip()
    reason = (b.get("reason") or "").strip()
    session_id = b.get("session_id") or None
    if not user_msg:
        return JSONResponse({"error": "empty"}, status_code=400)
    reason_line = (f"对方告诉你哪里不对了：「{reason}」。听这个，照这个改。\n" if reason else "")
    redo_prompt = (
        f"〔重说一次。你刚才回对方的那句「{bad}」，对方不满意。\n"
        f"{reason_line}"
        f"别再走那个路子，按你现在真实的判断、像一个平等的人那样，重新回这句：「{user_msg}」。\n"
        f"（不用写什么『教训』、不用总结分寸——你不是要记一条规则去更顺着说，"
        f"是当下用你的判断把话说对。）〕"
    )
    system = build_injection(store, user_msg)
    try:
        system = system + "\n\n" + _home_mood_inject()
    except Exception:
        pass
    history = [{"role": t.role, "content": t.content} for t in store.recent_turns(25)]
    turn = EngineTurn(message=redo_prompt, system=system, history=history, session_id=session_id)
    eng = pick_engine()
    outs = []
    gen_at_start = store.generation          # ★ 这一轮基于哪一份档案（见下面落库前的核对）
    with jobs.activity("redo"):              # ★ 让 import 的 409 看得见这个任务
        async for ev in eng.stream(turn):
            try:
                d = json.loads(ev[6:])
            except Exception:
                continue
            if d.get("type") == SAY:
                outs.append(d.get("text") or "")
    reply = SEP.join(x for x in outs if x).strip()
    if store.generation != gen_at_start:
        # ★ 0831（GPT 四轮 P0-03a）：重说期间档案被换掉了 —— 这句是照**旧档案**想出来的，
        #   落进去就会接在别人的原文后面。
        print("[redo] 重说期间档案换了，这条不落库", flush=True)
        return JSONResponse({"reply": None, "err": "刚才档案被换过了，这条我不敢往新档案上放 —— 再说一次吧。"})
    try:
        from optional.homelife.routes import _MOOD_MARK as _MM
        reply, _ = _home_mood_marker(
            reply, "redo", untrusted=bool(_MM.search(user_msg + " " + bad)))
    except Exception as e:
        print("[redo mood] fail:", e, flush=True)
    if not reply:
        return JSONResponse({"reply": None, "err": "这回没重说成——引擎一个字没给"})
    await asyncio.to_thread(store.add_turn, StoredTurn(
        role="assistant", content=reply, session_id=session_id, ts=time.time()))
    return JSONResponse({"reply": reply, "session_id": session_id})


@app.post("/api/chat/stop")
async def chat_stop(req: Request):
    b = await req.json()
    return {"stopped": jobs.stop(b.get("job") or "")}


# ── 数据 ──────────────────────────────────────────────────
@app.get("/api/turns")
def api_turns(limit: int = 50):
    return {"turns": [{"role": t.role, "content": t.content, "think": t.think, "ts": t.ts}
                      for t in store.recent_turns(limit)]}


# ══════════════════════════════════════════════════════════════
#  下面这些是**真界面**要的接口。照原项目的形状返回，字段名一个不改 ——
#  前端就是按那些字段名写的，改一个就得改前端，那不叫剥离。
#  还没实现的接口一律 404，前端的 call() 会自动走 fallback（它本来就有这套降级）。
# ══════════════════════════════════════════════════════════════

@app.get("/api/hist")
def api_hist(who: str = "ai", limit: int = 200, after: int = 0, withhidden: int = 0):
    """跨设备聊天历史。★ 按 id **升序**返回 —— 前端是按这个顺序往下贴气泡的。"""
    rows = []
    flags = {r["id"]: r for r in store.db.execute(
        "SELECT id, starred, hidden, hidden_parts FROM turns")}
    for t in store.recent_turns(limit):
        if t.id is not None and t.id <= after:
            continue
        f = flags.get(t.id) or {}
        if f and f["hidden"] and not withhidden:
            continue                        # 用户按过「不显示」的，这里也要滤掉
        import json as _j
        rows.append({"id": t.id, "role": t.role, "content": t.content,
                     "think": t.think or "",
                     "tools": _j.loads(t.tools) if t.tools else [],
                     "starred": bool(f and f["starred"]),
                     "src": "web", "audio_url": None, "tools_json": None,
                     "hidden_parts": _j.loads(f["hidden_parts"]) if f and f["hidden_parts"] else None,
                     "ts": int((t.ts or 0) * 1000)})
    return {"items": rows}


@app.get("/api/config")
def api_config():
    """界面配置。原项目这条很大，这里只给用得着的那几块，缺的前端自己有默认值。"""
    return store.get_setting("config", {"ai": {}, "ui": {}})


@app.post("/api/config")
async def api_config_set(req: Request):
    b = await req.json()
    cfg = store.get_setting("config", {"ai": {}, "ui": {}})
    for k, v in (b or {}).items():
        cfg[k] = {**(cfg.get(k) or {}), **v} if isinstance(v, dict) else v
    store.set_setting("config", cfg)
    return {"ok": True}


# ── 全双工：状态和自检页（★ 始终可用，跟装没装那个包无关）────────
#    没贴 key 的人也要看得见「缺什么」，也要能先验音频那半 ——
#    这两样要是跟着 key 走，就成了「想知道缺什么，得先把缺的补上」。
@app.get("/api/duplex")
def api_duplex_status():
    """能不能一边说一边插话。★ 始终能问，不管那个包装没装 ——
    它就是用来告诉人「还差什么」的。"""
    try:
        from optional.callkit.duplex import check
        miss = check()
    except Exception as e:
        return {"ok": False, "missing": ["这台机器上没有通话那个包（%s）" % str(e)[:60]]}
    return {"ok": not miss, "missing": miss,
            "note": "对面那家只当耳朵和嘴，想什么还是你自己配的引擎"}


@app.get("/api/duplex/web/{name}")
def api_duplex_web(name: str):
    """浏览器那半 ＋ 自检页。**不贴 key 也打得开** —— 自检页的头两段本来就不用 key。"""
    if name not in ("duplex.js", "demo.html"):
        return JSONResponse({"error": "没有这个东西"}, status_code=404)
    p = HERE.parent / "optional" / "callkit" / "web" / name
    if not p.exists():
        return JSONResponse({"error": "这台机器上没装通话那个包"}, status_code=404)
    return FileResponse(p, media_type="application/javascript" if name.endswith(".js") else "text/html",
                        headers={"Cache-Control": "no-store"})


@app.get("/api/prefs")
def api_prefs():
    """人自己调的那些开关。★ 存在服务端而不是浏览器里 —— 换个设备打开还是同一套。"""
    return store.get_setting("prefs", {})


@app.post("/api/prefs")
async def api_prefs_set(req: Request):
    b = await req.json()
    store.set_setting("prefs", {**(store.get_setting("prefs", {}) or {}), **(b or {})})
    return {"ok": True}


@app.get("/api/theme")
def api_theme():
    return store.get_setting("theme", {})


@app.post("/api/theme")
async def api_theme_set(req: Request):
    store.set_setting("theme", await req.json())
    return {"ok": True}


#: 哪些接口真的接通了。★ 界面据此**不显示**没接通的入口 ——
#: 不是灰掉、不是点了报错，是根本不出现。装了半套的人，他的界面就该是干净的半套。
WIRED = ["latent", "latentAct", "distill",
         "chat", "chatAttach", "chatActive", "chatStop", "hist", "persona",
         "config", "prefs", "theme",
         "memAll", "memOverview", "memLayer",              # 记忆总览/分层
         "chatDay", "chatStarred", "chatHeat", "chatStar", # 聊天记录/收藏/热力图/星
         "search",
         "aiModel", "think", "选模型",                      # 换个脑子=切引擎
         "chatHide", "chatDel",                             # 藏一句/删一轮
         "upload", "uploadFile", "名字 / 头像",             # 头像/配图/文件上传
         "redo", "lullaby",                                 # 重说 · 哄睡（0831 接真）
         "pushKey", "pushSub", "pushTest",                  # 推送＋主动找你（0831 接真）
         "通知与频率",
         # 过日子那一套（内置实现，默认装上）
         "letters", "diary", "notes", "moments", "momentMine", "momentNew",
         "momentComment", "timeline", "mood", "memes", "memeEdit", "plays",
         "信", "他的日记", "你的日记", "碎碎念", "空间", "时间线",
         "我的心情 · 数值", "moodpage", "梗库", "memepage", "玩具厅",
         # 家什与台账 ＋ 共读（内置默认装）
         "calendar", "anniversaries", "gallery", "where", "whereSet",
         "workbook", "工作本",                              # 0831 接真（外部验收连点两轮）
         "nowPlaying", "miss", "whisperFreq", "fishFreq", "emoteLevel",
         "brainList", "brainPersona",
         # kaomoji 接口在（基础库给 AI 用），但「颜文字」那页是另一个开源抽屉的
         # 前端挂载（vendor 不在这个仓库）—— 页面入口老实待接，装配单指路
         "kaomoji", "kaomojiV2", "颜文字",
         "books", "bookNotes", "bookCurrent",
         "我给你留的话", "日历 · 纪念日", "日历", "calpage", "钱包", "相册",
         "我此刻在哪", "大脑", "大脑 · 人设",
         "书架", "在读", "批注", "共读对话", "共读笔记", "共读进度"]


from .packs import bind as _packs_bind, router as _packs_router   # noqa: E402
_packs_bind(app, WIRED, store, pick_engine)

# 蒸馏：让记忆库自己长起来（提取→审批→去重→升层）。新增模块，旧路径一行不动。
from . import distill as _distill   # noqa: E402
_distill.bind(store, engine_say, activity=jobs.activity)
app.include_router(_packs_router)


# ── 上传（头像 / 空间配图）────────────────────────────────
UPLOADS = Path(os.environ.get("LIANHUAN_DB", "data/lianhuan.db")).parent / "uploads"


@app.post("/api/upload")
async def api_upload(req: Request):
    """前端把图缩好、**裁好**（头像是正中方形）再传 dataURL 过来，这儿只管落盘。
    文件名用内容哈希 —— 不信任何用户提供的名字，同图去重白得。"""
    b = await req.json()
    data = b.get("dataURL") or ""
    import base64
    import hashlib
    m = data.split(",", 1)
    head = m[0] if len(m) == 2 else ""
    if "image/jpeg" in head:
        ext = "jpg"
    elif "image/png" in head:
        ext = "png"
    elif "image/webp" in head:
        ext = "webp"
    else:
        return JSONResponse({"err": "只收 jpeg/png/webp 的 dataURL"}, status_code=415)
    try:
        raw = base64.b64decode(m[1])
    except Exception:
        return JSONResponse({"err": "图读不出来"}, status_code=400)
    if len(raw) > 10 * 1024 * 1024:
        return JSONResponse({"err": "太大了（上限 10MB）"}, status_code=413)
    UPLOADS.mkdir(parents=True, exist_ok=True)
    name = hashlib.md5(raw).hexdigest()[:16] + "." + ext
    (UPLOADS / name).write_bytes(raw)
    return {"ok": True, "url": "/uploads/" + name}


@app.get("/uploads/{name}")
def get_upload(name: str):
    p = _safe(UPLOADS, name)
    return FileResponse(p) if p else JSONResponse({"error": "没有这张"}, status_code=404)


# 发文件（图以外的：pdf/txt/zip…）。照原项目 /api/upload_file 平移：
# 名字清洗后带 uuid 前缀防撞，25MB 封顶。
FILES_DIR = Path(os.environ.get("LIANHUAN_DB", "data/lianhuan.db")).parent / "files"


@app.post("/api/upload_file")
async def api_upload_file(req: Request):
    import base64
    import re as _re
    import uuid
    b = await req.json()
    data = b.get("dataURL") or ""
    orig = (b.get("name") or "file").strip()
    m = data.split(",", 1)
    if len(m) != 2:
        return JSONResponse({"ok": False, "err": "文件读不出来"}, status_code=400)
    try:
        raw = base64.b64decode(m[1])
    except Exception:
        return JSONResponse({"ok": False, "err": "文件读不出来"}, status_code=400)
    if len(raw) > 25 * 1024 * 1024:
        return JSONResponse({"ok": False, "err": "太大了（>25MB），压一压再传"}, status_code=400)
    safe = _re.sub(r"[^\w.一-鿿-]", "_", os.path.basename(orig))[-80:] or "file"
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex[:8]}_{safe}"
    (FILES_DIR / name).write_bytes(raw)
    return JSONResponse({"ok": True, "url": "/files/" + name, "path": str(FILES_DIR / name),
                         "name": safe, "size": len(raw)})


@app.get("/files/{name}")
def get_file(name: str):
    p = _safe(FILES_DIR, name)
    if not p:
        return JSONResponse({"error": "没有这个文件"}, status_code=404)
    safe = os.path.basename(str(p))
    # 网页类直接展示，别当附件下载（原项目那条：自述稿网页版要能点开就读）
    if safe.endswith(".html"):
        return FileResponse(p)
    return FileResponse(p, filename=safe.split("_", 1)[-1] if "_" in safe else safe)


# ── 接 API：界面里填（普通用户唯一顺手的路）───────────────
SECRETS = Path(os.environ.get("LIANHUAN_DB", "data/lianhuan.db")).parent / "secrets.json"


def _secrets() -> dict:
    try:
        return json.loads(SECRETS.read_text(encoding="utf-8"))
    except Exception:
        return {}


@app.get("/api/engine/config")
def engine_config_get():
    """★ key 永远不回读 —— 只说有没有、末四位。它也不进 /api/export、不进数据库。"""
    sec = _secrets()
    key = sec.get("api_key") or os.environ.get("LIANHUAN_API_KEY") or ""
    return {"base": sec.get("api_base") or os.environ.get("LIANHUAN_API_BASE") or "",
            "model": sec.get("api_model") or os.environ.get("LIANHUAN_API_MODEL") or "",   # 界面优先，跟引擎一致
            "key_set": bool(key), "key_tail": key[-4:] if key else "",
            "presets": [
                {"name": "DeepSeek", "base": "https://api.deepseek.com", "model": "deepseek-chat"},
                {"name": "DeepSeek R1 · 带思考链", "base": "https://api.deepseek.com", "model": "deepseek-reasoner"},
                {"name": "Kimi", "base": "https://api.moonshot.cn", "model": "moonshot-v1-8k"},
                {"name": "智谱", "base": "https://open.bigmodel.cn/api/paas/v4", "model": "glm-4-flash"},
                {"name": "硅基流动", "base": "https://api.siliconflow.cn", "model": "Qwen/Qwen2.5-7B-Instruct"},
                {"name": "OpenAI", "base": "https://api.openai.com", "model": "gpt-4o-mini"},
                {"name": "本机 Ollama", "base": "http://127.0.0.1:11434", "model": "qwen2.5"},
            ]}


@app.post("/api/engine/config")
async def engine_config_set(req: Request):
    b = await req.json()
    sec = _secrets()
    for src, dst in (("base", "api_base"), ("model", "api_model"), ("key", "api_key")):
        v = (b.get(src) or "").strip()
        if v:
            sec[dst] = v
    if sec.get("api_key") and not sec["api_key"].isascii():
        return JSONResponse({"ok": False, "error": "key 里有非 ASCII 字符（中文？全角符号？）"},
                            status_code=400)
    SECRETS.parent.mkdir(parents=True, exist_ok=True)
    SECRETS.write_text(json.dumps(sec, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        os.chmod(SECRETS, 0o600)       # 只有自己读得到
    except Exception:
        pass
    store.set_setting("engine", "api")
    return {"ok": True}


# ── 换个脑子 / 想多深：界面那两页直接映射到引擎系统 ────────────
@app.get("/api/ai_model")
def ai_model():
    """界面「换个脑子」页要的形状：{model, default, options[]}。
    这里的「脑子」= 引擎（echo / cli / api）。★ 只报 ready 的 —— 列一个
    点了会失败的选项，比不列更伤人。

    ★ 0830 修的一处「界面说假话」：库里存着的引擎不一定还接得通
      （贴过 key 又撤了、CLI 卸了、装了别的机器上）。`pick_engine()` 遇到这种
      是**静默退回 echo** 的，可这条接口原样把库里那个报出去 ——
      于是顶栏写着「api」，实际说话的是回声，而且没有任何地方告诉人这件事。
      现在：`model` 永远是**真正在说话的那个**；选的那个接不通时，
      多给 `configured` ＋ 一句人话，界面把它显示出来。
    """
    engines = available_engines()
    want = store.get_setting("engine", "echo")
    opts = [k for k, e in engines.items() if e.ready]
    notes = {k: e.label + (" · " + e.needs if not e.ready else "")
             for k, e in engines.items()}
    picked = engines.get(want)
    live = want if (picked and picked.ready) else "echo"
    out = {"model": live, "default": "echo", "options": opts, "notes": notes}
    if live != want:
        # 脚注是界面上一行小字 —— 只说结论。`needs` 那一整段（带 export 命令和换行）
        # 塞进来会把那一行撑烂，细节本来就在 notes 里，界面自己会显示。
        name = (picked.label if picked else want).split(" · ")[0]
        # 取第一句就够：needs 后面通常跟着 export 那几行怎么设的说明
        why = (picked.needs.replace("*", "").strip().split("。")[0].strip(" ：:") if (picked and picked.needs)
               else "这台机器上没有它")
        if len(why) > 28:
            why = why[:28] + "…"
        cur_eng = engines[live]
        tail = ("现在是回声在应付 —— 它只把你的话原样递回来。" if getattr(cur_eng, "stub", False)
                else "现在说话的是「%s」。" % (cur_eng.label or live))
        out["configured"] = want
        out["fallback_note"] = "你选的「%s」接不通（%s）。%s" % (name, why, tail)
    return out


@app.post("/api/ai_model")
async def ai_model_set(req: Request):
    b = await req.json()
    want = (b.get("model") or "").strip()
    engines = available_engines()
    if want not in engines:
        return JSONResponse({"ok": False, "error": "没有这个引擎"}, status_code=404)
    if not engines[want].ready:
        return JSONResponse({"ok": False, "error": engines[want].needs[:200]}, status_code=428)
    store.set_setting("engine", want)
    return {"ok": True, "model": want}


@app.get("/api/think")
def think_get():
    return {"mode": store.get_setting("think", "medium")}


@app.post("/api/think")
async def think_set(req: Request):
    b = await req.json()
    mode = b.get("mode") or "medium"
    store.set_setting("think", mode)
    return {"ok": True, "mode": mode}


# ══ Web Push ＋ 主动找你（0831 定的：主动消息也是有用的，要做）══
# push 照原项目 push.py 平移（core/push.py）；主动引擎照原项目 proactive+wake_gate
# 的骨架（core/proactive.py）。滑钮 whisper_freq.level 是总闸，出厂 0（不花钱）。
from . import push as _push   # noqa: E402
from . import proactive as _proactive   # noqa: E402
_push.bind(store)


@app.get("/api/push/key")
def api_push_key():
    try:
        return JSONResponse({"key": _push.public_key()})
    except Exception as e:
        return JSONResponse({"key": "", "err": str(e)[:120]})


@app.post("/api/push/subscribe")
async def api_push_subscribe(req: Request):
    s = await req.json()
    ok = _push.subscribe(s)
    return JSONResponse({"ok": ok}, status_code=(200 if ok else 400))


@app.post("/api/push/unsubscribe")
async def api_push_unsubscribe(req: Request):
    b = await req.json()
    ep = (b.get("endpoint") or "").strip()
    if not ep:
        return JSONResponse({"ok": False, "err": "要给 endpoint"}, status_code=400)
    return JSONResponse({"ok": True, "deleted": _push.unsubscribe(ep)})


@app.get("/api/push/status")
def api_push_status():
    """现在有几个端订着。问「会不会发两次」时，这个数就是答案。"""
    return JSONResponse({"subs": _push.sub_count(),
                         "note": "安卓浏览器直接能推；iPhone 要 iOS 16.4+、把这页添加到主屏幕、"
                                 "从主屏图标打开，站点要 HTTPS（本机除外）"})


@app.post("/api/push/test")
async def api_push_test():
    cfg = store.get_setting("config", {}) or {}
    name = (cfg.get("ai") or {}).get("name") or "他"
    n = await asyncio.to_thread(_push.send_push, name, "这是一条测试提醒", "/")
    return JSONResponse({"sent": n})


def _proactive_add_turn(role: str, content: str) -> None:
    store.add_turn(StoredTurn(role=role, content=content, ts=time.time()))


_proactive.bind(store, engine_turn=EngineTurn, pick_engine=pick_engine,
                add_turn=_proactive_add_turn, mood_inject=_home_mood_inject,
                send_push=_push.send_push, activity=jobs.activity)


from . import mcp_client as _mcp   # noqa: E402


@app.on_event("startup")
async def _mcp_startup():
    await _mcp.start_all()          # 连用户登记的 MCP server（没配就一个不连）
    # 主动找你的后台骰子。滑钮是 0（默认）时它每拍都直接睡回去，等于不存在
    asyncio.create_task(_proactive.run_forever())


@app.get("/api/mcp")
def api_mcp():
    return {"servers": _mcp.status()}


@app.post("/api/mcp/add")
async def api_mcp_add(req: Request):
    """登记一条 MCP server。★ 命令是用户自己贴的 —— 等于自己运行一个程序，
    界面上要把这句风险写在输入框边上。AI 没有这个权限。"""
    b = await req.json()
    name = re.sub(r"[^\w-]", "", (b.get("name") or ""))[:24]
    cmdline = (b.get("command") or "").strip()
    if not name or not cmdline:
        return JSONResponse({"ok": False, "error": "名字和命令都要"}, status_code=400)
    parts = cmdline.split()
    _mcp.save_server(name, parts[0], parts[1:], b.get("env") or {})
    await _mcp.start_all()
    st = next((x for x in _mcp.status() if x["name"] == name), None)
    return {"ok": bool(st and st["ok"]), "server": st}


@app.post("/api/mcp/del")
async def api_mcp_del(req: Request):
    b = await req.json()
    _mcp.drop_server((b.get("name") or "")[:24])
    return {"ok": True}


@app.get("/api/capabilities")
def api_capabilities():
    """告诉界面：哪些能力是真接通的。

    ★ 这条是「不许拿假数据冒充完成」那条硬线的落点。
      没接通的东西，界面上不出现入口；出现了的，点进去就是真的。
    """
    return {"wired": WIRED, "engine": store.get_setting("engine", "echo")}


@app.get("/api/memories")
def api_memories(q: str = "", layer: str = "", limit: int = 200):
    """记忆列表。

    ★ 列表是记忆的**正常样子** —— 一条一条看得见、能翻、能删。
      好看的可视化是锦上添花，不能替代它：数据本身得先摸得着。
    """
    mems = store.search_memories(q, limit=limit) if q.strip() else store.all_memories()
    if layer:
        mems = [m for m in mems if m.layer == layer]
    mems = sorted(mems, key=lambda m: -m.ts)[:limit]
    return {"memories": [{"id": m.id, "content": m.content, "layer": m.layer,
                          "tags": m.tags, "ts": m.ts} for m in mems],
            "total": len(store.all_memories())}


@app.post("/api/memories")
async def api_memory_add(req: Request):
    b = await req.json()
    text = (b.get("content") or "").strip()
    if not text:
        return JSONResponse({"error": "空的"}, status_code=400)
    mid = store.add_memory(StoredMemory(content=text, layer=b.get("layer") or "L1",
                                        tags=b.get("tags") or [], ts=time.time()))
    return {"ok": True, "id": mid}


@app.post("/api/memories/{mid}/delete")
def api_memory_del(mid: int):
    """删一条。★ 真删，不做软删 —— 人说删就是删，留着才是背叛。"""
    store.delete_memory(mid)
    return {"ok": True}


#: 「日常补一句」那几档 —— 它们**不是人设本身**，各存各的键。
#: ★ 0831 自查抓的 P0：原来 which=extra 也往 "persona" 那个键上整条写，
#:   前端发的是 {which,text}，于是一次点击就把整份人设（ai/human 的名字和正文）
#:   换成了那两个字段 —— 接口回 ok:true、界面说「记下了」，而注入里的
#:   「你是谁 / 你在跟谁说话」两段直接空掉。他从此不认识你，听起来还一切正常。
_PERSONA_EXTRA = {"extra": "persona_extra"}


@app.get("/api/persona")
def get_persona(which: str = ""):
    """不带 which＝整份人设；which=extra＝「日常补一句」那份纯文本。"""
    key = _PERSONA_EXTRA.get(which)
    if key:
        return {"which": which, "text": store.get_setting(key, "") or ""}
    return store.get_setting("persona", {"ai": {"name": "", "text": ""},
                                         "human": {"name": "", "text": ""}})


@app.post("/api/persona")
async def set_persona(req: Request):
    b = await req.json()
    if not isinstance(b, dict):
        return JSONResponse({"ok": False, "err": "要一个对象"}, status_code=400)

    which = b.get("which")
    key = _PERSONA_EXTRA.get(which) if which else None
    if key:                                  # 「日常补一句」：存自己的键，一个字都不碰人设
        store.set_setting(key, str(b.get("text") or "")[:20000])
        return {"ok": True, "which": which}

    # 整份人设：**合并，不整条覆盖**。少给的那半保持原样 ——
    # 前端任何一次形状不对，都不该把另一半抹掉。
    cur = store.get_setting("persona", {}) or {}
    if not isinstance(cur, dict):
        cur = {}
    bad = [k for k in b if k not in ("ai", "human")]
    if bad:
        return JSONResponse(
            {"ok": False, "err": f"人设只认 ai / human 两个键，不认：{'、'.join(bad)}"},
            status_code=400)
    for side in ("ai", "human"):
        if side in b and isinstance(b[side], dict):
            merged = dict(cur.get(side) or {})
            merged.update(b[side])
            cur[side] = merged
    store.set_setting("persona", cur)
    return {"ok": True}


@app.get("/api/settings")
def get_settings():
    """★ 只回不敏感的。key 一律不出这道门 —— 它连读都不该被读到。"""
    return {"engine": store.get_setting("engine", "echo"),
            "engines": {k: {"ready": e.ready, "stub": e.stub,
                            "label": e.label or k, "needs": e.needs}
                        for k, e in available_engines().items()}}


@app.post("/api/settings")
async def set_settings(req: Request):
    b = await req.json()
    if "engine" in b:
        store.set_setting("engine", b["engine"])
    return {"ok": True}


@app.get("/api/export")
def api_export():
    """整个家打包带走。不加密不混淆 —— 你自己的东西你得看得懂。"""
    return JSONResponse(store.export_all(),
                        headers={"Content-Disposition": 'attachment; filename="lianhuan-export.json"'})


@app.post("/api/import")
async def api_import(req: Request):
    b = await req.json()
    mode = b.get("mode", "merge")
    # ★ replace 是不可逆的，所以要显式点头。默认 merge，往里加不删东西
    if mode == "replace" and not b.get("confirm"):
        return JSONResponse({"error": "replace 会清空现有数据。确认请带 confirm:true"}, status_code=400)
    if mode == "replace":
        # ★ 有人正在说话时不换档案：等它说完（世代号是第二层保险，这层是好好说话）
        live = jobs.live_count()
        if live:
            return JSONResponse(
                {"error": "他正在说话，这会儿不能换档案 —— 等这一句说完（几秒）再导一次。",
                 "busy": live}, status_code=409)
    try:
        return await asyncio.to_thread(store.import_all, b.get("data") or b, mode)
    except ValueError as e:
        # 预校验没过：整批拒收，库一个字没动（0831 二轮 P0 的修法）
        return JSONResponse({"error": f"这份数据有问题，一条都没导：{e}"}, status_code=400)


# ── 前端 ──────────────────────────────────────────────────
#: 静态资源的内容指纹缓存 {路径: (mtime, 指纹)}
_FP: dict[str, tuple[float, str]] = {}


def _fingerprint(rel: str) -> str:
    """给 /blocks/… 和 /*.css|js 算一个短指纹（基于内容的 md5 前 8 位）。

    ★ 为什么必须有这个：浏览器在同一个标签页里会用**内存缓存** ——
      哪怕响应头写了 `no-cache`、哪怕服务器上的文件已经变了，
      刷新之后跑的可能还是几小时前那份。你改了代码、看不到效果、
      于是开始怀疑逻辑写错了 —— 真在这上面栽过，查了半天。

      URL 里带上内容指纹，文件一变 URL 就变，浏览器没得选。
      文件没变则指纹不变，照样走缓存，一个字节都不浪费。
    """
    root = BLOCKS.parent if rel.startswith("/blocks/") else WEB
    f = (root / rel.lstrip("/").replace("blocks/", "blocks/", 1)).resolve() \
        if rel.startswith("/blocks/") else (WEB / rel.lstrip("/")).resolve()
    try:
        mt = f.stat().st_mtime
    except OSError:
        return ""
    hit = _FP.get(rel)
    if hit and hit[0] == mt:
        return hit[1]
    import hashlib
    fp = hashlib.md5(f.read_bytes()).hexdigest()[:8]
    _FP[rel] = (mt, fp)
    return fp


_ASSET = re.compile(r'(?:src|href)="(/(?:blocks/[^"]+|[\w./-]+\.(?:css|js)))"')


@app.get("/")
def index():
    html = (WEB / "index.html").read_text(encoding="utf-8")

    def stamp(m):
        fp = _fingerprint(m.group(1))
        return m.group(0).replace(m.group(1), m.group(1) + ("?v=" + fp if fp else ""))

    return Response(_ASSET.sub(stamp, html), media_type="text/html", headers=_STATIC_HEADERS)


def _safe(root: Path, name: str) -> Path | None:
    """★ 目录穿越：不做这一步的话 /../../etc/passwd 就出去了。"""
    p = (root / name).resolve()
    return p if str(p).startswith(str(root.resolve())) and p.is_file() else None


#: ★ `no-cache` **不是**「不缓存」，是「用之前必须回来问一句」。
#: 文件没变服务器回 304，一个字节都不传；变了立刻拿到新的。
#: 不写这行的话浏览器会拿着旧文件不放 —— 你改了代码、刷新了、以为没生效，
#: 实际上跑的是几小时前那份。真栽过一次，查了半天以为是逻辑写错了。
#: （离线能力靠 Service Worker，不靠浏览器这层缓存。）
_STATIC_HEADERS = {"Cache-Control": "no-cache"}


@app.get("/blocks/{name:path}")
def block_file(name: str):
    p = _safe(BLOCKS, name)
    return FileResponse(p, headers=_STATIC_HEADERS) if p else JSONResponse({"error": "没有这个东西"}, status_code=404)


@app.get("/{name:path}")
def static_file(name: str):
    p = _safe(WEB, name)
    return FileResponse(p, headers=_STATIC_HEADERS) if p else JSONResponse({"error": "没有这个东西"}, status_code=404)


def main() -> None:
    import getpass
    import sys

    import uvicorn
    ap = argparse.ArgumentParser()
    ap.add_argument("--lan", action="store_true", help="让同一个 wifi 的手机也能连（要口令）")
    ap.add_argument("--port", type=int, default=8420)
    a = ap.parse_args()
    host = "0.0.0.0" if a.lan else "127.0.0.1"
    if a.lan:
        # ★ 口令不做成命令行参数 —— 那样它会明晃晃挂在 `ps` 的输出里，
        #   同一台机器上任何一个进程都看得见。环境变量，或者当场敲。
        pw = os.environ.get("LIANHUAN_PASSWORD", "").strip()
        if not pw and sys.stdin.isatty():
            print("\n  开到网络上就得有口令 —— 知道地址的人都能进。")
            pw = getpass.getpass("  设一个（输入时不显示）：").strip()
        if not pw:
            print("\n  ✗ --lan 需要口令，没设就不开。两种给法：")
            print("      LIANHUAN_PASSWORD=你的口令 python -m core.server --lan")
            print("      或者在能敲字的终端里跑，它会当场问你。")
            print("    （别写成命令行参数 —— `ps` 一敲就看见了。）\n")
            raise SystemExit(2)
        try:
            _gate.arm(pw)
        except ValueError as e:
            print(f"\n  ✗ 这句口令不能用：{e}")
            print(f"      门开在网络上，谁都能敲。至少 {_gate.MIN_LEN} 个字符，别用文档里的占位串。")
            print("      换一句再起：LIANHUAN_PASSWORD=你的口令 python -m core.server --lan\n")
            raise SystemExit(2)
        print("\n  开了 --lan：同一个网络里的设备都能连，进门要口令。")
        print("     口令存的是加盐哈希，明文不落盘；30 天不用重报。")
        print("     ★ 会起进程的 MCP / 安装接口默认全关；直连本机要显式允许。")
        print("     公共 wifi、宿舍、办公室——还是别开。\n")
    print(f"  连环 · 开源版   http://127.0.0.1:{a.port}\n")
    uvicorn.run(app, host=host, port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
