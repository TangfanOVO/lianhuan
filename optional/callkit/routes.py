"""通话 —— 听（转写）和说（合成）。这算**功能**，不算外部项目：
贴一把 key 进来就能打电话。

## 你只需要选「中文」还是「英文」

底下接的是 ElevenLabs（一把 key，转写＋合成都有）和豆包/火山（合成）。
**但界面上不问你用哪家** —— 你选语言，这儿按语言挑：

  中文 → 豆包优先（中文听着更自然），没贴就用 ElevenLabs 的多语种模型
  英文 → ElevenLabs 优先，没贴就用豆包

只贴了一家？那两种语言都走那家，界面会说清楚现在是谁在说话 ——
**不能让人选了「英文」却不知道底下没接**。

## 这一版是「你说完他再说」，不是全双工

录音 → 停下 → 转写 → 他想 → 合成 → 放出来。中间不能插话。
真正的全双工（两边同时开着流、能打断）要另一条 WebSocket 的路，
这一版没做 —— 写在这儿是因为**含糊比没做更糟**。

★ key 走 core.secrets（界面贴或环境变量），绝不进库、不进导出。
"""
from __future__ import annotations

import base64
import json
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from core import secrets

router = APIRouter()


def have_eleven() -> bool: return bool(secrets.get("ELEVENLABS_API_KEY"))
def have_volc() -> bool:   return bool(secrets.get("VOLC_TTS_APPID") and secrets.get("VOLC_TTS_TOKEN"))


def lang() -> str:
    """说话用哪种语言。`zh` 或 `en`，默认中文。

    ★ 界面上问的是**语言**，不是厂商 —— 用的人不该关心底下接的是谁。
      （`TTS_PROVIDER` 那个旧键还认，谁在环境变量里写死了哪家，照他的来。）
    """
    v = (secrets.get("CALL_LANG") or "zh").strip().lower()
    return "en" if v.startswith("en") else "zh"


def voices() -> dict:
    """这两种语言现在分别由谁来说 —— 界面要照实显示，不许含糊。"""
    def who(l):
        order = _order(l)
        for name in order:
            if (name == "eleven" and have_eleven()) or (name == "volc" and have_volc()):
                return name
        return None
    return {"lang": lang(), "zh": who("zh"), "en": who("en"),
            "eleven": have_eleven(), "volc": have_volc()}


def _order(l: str) -> list:
    """按语言排引擎。中文豆包在前（听着更自然），英文 ElevenLabs 在前。"""
    prefer = (secrets.get("TTS_PROVIDER") or "").strip().lower()
    if prefer in ("eleven", "volc"):                 # 有人明确写死了就照他的
        return [prefer, "volc" if prefer == "eleven" else "eleven"]
    return ["volc", "eleven"] if l == "zh" else ["eleven", "volc"]


def _eleven_key() -> str:
    """取 key，顺手挡住一类**报错完全看不懂**的情况。

    ★ 0830 真撞到的：key 里混进非 ASCII 字符（粘贴时带进了中文、全角符号、
      或者从网页复制时夹带的不可见字符），httpx 往 header 上塞的时候直接抛
      `'ascii' codec can't encode characters` —— 那句话对用的人毫无意义，
      他只会以为是我们的程序坏了。宁可在这儿拦下来，说人话。
    """
    k = (secrets.get("ELEVENLABS_API_KEY") or "").strip()
    if k and not k.isascii():
        raise RuntimeError(
            "这把 ElevenLabs key 里有中文或全角字符 —— 多半是复制的时候带进来的。"
            "去后台重新建一把，用 sk- 开头那串完整的（key 只在创建那一次完整显示）。")
    return k


