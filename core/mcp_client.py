"""薄 MCP 客户端 —— 让 AI 用上用户配好的 MCP 工具（钓鱼、日历、任何 stdio server）。

原项目的 AI 有 28 只 MCP 手，走的就是这条路。开源版把它接到 API 引擎上：
`data/mcp.json` 里登记 server（**格式跟 Claude 的 .mcp.json 一样**，现成配置直接抄），
启动时连上、拉工具清单、并进 AI 的手；AI 调工具 = 这儿转发 JSON-RPC。

★ 安全边界：server 的启动命令是**用户自己贴的**（等于用户自己运行程序）。
  AI 只能用已登记的 server，**不能自己添加** —— 想要新的就写进装配单等人点头。
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path

_servers: dict = {}          # name -> _Server


def _cfg_file() -> Path:
    return Path(os.environ.get("LIANHUAN_DB", "data/lianhuan.db")).parent / "mcp.json"


def load_cfg() -> dict:
    try:
        return json.loads(_cfg_file().read_text(encoding="utf-8")).get("mcpServers") or {}
    except Exception:
        return {}


def save_server(name: str, command: str, args: list, env: dict) -> None:
    f = _cfg_file()
    try:
        cfg = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        cfg = {}
    cfg.setdefault("mcpServers", {})[name] = {"command": command, "args": args, "env": env}
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")


def drop_server(name: str) -> None:
    f = _cfg_file()
    try:
        cfg = json.loads(f.read_text(encoding="utf-8"))
        cfg.get("mcpServers", {}).pop(name, None)
        f.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass
    s = _servers.pop(name, None)
    if s:
        asyncio.get_event_loop().create_task(s.close())


class _Server:
    def __init__(self, name: str, spec: dict):
        self.name, self.spec = name, spec
        self.proc: asyncio.subprocess.Process | None = None
        self.tools: list = []
        self.err = ""
        self._id = 0
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        try:
            env = dict(os.environ)
            env.update(self.spec.get("env") or {})
            self.proc = await asyncio.create_subprocess_exec(
                self.spec["command"], *(self.spec.get("args") or []),
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL, env=env,
                limit=8 * 1024 * 1024)
            await self._rpc("initialize", {
                "protocolVersion": "2024-11-05", "capabilities": {},
                "clientInfo": {"name": "lianhuan", "version": "0.1"}}, timeout=20)
            await self._notify("notifications/initialized")
            r = await self._rpc("tools/list", {}, timeout=20)
            self.tools = (r or {}).get("tools") or []
        except Exception as e:
            self.err = f"{type(e).__name__}: {e}"[:160]
            await self.close()

    async def _send(self, msg: dict) -> None:
        self.proc.stdin.write((json.dumps(msg, ensure_ascii=False) + "\n").encode())
        await self.proc.stdin.drain()

    async def _notify(self, method: str) -> None:
        await self._send({"jsonrpc": "2.0", "method": method})

    async def _rpc(self, method: str, params: dict, timeout: float = 45) -> dict:
        async with self._lock:               # stdio 一条管道，请求要排队
            self._id += 1
            rid = self._id
            await self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
            loop = asyncio.get_running_loop()
            end = loop.time() + timeout
            while True:
                left = end - loop.time()
                if left <= 0:
                    raise TimeoutError(method)
                line = await asyncio.wait_for(self.proc.stdout.readline(), timeout=left)
                if not line:
                    raise RuntimeError("server 退出了")
                try:
                    d = json.loads(line)
                except Exception:
                    continue                  # 有的 server 往 stdout 混日志，跳过
                if d.get("id") == rid:
                    if "error" in d:
                        raise RuntimeError(str(d["error"])[:200])
                    return d.get("result") or {}

    async def call(self, tool: str, args: dict) -> dict:
        r = await self._rpc("tools/call", {"name": tool, "arguments": args})
        # 把 content 摊平成文本，喂回模型
        out = []
        for c in (r or {}).get("content") or []:
            if c.get("type") == "text":
                out.append(c.get("text") or "")
        txt = "\n".join(out)[:4000] or json.dumps(r, ensure_ascii=False)[:2000]
        return {"ok": not (r or {}).get("isError"), "result": txt}

    async def close(self) -> None:
        p, self.proc = self.proc, None
        if p and p.returncode is None:
            try:
                p.kill()
                await p.wait()
            except Exception:
                pass


async def start_all() -> None:
    for name, spec in load_cfg().items():
        if name not in _servers:
            s = _Server(name, spec)
            _servers[name] = s
            await s.start()


def status() -> list:
    return [{"name": n, "tools": [t["name"] for t in s.tools],
             "ok": bool(s.tools), "err": s.err}
            for n, s in _servers.items()]


def _fn_name(server: str, tool: str) -> str:
    """openai 函数名只许 [A-Za-z0-9_-] 64 字内。"""
    return re.sub(r"[^A-Za-z0-9_-]", "_", f"{server}__{tool}")[:64]


def openai_tools() -> list:
    out = []
    for n, s in _servers.items():
        for t in s.tools:
            out.append({"type": "function", "function": {
                "name": _fn_name(n, t["name"]),
                "description": f"[{n}] " + (t.get("description") or "")[:400],
                "parameters": t.get("inputSchema") or {"type": "object", "properties": {}}}})
    return out


async def execute(fn_name: str, args: dict) -> dict | None:
    """认领得了就执行，认领不了返回 None（让内置的手接着试）。"""
    for n, s in _servers.items():
        for t in s.tools:
            if _fn_name(n, t["name"]) == fn_name:
                try:
                    return await s.call(t["name"], args)
                except Exception as e:
                    return {"ok": False, "err": f"{type(e).__name__}: {e}"[:200]}
    return None
