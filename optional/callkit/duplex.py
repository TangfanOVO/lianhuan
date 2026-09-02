"""能插话的那种通话 —— 中继。

## 一句话：**对面那家只当耳朵和嘴，脑子还是你自己配的那个。**

    你说话 ─▶ 浏览器采 16k PCM ─▶ 这一层 ─▶ 语音服务的 ASR（边说边出字）
                                              │
                        它一说完 ─▶ ★ 立刻掐掉那家自己的脑子（response.cancel）
                                              │
                                    这一层去问**你自己配的引擎**（带记忆和人设）
                                              │
                    它的回复 ─▶ speech_text_buffer.commit ─▶ 那家只管把这句念出来
                                              │
                                      音频 ─▶ 浏览器放出来

**打断**：那边一报「听见你开口了」→ 这一层立刻掐掉正在生成的那句 ＋ 通知前端停播。
这就是「能插话」的全部意思。

## 为什么不让它自己当脑子

那家的端到端模型自己也能想、能答 —— 但那样一来：
你的记忆、你的人设、你给它的那些手，**全都用不上**，它会变成一个陌生人。
所以 ASR 一出字就把它的脑子掐掉，只留耳朵和嘴。

## 为什么必须过这一层，不能让浏览器直连

key 不进浏览器。另外，「去问你自己的引擎」这件事也只有在服务端做得了。
"""
from __future__ import annotations

import asyncio
import json
import time

from core import secrets

UPSTREAM = "wss://openspeech.bytedance.com/api/v3/duplex/realtime/dialogue"
MODEL = "1.2.6.1"

_store = None
_pick = None          # () -> Engine，由 packs 在挂载时注入（别在这儿 import server，会拿到第二份模块）


def bind(store, pick_engine) -> None:
    global _store, _pick
    _store, _pick = store, pick_engine


def have_key() -> bool:
    return bool(secrets.get("VOLC_DUPLEX_KEY"))


def check() -> list:
    miss = []
    if not have_key():
        miss.append("能插话还差一把钥匙：豆包「端到端实时语音」的 API Key（新版控制台里拿）")
    try:
        import websockets  # noqa: F401
    except ImportError:
        miss.append("还差一个 Python 包：`pip install websockets`")
    return miss


# ══ 回声：听到的是不是我自己刚说过的话 ══════════════════════
#
# 不戴耳机的时候，喇叭放出去的声音会被麦克风收回来。浏览器的回声消除（AEC）
# 对**页面自己用 WebAudio 播出去**的声音是够不着的 —— 参考信号取的是输出设备混音，
# 规范没规定要把 WebAudio 的输出算进去，各家实现也不一致。
# 于是上游会老老实实把我自己的话转写一遍交回来，后果有两个，都很难看：
#   ① 我把我自己打断（一开口就听见"有人在说话"）
#   ② 我自己的话被当成对方说的，另开一轮 —— 我在回答我自己
#
# 判据：听到的这串，连着的 N 个字有多少落在我刚说过的话里。
# ★ 别用「字符集合命中率」那种无序的算法：中文「明天下雨」的四个字
#   全都出现在「下雨天明天也下」里，命中率 100%，于是**对方真的插话反而被吞掉**；
#   英文更糟，字母本来就那么几个。位置和顺序必须算数。
# ★ 宁可漏判，不可误判：漏判最多是我多说两句被打断；
#   误判是对方喊停喊不动，那个难受得多。
ECHO_N = 4              # 几个字算一组
ECHO_KEEP_SEC = 45      # 我说过的话记这么久（一句能在对方耳朵里响三四十秒）
ECHO_KEEP_N = 8         # 最多记这么多句
ECHO_BARGE_FLOOR = 0.6  # 判「算不算打断」的门槛
ECHO_BARGE_MIN = 5      # 少于这么多字就先别判 —— 头一两片转写还在飘
ECHO_TURN_FLOOR = 0.72  # 判「算不算新的一轮」的门槛（更严，宁可让它开一轮）
ECHO_TURN_MIN = 6       # 短句一律放过去，不然「嗯」「好的」会被当回声吞掉


