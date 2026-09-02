"""两副耳朵、两张嘴 —— 各家用自己的，中间只换脑子。

## 为什么有这个文件

原来只有一条路：豆包那条端到端 WS（它一个连接同时当耳朵和嘴），我们把它的**脑子**掐掉，
换成用户自己配的引擎。这条是对的。

错的是**只做了这一条**。ElevenLabs 那边耳朵和嘴都是现成的（Scribe v2 Realtime 流式转写
＋ 流式合成），却被拿来只当嘴，跟豆包的耳朵拼在一起用 —— 那是个不该存在的混合体：
两家都能听能说，没有理由让 A 听、B 说，更没有理由在中间补本地转写或语言翻译。

所以这儿把「耳朵和嘴」抽成一层，**两家各成一条完整的路**：

    豆包听 → 你自己配的引擎想 → 豆包说
    11lab听 → 你自己配的引擎想 → 11lab说

★ 换的永远只有中间那一段（脑子）。耳朵和嘴一律用那一家自己的，不跨家拼、不本地补。

## 两家的形状不一样，但对外是同一套事件

- 豆包：**一个 WS 同时是耳朵和嘴**。说话＝往同一条连接发 `speech_text_buffer.commit`。
- 11lab：耳朵是 Scribe 的 WS，嘴是 TTS 的流式 HTTP —— **两个连接**，但对外一样。

对外统一成这几个事件（跟中继原来处理的那套对齐，前端一个字都不用改）：

    heard.started  人开口了（该闭嘴了）
    heard.delta    边说边出的字
    heard.done     这句说完了 {text}
    audio          一块 PCM {b64}
    spoken         这一句念完了
    error          出错了 {message}
    closed         连接断了
"""
from __future__ import annotations

import asyncio
import base64
import json
from urllib.parse import urlencode

from core import secrets

#: 对外的事件名 —— 两家都映射到这一套
HEARD_STARTED = "heard.started"
HEARD_DELTA = "heard.delta"
HEARD_DONE = "heard.done"
AUDIO = "audio"
SPOKEN = "spoken"
ERROR = "error"
CLOSED = "closed"

VOLC_URL = "wss://openspeech.bytedance.com/api/v3/duplex/realtime/dialogue"
VOLC_MODEL = "1.2.6.1"
ELEVEN_STT_URL = "wss://api.elevenlabs.io/v1/speech-to-text/realtime"


def which() -> str:
    """这一通用哪一家。`volc` 或 `eleven`。

    ★ 按**语言**挑，跟 TTS 那条一个口径（中文豆包在前、英文 11lab 在前）——
      用的人只选语言，不该关心底下是谁。哪家没贴 key 就自动落到另一家。
    """
    from .routes import _order, have_eleven, lang
    prefer = (secrets.get("CALL_PROVIDER") or "").strip().lower()
    if prefer in ("volc", "eleven"):
        return prefer                      # 有人写死了就照他的
    for name in _order(lang()):
        if name == "eleven" and have_eleven() and _has_realtime_stt():
            return "eleven"
        if name == "volc" and secrets.get("VOLC_DUPLEX_KEY"):
            return "volc"
    return "volc"


def _has_realtime_stt() -> bool:
    """★ 只有 ElevenLabs 的 key 还不够 —— 流式转写要账号开通了才用得上。
    没开通的话连上去会被拒，那时候落回豆包比硬撑着好。"""
    return (secrets.get("ELEVEN_REALTIME") or "1").strip() not in ("0", "off", "no")


def available() -> dict:
    """哪几条路现在真能走 —— 界面照实显示用，不许含糊。"""
    from .routes import have_eleven
    return {
        "volc": bool(secrets.get("VOLC_DUPLEX_KEY")),
        "eleven": bool(have_eleven() and _has_realtime_stt()),
        "using": which(),
    }


