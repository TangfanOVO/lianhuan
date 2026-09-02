"""Small, auditable UI bridge to the pinned Engawa MCP server."""
from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core import mcp_client

router = APIRouter()
ALLOWED = (
    "web_read", "rss_read", "shelf", "shelf_add", "shelf_suggest", "shelf_remove",
    "sky_tonight", "apod", "daily_art", "arxiv_new", "daily_poem", "on_this_day",
)


def _server_status() -> dict | None:
    return next((item for item in mcp_client.status() if item["name"] == "engawa"), None)


@router.get("/api/engawa/status")
def status():
    item = _server_status()
    tools = [name for name in (item or {}).get("tools", []) if name in ALLOWED]
    ok = bool(item and item.get("ok") and tools)
    return {"ok": ok, "service": "Engawa MCP", "tools": tools,
            "detail": (f"本机檐廊已连接；{len(tools)} 件工具可用"
                       if ok else "适配器在，但本机 Engawa 还没安装或没连上")}


@router.post("/api/engawa/action")
async def action(req: Request):
    raw = await req.body()
    if len(raw) > 8_000:
        return JSONResponse({"ok": False, "error": "参数太长"}, status_code=413)
    try:
        body = json.loads(raw or b"{}")
    except Exception:
        return JSONResponse({"ok": False, "error": "不是有效 JSON"}, status_code=400)
    tool = body.get("tool") if isinstance(body, dict) else ""
    args = body.get("arguments") if isinstance(body, dict) else {}
    if tool not in ALLOWED or not isinstance(args, dict) or len(args) > 10:
        return JSONResponse({"ok": False, "error": "动作或参数不在白名单里"}, status_code=400)
    result = await mcp_client.call_tool("engawa", tool, args)
    if result is None:
        return JSONResponse({"ok": False, "error": "Engawa 还没连上"}, status_code=503)
    if not result.get("ok"):
        return JSONResponse({"ok": False, "error": result.get("err") or "Engawa 没读回来"}, status_code=502)
    return {"ok": True, "tool": tool, "content": result.get("result"),
            "source": "Engawa MCP · 本机运行时"}