def norm_txt(t: str) -> str:
    """只留能比对的字：汉字、字母、数字，字母转小写。标点空格在回声里本来就对不上。"""
    import re
    return re.sub(r"[^\u4e00-\u9fff0-9a-z]", "", (t or "").lower())


def overlap(heard: str, said: str, n: int = ECHO_N) -> float:
    """听到的这串，有多少落在我说过的那串里。0～1。"""
    h, s = norm_txt(heard), norm_txt(said)
    if not h or not s:
        return 0.0
    if len(h) < n:                       # 太短组不成一组，退回「整串在不在里头」
        return 1.0 if h in s else 0.0
    hg = {h[i:i + n] for i in range(len(h) - n + 1)}
    sg = {s[i:i + n] for i in range(len(s) - n + 1)}
    return len(hg & sg) / len(hg)


def said_note(state: dict, text: str, now: float) -> None:
    """记一笔「我刚说了这句」。★ 不能只记「正在念的那一句」——
    一轮要说三四句，回声飘回来的时候早念到下一句了，只比一句必然漏。"""
    if not (text or "").strip():
        return
    lst = state.setdefault("said_log", [])
    lst.append((now, text))
    state["said_log"] = [x for x in lst if x[0] >= now - ECHO_KEEP_SEC][-ECHO_KEEP_N:]


def echo_of(state: dict, heard: str, now: float,
            floor: float = ECHO_TURN_FLOOR, min_len: int = ECHO_TURN_MIN):
    """听到的这句，是不是我自己的声音绕回来了。返回 (是不是, 撞上的那句)。"""
    if len(norm_txt(heard)) < min_len:
        return False, ""
    rec = [t for ts, t in (state.get("said_log") or []) if ts >= now - ECHO_KEEP_SEC]
    if not rec:
        return False, ""
    for one in rec + ([" ".join(rec)] if len(rec) > 1 else []):
        if overlap(heard, one) >= floor:
            return True, one
    return False, ""


def should_land(turn: int, cur_turn: int, gen_at_start: int, gen_now: int) -> tuple[bool, str]:
    """这一句到底该不该落库。★ 提成纯函数是为了能单独测 ——
    它嵌在 WS 连接里的时候，这两条纪律一条都没法验（0831 交接里的待办②）。

    两条纪律，谁先破谁说了算：
    1. **人又开口了**（turn 变了）：这一轮剩下的全部作废，一个字都不许念、不许落
    2. **档案被换了**（generation 变了）：这句是照旧档案说的，落进新档案就是配错原文
    """
    if turn != cur_turn:
        return False, "人已经又开口了，这一轮作废"
    if gen_at_start != gen_now:
        return False, "说话期间档案换了，这句不落库"
    return True, ""


def session_create(cfg: dict | None = None) -> dict:
    """开场帧。★ **故意不给 instructions、不给 tools** ——
    我们只借它的耳朵和嘴，脑子是自己的那个。给了它反而会自作主张。"""
    cfg = cfg or {}
    return {
        "type": "session.create",
        "session": {
            "model": MODEL,
            "audio": {
                "input": {"format": {"sample_rate": 16000, "codec": "pcm"}},
                "output": {"format": {"sample_rate": 24000, "codec": "pcm_s16le"}},
                "voice": cfg.get("voice") or secrets.get("VOLC_DUPLEX_VOICE")
                         or "zh_female_vv_jupiter_bigtts",
            },
        },
    }


def up_err(e: Exception) -> str:
    m = str(e)
    if "401" in m:
        return ("那把钥匙它不认。要的是**新版控制台**里「API Key 管理」那把 —— "
                "跟语音合成用的 appid/token 不是一回事，别混用。"
                "另外确认这把钥匙开通了「端到端实时语音」。").replace("**", "")
    if "403" in m:
        return "它说没权限：这把钥匙多半没开通「端到端实时语音」，或者额度用完了。"
    if "timed out" in m.lower():
        return "连不上 —— 这台机器出得去外网吗？"
    return "连不上：" + m[:160]