# ══════════════════════════════════════════════════════════════════
class VolcDuplex:
    """豆包：一个 WS 既是耳朵也是嘴。

    ★ 它自己也能想 —— 但那样一来用户的记忆、人设、那些手全都用不上，
      它会变成一个陌生人。所以 ASR 一出字就把它的脑子掐掉（`response.cancel`），
      只留耳朵和嘴。
    """

    name = "volc"

    def __init__(self, voice: str | None = None):
        self.voice = voice or secrets.get("VOLC_DUPLEX_VOICE") or "zh_female_vv_jupiter_bigtts"
        self.up = None

    async def open(self):
        import websockets
        key = secrets.get("VOLC_DUPLEX_KEY")
        self.up = await websockets.connect(VOLC_URL,
                                           additional_headers={"X-Api-Key": key},
                                           max_size=None)
        await self.up.send(json.dumps({
            "type": "session.create",
            "session": {
                "model": VOLC_MODEL,
                "audio": {
                    "input": {"format": {"sample_rate": 16000, "codec": "pcm"}},
                    "output": {"format": {"sample_rate": 24000, "codec": "pcm_s16le"}},
                    "voice": self.voice,
                },
            },
        }, ensure_ascii=False))

    async def close(self):
        if self.up:
            try:
                await self.up.close()
            finally:
                self.up = None

    async def send_audio(self, b64: str):
        await self.up.send(json.dumps({"type": "input_audio_buffer.append", "audio": b64}))

    async def hush(self):
        """掐掉它自己的脑子 / 停下正在念的。"""
        await self.up.send(json.dumps({"type": "response.cancel"}))

    async def say(self, text: str, tag: str):
        """让它念这一句。

        ★ 用 `commit` 而不是 `replacement`：后者只在它自己正生成回复的窗口内有效，
          我们把它的脑子掐掉之后那个窗口就关了（原项目 0818 栽过一次）。
        """
        await self.up.send(json.dumps({"type": "speech_text_buffer.commit",
                                       "event_id": tag, "text": text},
                                      ensure_ascii=False))

    async def recv(self):
        async for raw in self.up:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", "ignore")
            try:
                d = json.loads(raw)
            except Exception:
                continue
            t = d.get("type") or ""
            if t == "conversation.item.input_audio_transcription.started":
                yield {"type": HEARD_STARTED}
            elif t == "conversation.item.input_audio_transcription.delta":
                yield {"type": HEARD_DELTA, "text": (d.get("delta") or d.get("text") or "")}
            elif t == "conversation.item.input_audio_transcription.completed":
                yield {"type": HEARD_DONE,
                       "text": (d.get("text") or d.get("transcript") or "").strip()}
            elif t == "response.output_audio.delta":
                yield {"type": AUDIO, "b64": d.get("audio")}
            elif t == "response.output_audio.done":
                yield {"type": SPOKEN}
            elif t == "error":
                yield {"type": ERROR, "message": str(d.get("message") or d)[:200]}
        yield {"type": CLOSED}


