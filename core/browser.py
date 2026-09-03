"""连环 · 浏览器版的胶水 —— 同一份后端跑在页面里（Pyodide），不重写。

页面（apps/local/local-boot.js）把 core/ optional/ seed/ 解到 /app，装好 fastapi 那几个纯 Python 包，
然后调这里的 boot() / lifespan()，之后每一条 fetch 都走 handle() 直接喂给 ASGI app。
数据在 /lh/data（页面把它挂成 IndexedDB 持久盘），也就是「家在手机浏览器里」。

★ 只在 sys.platform == "emscripten" 时才有 Pyodide 那些东西；电脑上 import 这个模块没有任何副作用，
  transport() 回 None（httpx 用默认），测试就靠这一点在电脑上验 handle()。
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

IN_BROWSER = sys.platform == "emscripten"

_app = None


def _no_threads() -> None:
    """Pyodide 没有线程：starlette / anyio 把同步端点和文件 IO「丢进线程池」，这里改成当场跑。"""
    import anyio.to_thread
    import starlette.concurrency

    async def inline(func, *args, **kw):
        return func(*args, **kw)

    async def inline_anyio(func, *args, abandon_on_cancel=False, cancellable=None, limiter=None):
        return func(*args)

    asyncio.to_thread = inline
    anyio.to_thread.run_sync = inline_anyio
    starlette.concurrency.run_in_threadpool = inline
    for modname in ("starlette.routing", "starlette.background", "fastapi.routing",
                    "fastapi.dependencies.utils", "fastapi.concurrency"):
        try:
            mod = __import__(modname, fromlist=["_"])
        except Exception:
            continue
        if hasattr(mod, "run_in_threadpool"):
            mod.run_in_threadpool = inline


def boot(data_dir: str, patch: bool | None = None) -> dict:
    """设好数据目录、打好补丁、把 app 拉起来。回一个能给页面看的小结。"""
    global _app
    os.makedirs(data_dir, exist_ok=True)
    os.environ["LIANHUAN_DB"] = os.path.join(data_dir, "lianhuan.db")
    if IN_BROWSER if patch is None else patch:
        _no_threads()
    from core.server import app
    _app = app
    return {"ok": True, "db": os.environ["LIANHUAN_DB"], "python": sys.version.split()[0]}


async def lifespan() -> dict:
    """跑一遍 ASGI 的 startup（没有 uvicorn 替我们跑）。shutdown 永远不发 —— 页面关了就是关了。"""
    done: asyncio.Future = asyncio.get_event_loop().create_future()
    q = [{"type": "lifespan.startup"}]

    async def receive():
        if q:
            return q.pop(0)
        await asyncio.sleep(3600 * 24 * 365)
        return {"type": "lifespan.shutdown"}

    async def send(m):
        if m["type"] in ("lifespan.startup.complete", "lifespan.startup.failed") and not done.done():
            done.set_result(m)

    asyncio.ensure_future(_app({"type": "lifespan", "asgi": {"version": "3.0"}}, receive, send))
    return await done


def _py(x):
    """JS 传进来的东西（JsProxy）转成 Python；电脑上传的本来就是 Python，原样回。"""
    return x.to_py() if hasattr(x, "to_py") else x


def _js(b: bytes):
    if IN_BROWSER:
        from pyodide.ffi import to_js
        return to_js(b)
    return b


async def handle(method: str, path: str, query: str, headers, body, sink) -> None:
    """跑一条请求，结果流进 sink：sink.start(status, headers_json) → sink.chunk(bytes) … → sink.end()。

    headers：[[名, 值], …]；body：bytes / Uint8Array / None。
    流式回复（/chat 的 SSE）也走这条：每来一段就 chunk 一段，页面那头接成 ReadableStream。"""
    hdrs = [(str(k).lower().encode("latin-1"), str(v).encode("latin-1")) for k, v in (_py(headers) or [])]
    raw = _py(body)
    raw = bytes(raw) if raw else b""
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": method.upper(), "scheme": "http", "path": path, "raw_path": path.encode("utf-8"),
        "query_string": (query or "").encode("utf-8"), "root_path": "", "headers": hdrs,
        "client": ("127.0.0.1", 0), "server": ("127.0.0.1", 80),
    }
    got = [{"type": "http.request", "body": raw, "more_body": False}]

    async def receive():
        if got:
            return got.pop(0)
        await asyncio.sleep(3600 * 24)          # 页面不主动断；关页就是断
        return {"type": "http.disconnect"}

    started = False

    async def send(m):
        nonlocal started
        if m["type"] == "http.response.start":
            started = True
            sink.start(int(m["status"]),
                       json.dumps([[k.decode("latin-1"), v.decode("latin-1")] for k, v in m.get("headers", [])]))
        elif m["type"] == "http.response.body":
            b = m.get("body", b"")
            if b:
                sink.chunk(_js(bytes(b)))
            if not m.get("more_body"):
                sink.end()

    try:
        await _app(scope, receive, send)
        if not started:                          # app 一声没吭就退了：给页面一个能看懂的答案
            sink.start(500, json.dumps([["content-type", "text/plain; charset=utf-8"]]))
            sink.chunk(_js("后端没有回应这条请求".encode("utf-8")))
            sink.end()
    except Exception as e:                       # noqa: BLE001 —— 页面那头要看见真实原因
        if not started:
            sink.start(500, json.dumps([["content-type", "text/plain; charset=utf-8"]]))
            sink.chunk(_js(f"{type(e).__name__}: {e}".encode("utf-8")))
        sink.end()


def transport():
    """给 httpx 用的运输层：浏览器里没有 socket，走页面的 fetch（流式也行）。电脑上回 None ＝ httpx 默认。"""
    if not IN_BROWSER:
        return None
    import httpx
    from pyodide.ffi import to_js
    from pyodide.http import pyfetch

    #: 浏览器不让页面自己设的头（fetch 会静默丢掉或报错），发出去之前先摘掉
    FORBIDDEN = {"host", "content-length", "connection", "accept-encoding", "user-agent", "transfer-encoding"}

    class _Body(httpx.AsyncByteStream):
        def __init__(self, resp):
            self.resp = resp

        async def __aiter__(self):
            reader = self.resp.js_response.body.getReader()
            while True:
                r = await reader.read()
                if r.done:
                    break
                yield r.value.to_bytes()

        async def aclose(self):
            return None

    class _Transport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            body = await request.aread()
            headers = {k: v for k, v in request.headers.items() if k.lower() not in FORBIDDEN}
            kw = {"method": request.method, "headers": headers}
            if body:
                kw["body"] = to_js(body)
            resp = await pyfetch(str(request.url), **kw)
            js = resp.js_response
            hdrs = [(str(pair[0]), str(pair[1])) for pair in js.headers]
            return httpx.Response(int(js.status), headers=hdrs, stream=_Body(resp), request=request)

    return _Transport()