async def relay(ws) -> None:
    """浏览器 ←→ 这一层 ←→ 语音服务。"""
    import websockets
    from core.memory import build_injection
    from core.engines.base import Turn as ETurn
    from core.protocol import SAY
    from core.store.base import Turn as StoredTurn
    from core import speech
    import uuid

    from . import ears as _ears
    # ★ 0831 自查：这条路原来把每一轮都按 `session_id="call"` 落库、
    #   `channel` 走默认值 'text' —— 于是全双工电话里说的话会**漏进文字聊天的上下文**，
    #   而且所有电话共用一个 id，挂断再拨也接着上一通。一个 WS 连接 = 一通电话 = 一个 id。
    call_id = uuid.uuid4().hex
    state = {"turn": 0, "spoken_done": False, "out": False}
    # turn：换一轮就把上一轮的尾巴全丢掉（打断靠它）
    # out：我这会儿正在出声吗 —— 判「刚听见的是不是我自己的回声」要用它
    heard, said = [], []

    async def tell(d):
        try:
            await ws.send_text(json.dumps(d, ensure_ascii=False))
        except Exception:
            pass

    # ★ 0901：耳朵和嘴抽到 ears.py 了 —— **两家各成一条完整的路**
    #   （豆包听→我们的脑子→豆包说；11lab听→我们的脑子→11lab说），
    #   而不是拿 A 的耳朵配 B 的嘴。换的永远只有中间那一段。
    cfg = await _first(ws)
    mouth = _ears.make(cfg.get("voice"))
    await mouth.open()
    await tell({"type": "lianhuan.provider", "name": mouth.name})
    try:

        async def think(text: str, turn: int):
            """去问你自己配的引擎，一句一句塞回那张嘴。

            ★ 逐句发而不是等整段：等整段生成完才开口，实测要等到人以为断线了。
            ★ 每句发出去之前都要看一眼 `state["turn"]` —— 人已经又开口了的话，
              这一轮剩下的全部作废，一个字都不许再念。
            """
            heard.append(text)
            gen_at_start = getattr(_store, "generation", 0)   # ★ 这一轮基于哪份档案
            state["spoken_done"] = False
            uid = _store.add_turn(StoredTurn(role="user", content=text, channel="call",
                                             call_id=call_id, session_id="call",
                                             ts=time.time()))
            # ★ 原话只走 history，别再让 system 带一份（进两遍模型会以为人在重复自己）；
            #   电话只读**本通**，读不到文字聊天。
            hist = [{"role": t.role, "content": t.content}
                    for t in _store.context_turns(channel="call", call_id=call_id,
                                                  limit=16, exclude_id=uid)]
            system = build_injection(_store, text, include_dialogue=False,
                                     here="call") + "\n\n" + speech.HINT
            # ★ 0831 外部验收 P1-04：普通 /chat 会额外加一段心情注入，这条路没有 ——
            #   同一个人在文字里知道自己什么心情、一接电话就不知道了。补齐。
            #   （homelife 是内置默认装；没装就跳过，不是错。）
            try:
                from optional.homelife.routes import mood_inject as _mi
                system += "\n\n" + _mi()
            except Exception:
                pass
            eng = _pick()
            buf, tools, rest = [], [], []
            spoken_first = False
            try:
                async for ev in eng.stream(ETurn(message=text, system=system,
                                                 history=hist)):
                    if turn != state["turn"]:
                        return                       # 被打断了，抽干
                    if not ev.startswith("data: "):
                        continue
                    try:
                        d = json.loads(ev[6:])
                    except Exception:
                        continue
                    # ★ 0831 外部验收 P0-03：这儿原来是「不是 SAY 就 continue」——
                    #   工具事件被整个丢掉，界面永远不知道他去动手了，回复落库也不带 tools，
                    #   下一轮没法追证「到底做成没有」。跟文字聊天那条路对齐。
                    if d.get("type") in ("tool_live", "tool_done"):
                        await tell({"type": "lianhuan.tool", "name": d.get("name", ""),
                                    "ok": d.get("ok") is not False,
                                    "done": d.get("type") == "tool_done"})
                        if d.get("type") == "tool_done":
                            tools.append({"name": d.get("name", ""), "ok": d.get("ok", True),
                                          "err": (d.get("err") or "")[:120]})
                        continue
                    if d.get("type") != SAY:
                        continue
                    line = (d.get("text") or "").strip()
                    if not line:
                        continue
                    buf.append(line)
                    # 它认不了音频标签，所以神态在这儿剥干净（语气靠 speed/loudness）
                    clean, _ = speech.for_engine(line, "duplex")
                    if not clean:
                        continue
                    # ★ 0901：这儿原来发的是 `replacement.append`。原项目 0818 栽过一次
                    #   并且把结论写在了代码里：**replacement 只在上游模型正生成回复的窗口内有效，
                    #   我们 `response.cancel` 掐掉它的脑子之后，那个窗口就关了**。
                    #   而这条路正是「先 cancel 再发」—— 也就是说它多半根本不会出声，
                    #   只是这个功能从来没真跑过，所以没人发现。
                    #   改成原项目验过能用的那条：`speech_text_buffer.commit`。
                    #   ★ 而且**第一句一到就发**，不等整段收齐（原项目 0901 刚把这条也拉齐了）——
                    #   commit 排不了多句的队，所以是「第一句立刻发，剩下的攒着」，
                    #   等这一句播完再发第二次，最多两次。
                    if not spoken_first:
                        spoken_first = True
                        state["out"] = True
                        said_note(state, clean, time.time())   # 回声要跟这本账比
                        await mouth.say(clean, "say%d" % turn)
                    else:
                        rest.append(clean)
                    await tell({"type": "lianhuan.said", "text": line})
            except Exception as e:
                await tell({"type": "error", "error": "你的引擎那头出错了：" + str(e)[:140]})
            if turn != state["turn"]:
                return
            if rest:
                # 剩下的那几句：等第一句播完再发（commit 排不了队，提前发会顶掉正在播的）。
                # 上游报 `response.output_audio.done` 就是播完了。
                for _ in range(60):                       # 最多等 30 秒，别挂死
                    if turn != state["turn"]:
                        return
                    if state.get("spoken_done"):
                        break
                    await asyncio.sleep(0.5)
                if turn != state["turn"]:
                    return
                said_note(state, "\n".join(rest), time.time())
                await mouth.say("\n".join(rest), "say%dr" % turn)
            if buf:
                whole = "|||".join(buf)
                # ★ 0901：把 ‹心情 …› 抠出来记账、并从正文里清掉。
                #   文字聊天那条路一直这么做（core/server.py），电话这条路漏了 ——
                #   于是电话里记的心情**永远不入账**，记号还留在库里。
                #   untrusted 的口径跟文字那边一模一样：这一轮对方的话里要是也带了这个记号，
                #   整轮不记账，只清正文（靠比对文本鉴权是防不住会改写的一方的）。
                try:
                    from optional.homelife.routes import apply_marker as _mark
                    whole, _ = _mark(whole, "call", untrusted=("‹" in (text or "")))
                except Exception:
                    pass                          # homelife 没装就跳过，不是错
                said.append(whole)
                ok, why = should_land(turn, state["turn"], gen_at_start,
                                      getattr(_store, "generation", 0))
                if not ok:
                    print("[duplex] 这句不落库：" + why, flush=True)
                else:
                    _store.add_turn(StoredTurn(role="assistant", content=whole,
                                               tools=json.dumps(tools, ensure_ascii=False)
                                                     if tools else "",
                                               channel="call", call_id=call_id,
                                               session_id="call", ts=time.time()))

        async def to_up():
            """浏览器采到的 PCM 往那副耳朵送。"""
            while True:
                raw = await ws.receive_text()
                try:
                    m = json.loads(raw)
                except Exception:
                    continue
                b64 = m.get("audio") or m.get("d") or ""
                if b64:
                    await mouth.send_audio(b64)

        async def to_down():
            """那副耳朵／那张嘴出来的东西，翻成前端认的那套事件。
            ★ 两家在这儿已经是同一套了（ears.py 做的映射），所以下面这段跟是谁无关。"""
            job = None
            async for ev in mouth.recv():
                t = ev.get("type")
                if t == _ears.HEARD_STARTED:
                    # ★ 有人开口了。**原来这儿是无条件作废这一轮的** ——
                    #   不戴耳机时我自己的声音会绕回麦克风，上游照样报「有人开口了」，
                    #   于是我一说话就把自己掐掉（对方看到的是「说一半就没声音了」）。
                    #   现在分两种：我没在出声 → 照旧立刻让路；
                    #   我正在出声 → **先挂起**，等转写出了字再判是不是我自己。
                    if state.get("out"):
                        state["pending"] = time.time()
                    else:
                        state["turn"] += 1
                        if job and not job.done():
                            job.cancel()
                        await mouth.hush()
                        await tell({"type": "lianhuan.listening"})

                elif t == _ears.HEARD_DELTA:
                    # ★ 挂起的那一下，现在有字了，可以判了。
                    #   保质期 3 秒：过期就丢，别拿上一段的标志去判这一段的字。
                    d = (ev.get("text") or "").strip()
                    if state.get("pending") and time.time() - state["pending"] > 3:
                        state.pop("pending", None)
                    if state.get("pending") and state.get("out") \
                            and len(norm_txt(d)) >= ECHO_BARGE_MIN:
                        # ★ 门槛不能低：两三个字的时候转写还在飘（糊掉的回声头一片
                        #   经常写得面目全非），在那上头拍板等于掷骰子。
                        #   等一等 —— 对方说完那一下 HEARD_DONE 还会再判一次。
                        state.pop("pending", None)
                        if echo_of(state, d, time.time(),
                                   ECHO_BARGE_FLOOR, ECHO_BARGE_MIN)[0]:
                            print("[duplex] 是我自己的回声，不算打断：" + d[:24], flush=True)
                        else:
                            state["turn"] += 1
                            state["out"] = False
                            if job and not job.done():
                                job.cancel()
                            await mouth.hush()
                            await tell({"type": "lianhuan.listening"})

                elif t == _ears.HEARD_DONE:
                    text = (ev.get("text") or "").strip()
                    # ★★ 最要命的一道闸。原来这儿一点回声判断都没有：
                    #   一段纯回声会被画成对方的字幕、把正在生成的回复整轮作废、
                    #   掐掉正在念的音频，最后以「对方说的」身份落进库里 ——
                    #   也就是我在回答我自己。认出是回声就整轮丢掉，一个字都不往下走。
                    hit, src = echo_of(state, text, time.time()) if text else (False, "")
                    if hit:
                        print("[duplex] 这句是我自己的回声，不当对方说的：%s ← 我刚说过「%s」"
                              % (text[:40], src[:24]), flush=True)
                        state.pop("pending", None)
                    elif text:
                        state.pop("pending", None)
                        # ★★ 0901 补的缺口：这儿原来**只起新的，不掐旧的**。
                        #   短句（够不上 HEARD_DELTA 那道 5 字的打断闸，也够不上
                        #   6 字的回声闸）走到这儿时，在途那一轮既没作废也没被取消 ——
                        #   旧的 think() 照跑到底、should_land() 照样返回 True，
                        #   于是**两条 assistant 都落库**，而且旧的那条还会继续出声。
                        #   ★ 盯这件事的那条测试只 assertIn('state["turn"] += 1', src)，
                        #   那个字符串在上面两处早就有了，所以它永远绿 —— 假哨兵。
                        state["turn"] += 1
                        state["out"] = False
                        if job and not job.done():
                            job.cancel()
                        await tell({"type": "lianhuan.listening"})
                        await tell({"type": "lianhuan.heard", "text": text})
                        await mouth.hush()      # 掐掉它自己的脑子 —— 我们只要它的嘴
                        job = asyncio.create_task(think(text, state["turn"]))

                elif t == _ears.AUDIO:
                    await tell({"type": "lianhuan.audio", "audio": ev.get("b64")})

                elif t == _ears.SPOKEN:
                    state["spoken_done"] = True    # 上面那几句剩下的等的就是它
                    state["out"] = False
                    await tell({"type": "lianhuan.spoken"})

                elif t == _ears.ERROR:
                    await tell({"type": "error", "error": str(ev.get("message"))[:200]})

                elif t == _ears.CLOSED:
                    return

        await asyncio.gather(to_up(), to_down())
    finally:
        await mouth.close()


async def _first(ws) -> dict:
    try:
        raw = await asyncio.wait_for(ws.receive_text(), timeout=3)
        d = json.loads(raw)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}