def _eleven_err(code: int, body: str) -> str:
    """ElevenLabs 报错时**别只回一个数字** —— 401 的坑太深，直接把该查的摆出来。

    ★ 下面这几条是真踩出来的，不是从文档抄的：
      · 后台那个「复制」按钮拿到的**不一定能用**：key 只在创建时完整显示一次，
        之后复制到的可能是残的 —— 重新建一把，用 `sk-` 开头那个完整的
      · **权限**：勾得不全一样是 401。整条电话链至少要
        Voices read ＋ Text to Speech ＋ Speech to Text；
        实在调不通就先建一把**不限制权限**的试，通了再往回收
      · 401 ＝ key 的事（无效／复制不全／过期／停用／已轮换）；
        **IP 白名单不匹配是 403，不是 401** —— 别对着白名单查半天
    """
    # ★ 400 也可能是 key 的事：复制不全时它回的是 400 不是 401，
    #   而且会直接说「API key must be exactly N characters」—— 那句话比我们说十句都准，
    #   所以把它原样带出去，再补上该怎么办。
    detail = ""
    if code in (400, 401):
        try:
            import json as _j
            d = _j.loads(body or "{}").get("detail") or {}
            detail = str(d.get("message") or "")[:140]
        except Exception:
            detail = ""
    if code == 400 and ("api key" in (detail or "").lower() or "authentication" in (body or "").lower()):
        return ("ElevenLabs 不认这把 key（400）：" + (detail or "格式不对")
                + "　→ 多半是复制不全。key 只在创建那一次完整显示，"
                "后台再点「复制」拿到的不一定是整串 —— 重新建一把，用 sk- 开头那串完整的。")
    if code == 401:
        return ("ElevenLabs 说这把 key 不认（401）"
                + ("：" + detail if detail else "") + "。八成是这三件之一："
                "① 后台点「复制」拿到的 key 是残的 —— key 只在创建那一次完整显示，"
                "重新建一把用 sk- 开头那个完整的；"
                "② 权限没勾全 —— 整条电话链要 Voices read ＋ Text to Speech ＋ Speech to Text，"
                "调不通就先建一把不限制权限的试，通了再往回收；"
                "③ key 过期／被停用／已经轮换过了。"
                "（顺带：IP 白名单不匹配报的是 403 不是 401，别往那儿查。）")
    if code == 403:
        return "ElevenLabs 说没权限（403）—— 多半是 IP 白名单不匹配，或者这把 key 缺这一项权限。"
    if code == 429:
        return "ElevenLabs 说太频繁了（429）—— 等一下再说，或者看看额度还剩多少。"
    return f"ElevenLabs 回了 {code}：{(body or '')[:120]}"


# ── 说（合成）─────────────────────────────────────────────
def eleven_model() -> str:
    """用哪个模型。★ 只有 **v3** 认音频标签（`[sighs]` 这种）——
    别的模型看见方括号会**一本正经念出来**，所以文本那头要照这个决定剥不剥。"""
    return (secrets.get("ELEVEN_MODEL") or "eleven_multilingual_v2").strip()


async def _tts_eleven(text: str) -> bytes:
    import httpx
    from core import speech
    voice = secrets.get("ELEVEN_VOICE_ID") or "21m00Tcm4TlvDq8ikWAM"
    model = eleven_model()
    # 「叹了口气」→ [sighs]（v3）；不认标签的模型这儿会把神态整段剥掉
    text, _ = speech.for_engine(text, "eleven_v3" if "v3" in model else model)
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128",
            headers={"xi-api-key": _eleven_key()},
            json={"text": text, "model_id": model})
        if r.status_code != 200:
            raise RuntimeError(_eleven_err(r.status_code, r.text))
        return r.content


async def _tts_volc(text: str) -> bytes:
    import httpx
    from core import speech
    # 它认不了音频标签，所以走另一条：把神态剥干净，改用语速/音量/音调来做
    # （说重话难听不是因为音量，是因为平推的嗓子做不出软化 —— 要放慢、压低、留气口）
    text, p = speech.for_engine(text, "volc")
    audio = {"voice_type": secrets.get("VOLC_VOICE_TYPE") or "BV001_streaming",
             "encoding": "mp3"}
    if p:
        # 我们这边是 -50~100 的相对值，上游要的是倍率（1.0 ＝ 正常）
        audio["speed_ratio"] = round(1 + p["speed"] / 100, 3)
        audio["volume_ratio"] = round(1 + p["loudness"] / 100, 3)
        audio["pitch_ratio"] = round(p["pitch"], 3)
    payload = {
        "app": {"appid": secrets.get("VOLC_TTS_APPID"),
                "token": secrets.get("VOLC_TTS_TOKEN"), "cluster": "volcano_tts"},
        "user": {"uid": "lianhuan"},
        "audio": audio,
        "request": {"reqid": uuid.uuid4().hex, "text": text, "operation": "query"},
    }
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post("https://openspeech.bytedance.com/api/v1/tts",
                         headers={"Authorization": "Bearer;" + secrets.get("VOLC_TTS_TOKEN")},
                         json=payload)
        d = r.json()
        if not d.get("data"):
            raise RuntimeError(f"豆包回了：{str(d.get('message') or d)[:120]}")
        return base64.b64decode(d["data"])


