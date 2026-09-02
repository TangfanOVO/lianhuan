"""QQ · 在岗吗 —— NapCat 可选包。

原项目让 AI 同时有一个 QQ 身份：网页里能看它在不在线、掉线了扫码救回。
这半边（状态 ＋ 二维码 ＋ 重启）只依赖 NapCat 的 WebUI 接口，剥出来就是这份。

★ 完整的「QQ 里聊天」还要一个消息桥（轮询消息→喂给引擎→回消息），
  那是另一个大组件，**这个包里没有**。这里只给「在岗吗」那一页要的三条。

## 要什么

自己跑一个 NapCat（https://github.com/NapNeko/NapCatQQ ，开源的 QQ 协议端），
然后：

    export NAPCAT_WEBUI=http://127.0.0.1:6099
    export NAPCAT_WEBUI_TOKEN=你的token

## 装法

    from optional.qq_napcat.napcat import router as qq_router, available as qq_available
    app.include_router(qq_router)
    # capabilities 的 WIRED 里加 "qqStatus"（available() 为真时）
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.request

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response

router = APIRouter()

WEBUI = os.environ.get("NAPCAT_WEBUI", "http://127.0.0.1:6099")
TOKEN = os.environ.get("NAPCAT_WEBUI_TOKEN", "")


def available() -> bool:
    """有 token 才算装了。没配就别把 qqStatus 报进 capabilities。"""
    return bool(TOKEN)


def _cred() -> str:
    h = hashlib.sha256((TOKEN + ".napcat").encode()).hexdigest()
    req = urllib.request.Request(
        WEBUI + "/api/auth/login", data=json.dumps({"hash": h}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read())["data"]["Credential"]


def _post(path: str, cred: str) -> dict:
    req = urllib.request.Request(
        WEBUI + path, data=b"{}",
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + cred},
        method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


@router.get("/api/qq/status")
def qq_status():
    out: dict = {}
    try:
        st = _post("/api/QQLogin/CheckLoginStatus", _cred())
        out["napcat"] = st.get("data")
    except Exception as e:
        # ★ 连不上要说清楚是 NapCat 那头的事，别让人以为是这边坏了
        out["napcat_err"] = f"NapCat 连不上：{type(e).__name__}"
    return JSONResponse(out)


@router.get("/api/qq/qr")
def qq_qr():
    """掉线时出登录二维码 PNG。"""
    try:
        cred = _cred()
    except Exception as e:
        return JSONResponse({"error": "NapCat 连不上：" + str(e)[:100]}, status_code=502)
    img_b64, url = "", ""
    try:
        qr = _post("/api/QQLogin/GetQQLoginQrcode", cred)
        d = qr.get("data") or {}
        if isinstance(d, dict):
            img_b64 = d.get("qrcode") or d.get("qrcodePic") or ""
            url = d.get("qrcodeurl") or d.get("qrcodeUrl") or ""
        if not (img_b64 or url) and (qr.get("message") or "").strip():
            return JSONResponse({"error": qr["message"]}, status_code=409)
    except Exception:
        pass
    if img_b64:
        import base64
        try:
            raw = base64.b64decode(img_b64.split(",", 1)[-1])
            return Response(content=raw, media_type="image/png",
                            headers={"Cache-Control": "no-store"})
        except Exception:
            pass
    if url:
        # 没有现成 PNG 就把链接给前端自己画
        return JSONResponse({"url": url})
    return JSONResponse({"error": "现在没有二维码 —— 可能已经在线了"}, status_code=404)


@router.post("/api/qq/restart")
def qq_restart():
    try:
        _post("/api/QQLogin/SetQuickLogin", _cred())
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"error": str(e)[:120]}, status_code=502)