# ══════════════════════════════════════════════════════════════════
class ElevenDuplex:
    """ElevenLabs：耳朵是 Scribe v2 Realtime 的 WS，嘴是流式 TTS。

    ★ 跟豆包不同的是它**没有自己的脑子**要掐 —— Scribe 只转写。
      所以「打断」这件事在这儿是：停掉正在推的那段音频（`hush()` 设一个代，
      正在跑的合成看见代变了就自己收手）。
    """

    name = "eleven"

    def __init__(self, voice: str | None = None):
        self.voice = voice or secrets.get("ELEVEN_VOICE_ID") or "21m00Tcm4TlvDq8ikWAM"
        self.up = None
        self._gen = 0                    # 打断用：换一代，正在念的那段自己停
        self._out = None                 # 合成产出的音频往这儿放
        self._seg = False

    async def open(self):
        import websockets
        from .routes import _eleven_key, lang
        q = urlencode({
            "model_id": "scribe_v2_realtime",
            "audio_format": "pcm_16000",
            "commit_strategy": "vad",
            # ★ 这个数就是「你停多久算说完了」。太大＝他半天不接话，太小＝你换气他就抢。
            "vad_silence_threshold_secs": (secrets.get("ELEVEN_VAD_SEC") or "0.8"),
            "vad_threshold": "0.4",
            "min_speech_duration_ms": "100",
            "min_silence_duration_ms": "100",
            # ★ 0901 拿真 key 打过才知道：这个参数叫 `language_code`，不叫 `language`。
            #   写成 language 它**不报错**，只是 session 里 language_code 是 null ——
            #   静悄悄地当成没指定。（写完没跑过的东西就是这样骗人的。）
            "language_code": "zho" if lang() != "en" else "eng",
        })
        self.up = await websockets.connect(
            f"{ELEVEN_STT_URL}?{q}",
            additional_headers={"xi-api-key": _eleven_key()},
            ping_interval=20, ping_timeout=20, max_size=8 * 1024 * 1024)
        self._out = asyncio.Queue()

    async def close(self):
        self._gen += 1
        if self.up:
            try:
                await self.up.close()
            finally:
                self.up = None

    async def send_audio(self, b64: str):
        await self.up.send(json.dumps({"message_type": "input_audio_chunk",
                                       "audio_base_64": b64, "sample_rate": 16000},
                                      separators=(",", ":")))

    async def hush(self):
        """人开口了 —— 把正在念的那段掐掉（Scribe 那头没有脑子要掐）。"""
        self._gen += 1

    async def say(self, text: str, tag: str):
        """流式合成，边出边往外推。

        ★ 要 `pcm_24000`：跟豆包那条出来的格式一样，前端一个字都不用改。
        """
        import httpx
        from core import speech
        from .routes import _eleven_key, eleven_model
        gen, model = self._gen, eleven_model()
        text, _ = speech.for_engine(text, "eleven_v3" if "v3" in model else model)
        if not text.strip():
            return
        url = (f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice}/stream"
               f"?output_format=pcm_24000")
        try:
            async with httpx.AsyncClient(timeout=60) as c:
                async with c.stream("POST", url,
                                    headers={"xi-api-key": _eleven_key()},
                                    json={"text": text, "model_id": model}) as r:
                    if r.status_code != 200:
                        body = (await r.aread()).decode("utf-8", "ignore")
                        from .routes import _eleven_err
                        await self._out.put({"type": ERROR,
                                             "message": _eleven_err(r.status_code, body)})
                        return
                    async for chunk in r.aiter_bytes(4800):     # 0.1 秒一块
                        if gen != self._gen:
                            return                              # 被打断了，别再推
                        if chunk:
                            await self._out.put({"type": AUDIO,
                                                 "b64": base64.b64encode(chunk).decode()})
        except Exception as e:
            await self._out.put({"type": ERROR, "message": "合成那头出错了：" + str(e)[:140]})
            return
        if gen == self._gen:
            await self._out.put({"type": SPOKEN})

    async def recv(self):
        """把「耳朵那条 WS」和「嘴产出的音频」并成一条流。"""
        async def _from_ws():
            async for raw in self.up:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", "ignore")
                try:
                    d = json.loads(raw)
                except Exception:
                    continue
                yield d
            yield None                                          # 断了

        ws_it = _from_ws()
        ws_task = asyncio.ensure_future(ws_it.__anext__())
        out_task = asyncio.ensure_future(self._out.get())
        try:
            while True:
                done, _ = await asyncio.wait({ws_task, out_task},
                                             return_when=asyncio.FIRST_COMPLETED)
                if out_task in done:
                    yield out_task.result()
                    out_task = asyncio.ensure_future(self._out.get())
                if ws_task in done:
                    try:
                        d = ws_task.result()
                    except StopAsyncIteration:
                        yield {"type": CLOSED}
                        return
                    if d is None:
                        yield {"type": CLOSED}
                        return
                    for ev in self._map(d):
                        yield ev
                    ws_task = asyncio.ensure_future(ws_it.__anext__())
        finally:
            for t in (ws_task, out_task):
                if not t.done():
                    t.cancel()

    def _map(self, d: dict):
        """Scribe 的事件 → 对外那一套。"""
        mt = str(d.get("message_type") or "")
        text = str(d.get("text") or "").strip()
        if mt == "partial_transcript":
            if text and not self._seg:
                self._seg = True
                yield {"type": HEARD_STARTED}
            if text:
                yield {"type": HEARD_DELTA, "text": text}
        elif mt == "final_transcript":
            # ★ 它在 VAD 收口**之前**先给一版定稿；这一版只当增量，
            #   真正开一轮要等下面那个 committed（不然一句话会被切成两轮）。
            if text:
                self._final = text
                yield {"type": HEARD_DELTA, "text": text}
        elif mt == "committed_transcript":
            self._seg = False
            t = text or getattr(self, "_final", "")
            self._final = ""
            # ★ 0901 实测：人不说话的时候它也会隔一阵空收一次口 ——
            #   一条 partial 都没有，committed 的 text 是空的。空的不许开一轮。
            if t:
                yield {"type": HEARD_DONE, "text": t}
        elif mt in ("session_closed", "session_ended"):
            yield {"type": CLOSED}
        elif mt in ("auth_error", "quota_exceeded", "rate_limited", "input_error",
                    "transcriber_error", "invalid_request", "unaccepted_terms",
                    "queue_overflow", "resource_exhausted",
                    "session_time_limit_exceeded", "chunk_size_exceeded",
                    "insufficient_audio_activity", "commit_throttled", "error"):
            self._seg = False
            yield {"type": ERROR, "message": _el_err(mt, d)}


def _el_err(mt: str, d: dict) -> str:
    """把它的错误码翻成人话 —— 照实说缺什么、去哪改。"""
    raw = str(d.get("error") or d.get("message") or "")[:140]
    if mt == "auth_error":
        return "ElevenLabs 那把钥匙它不认（功能包页里换一把）。"
    if mt in ("quota_exceeded", "resource_exhausted"):
        return "ElevenLabs 额度用完了。"
    if mt in ("rate_limited", "commit_throttled"):
        return "ElevenLabs 说太快了，缓一下再说。"
    if mt == "unaccepted_terms":
        return "这个账号还没同意 ElevenLabs 那边的条款 —— 去它网站上点一下。"
    if mt == "insufficient_audio_activity":
        return "没听见声音 —— 麦克风是不是没给权限？"
    return "ElevenLabs 转写出错：" + (raw or mt)


def make(voice: str | None = None):
    """按当前配置开一副耳朵＋一张嘴。"""
    return ElevenDuplex(voice) if which() == "eleven" else VolcDuplex(voice)