@router.post("/api/tts")
async def api_tts(req: Request):
    b = await req.json()
    text = (b.get("text") or "").strip()[:600]
    if not text:
        return JSONResponse({"error": "空的"}, status_code=400)
    # ★ 按**语言**挑，不是按厂商。请求里带了 lang 就用它（一句英文可以临时切过去）
    l = (b.get("lang") or "").strip().lower()
    l = "en" if l.startswith("en") else ("zh" if l.startswith("zh") else lang())
    fns = {"eleven": _tts_eleven, "volc": _tts_volc}
    chain = [(n, fns[n]) for n in _order(l)]
    errs = []
    for name, fn in chain:
        if (name == "eleven" and not have_eleven()) or (name == "volc" and not have_volc()):
            continue
        try:
            audio = await fn(text)
            return Response(content=audio, media_type="audio/mpeg",
                            headers={"Cache-Control": "no-store"})
        except Exception as e:
            errs.append(f"{name}: {e}")
    return JSONResponse({"error": "合成没成。" + ("；".join(errs)[:200] if errs
                         else "两家的 key 都还没贴（功能包页里贴）。")}, status_code=502)


# ── 听（转写）─────────────────────────────────────────────
@router.post("/api/listen")
async def api_listen(req: Request):
    b = await req.json()
    data = b.get("dataURL") or ""
    m = data.split(",", 1)
    if len(m) != 2:
        return JSONResponse({"error": "录音读不出来"}, status_code=400)
    if not have_eleven():
        return JSONResponse({"error": "转写要 ElevenLabs 的 key（功能包页里贴）——"
                                      "或者照 docs/API.md 的契约自己接一家识别"}, status_code=501)
    try:
        raw = base64.b64decode(m[1])
    except Exception:
        return JSONResponse({"error": "录音读不出来"}, status_code=400)
    mime = "audio/webm"
    if "audio/mp4" in m[0]:
        mime = "audio/mp4"
    import httpx
    async with httpx.AsyncClient(timeout=90) as c:
        r = await c.post("https://api.elevenlabs.io/v1/speech-to-text",
                         headers={"xi-api-key": _eleven_key()},
                         data={"model_id": "scribe_v1",
                               # 说明这句大概是什么语言，短句的识别率差别很明显
                               "language_code": "eng" if lang() == "en" else "zho"},
                         files={"file": ("say" + (".mp4" if mime == "audio/mp4" else ".webm"),
                                         raw, mime)})
        if r.status_code != 200:
            return JSONResponse({"error": _eleven_err(r.status_code, r.text)}, status_code=502)
        d = r.json()
    return JSONResponse({"text": (d.get("text") or "").strip(), "feel": ""})


# ── 能插话的那种（要另一把钥匙）────────────────────────────
@router.websocket("/api/call/duplex")
async def call_duplex(ws):
    """能插话的通话。**对面那家只当耳朵和嘴，脑子还是你自己配的引擎。**"""
    from . import duplex as _dx
    await ws.accept()
    miss = _dx.check()
    if miss:
        await ws.send_text(json.dumps({"type": "error", "error": "；".join(miss)},
                                      ensure_ascii=False))
        await ws.close()
        return
    try:
        await _dx.relay(ws)
    except Exception as e:
        try:
            await ws.send_text(json.dumps({"type": "error", "error": _dx.up_err(e)},
                                          ensure_ascii=False))
        except Exception:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass


# ── 这会儿谁在说话 ／ 换语言 ────────────────────────────────
# ★ 路径叫 /api/call/lang，**不叫 /api/voice** —— 后者在这套界面里是「音色调校」
#   （语速/音高/音色/用谁的嗓子）那一族，语义完全不同。两件事共用一个名字，
#   接上之后那一页会拿到不认识的数据、显示得乱七八糟。（0830 差点就这么撞上。）
@router.get("/api/call/lang")
def api_voice():
    """界面拿它来显示：现在说哪种语言、这两种语言分别由谁来说。

    ★ 有一种情况必须说清楚：只贴了一家 key 时，**两种语言都走那家** ——
      人选了「英文」却不知道底下没接，那就是界面在骗他。
    """
    v = voices()
    v["ok"] = bool(v["eleven"] or v["volc"])
    v["listen"] = "eleven" if have_eleven() else None      # 转写目前只有这一家
    return v


@router.post("/api/call/lang")
async def api_voice_set(req: Request):
    b = await req.json()
    l = (b.get("lang") or "").strip().lower()
    if not l.startswith(("zh", "en")):
        return JSONResponse({"ok": False, "error": "只认 zh 或 en"}, status_code=400)
    secrets.set_many({"CALL_LANG": "en" if l.startswith("en") else "zh"})
    return {"ok": True, **voices()}
