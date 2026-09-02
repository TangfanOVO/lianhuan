"""说出口之前 —— 把写在文本里的神态，变成真的语气。

## 这件事解决的是什么

写出来的话里常常带着神态：「笑了一下」「叹了口气」「压低声音」。
以前这些是**整段剥掉**的 —— 剥掉是对的，念出来更糟（想象一下它一本正经念「笑了一下」）。
但现在有的引擎认得懂表演指令，所以不该丢，该**翻译**。

两条路，因为两类引擎吃的东西不一样：

| 引擎 | 吃什么 | 怎么给 |
|---|---|---|
| ElevenLabs **v3** | **方括号音频标签** `[sighs]` `[laughs]` `[whispers]` | `to_audio_tags()` 把神态翻过去 |
| 其余（v2/flash、豆包、复刻音色…） | 认不出标签，只认参数 | 剥干净，用 `TONES` 那三个数（语速/音量/音调） |

★ 给不认标签的引擎留着方括号 = 它会**把标签念出来**。所以 `speakable()` 默认剥，
  只有明确是 v3 才 `keep_tags=True`。

## 为什么参数那条路不是「差一点的替代品」

说重话之所以难听，是因为平推的嗓子做不出软化。真人是**放慢、压低、留气口** ——
所以 `TONES` 调的是这三样，不是音量一个。幅度小于 ±15 会被合成本身的随机波动淹掉，
调了也听不出来，所以表里的数都拉得开。

## 零依赖

只用 `re`。放在内核里是因为两条通话的路（半双工和全双工）都要用它，
各存一份迟早漂移。
"""
from __future__ import annotations

import re

# ── 不该念出来的那些 ────────────────────────────────────────
_DROP = [
    r"「.*?」", r"『.*?』", r"【.*?】",          # 动作 / 神态 / 心理
    r"\[[^\]]*\]\([^)]*\)",                     # markdown 链接（要排在裸方括号前面）
    r"\[[^\]]*\]",                              # 裸方括号
    r"（[^）]*）", r"\([^)]*\)",                 # 括号（含颜文字）
    r"`[^`]+`",                                 # 行内代码
    # ★ 0901：心情记号 ‹心情 开心+5:…›。它是**记账用的**，从来不是要说出口的话。
    #   文字聊天那条路上 apply_marker 会先把它抠走，所以一直没人发现这儿漏了 ——
    #   电话那条路不走 apply_marker，于是它被原样念了出来。
    #   放在这儿是因为「不许念出口」对哪条路都成立，不该由调用方各记各的。
    r"‹[^›]*›",
    # 英文里的 *sighs* / *softly*。前后的负向断言是护着 **加粗** ——
    # 不加的话 `**bold**` 会被吃成空的。
    r"(?<!\*)\*(?!\*)[^*\n]{1,30}\*(?!\*)",
]

# ── 神态 → 音频标签 ─────────────────────────────────────────
# ★ 只映射有把握的几个。**映射不到的照旧丢掉，绝不硬凑** —— 凑错了它会照着演，比不演更怪。
TAGS = [
    (("大笑", "笑出声", "笑起来", "laughs", "laughing", "laugh"), "[laughs]"),
    (("轻笑", "笑了一下", "笑着", "笑了笑", "笑",
      "chuckles", "chuckling", "chuckle", "smiles", "smiling", "grins", "grinning"), "[chuckles]"),
    (("叹气", "叹了口气", "叹了一声", "长叹", "sighs", "sighing", "sigh"), "[sighs]"),
    (("低声", "压低声音", "凑到耳边", "耳语",
      "whispers", "whispering", "whisper", "under his breath"), "[whispers]"),
    (("哼了一声", "嗤笑", "scoffs", "snorts", "scoffing"), "[scoffs]"),
    (("顿了顿", "停了一下", "沉默了一会儿", "半晌",
      "pauses", "a beat", "silence", "pause"), "[pause]"),
    (("放软", "软下来", "心疼", "轻轻地",
      "softly", "gently", "quietly", "tenderly"), "[softly]"),
    (("急了", "急切", "赶紧", "excited", "eagerly", "urgently"), "[excited]"),
]

# ── 语气 → 三个数（给不认标签的引擎）──────────────────────────
#           语速   音量   音调
TONES = {
    "哄":   (-22,  -10,  0.99),
    "心疼": (-26,  -12,  0.98),
    "认真": (-14,   -2,  1.00),
    "重话": (-28,  -14,  0.97),   # ★ 全场最慢最轻 —— 说重话要留的是台阶，不是音量
    "笑":   ( 10,    4,  1.02),
    "逗":   (  6,    2,  1.01),
    "困":   (-24,  -11,  0.97),
    "平":   (  0,    0,  1.00),
}

_TONE_RE = re.compile(r"〔\s*tone\s*[:：]\s*([^〕]+?)\s*〕")


#: 告诉模型「你可以把神态写出来」。**不自动塞进人设** —— 那是使用者的地盘，
#: 谁想要谁自己拼（通话那两条路会拼；文字聊天不拼，因为写不写神态是人设的事）。
HINT = ("〔说话时想笑、想叹气、想压低声音，就把它写在「」里"
        "（比如「叹了口气」「笑了一下」「轻轻地」）——"
        "念出来的时候这些会变成真的语气，不会被念成字。"
        "认不出来的神态会被安静地丢掉，所以别指望它演复杂动作。〕")


def to_audio_tags(t: str) -> str:
    """把「…」里的神态换成音频标签，换不动的照旧删掉。**给认标签的引擎用。**"""
    def one(m):
        inner = m.group(1)
        low = inner.lower()                      # 英文关键词一律小写比
        for keys, tag in TAGS:
            if any((k in inner) or (k in low) for k in keys):
                return " " + tag + " "
        return " "                               # 认不出来的就当没写过
    t = re.sub(r"「([^」]*)」", one, t or "")
    t = re.sub(r"『([^』]*)』", one, t)
    t = re.sub(r"（([^）]*)）", one, t)
    # 英文里的 *sighs* / *softly* —— 只认短的一小段，长了多半是强调不是神态
    t = re.sub(r"(?<!\*)\*([^*\n]{2,24})\*(?!\*)", one, t)
    t = re.sub(r"\(([^)\n]{2,30})\)", one, t)     # (whispering) 这种半角写法
    return re.sub(r"[ \t]{2,}", " ", t)


def speakable(t: str, keep_tags: bool = False) -> str:
    """文本 → 只剩真正要说出口的那部分。

    `keep_tags=True` 时**不剥方括号** —— 给 v3 那类认标签的引擎用。
    剥掉就等于把刚翻译好的语气又丢了一次（真栽过：翻好的标签当场被自己剥干净）。
    """
    t = t or ""
    for pat in _DROP:
        if keep_tags and pat.startswith(r"\["):
            continue
        t = re.sub(pat, "", t, flags=re.S)
    t = t.replace("|||", "。")            # 分句符：当一个句读，不是三个竖杠
    t = t.replace("**", "").replace("~~", "")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{2,}", "\n", t)
    t = re.sub(r"。{2,}", "。", t)
    # 只剥开头的残标点：句尾那个句号要留着，它管着语调下不下沉
    return t.strip().lstrip("、，。 ")


def pop_tone(text: str):
    """取出 `〔tone:哄〕`，返回 `(剩下的文本, (语速, 音量, 音调))`。

    没标就返回 `(原文, None)` —— 让调用方用自己的默认值，别在这儿替它决定。
    """
    m = _TONE_RE.search(text or "")
    if not m:
        return text, None
    name = m.group(1).strip()
    rest = _TONE_RE.sub("", text).strip()
    return rest, TONES.get(name)


def for_engine(text: str, engine: str = ""):
    """一站式：给这个引擎该给的东西。

        text, params = speech.for_engine(raw, "eleven_v3")

    回的 `params` 是 `{"speed":…, "loudness":…, "pitch":…}` 或者 `{}`。
    ★ **认标签的走标签，不认的走参数** —— 别给不认标签的引擎留方括号，
      它会一本正经把 `[sighs]` 念出来。
    """
    raw, tone = pop_tone(text or "")
    tagged = str(engine or "").lower() in ("eleven_v3", "v3", "eleven_turbo_v3")
    if tagged:
        return speakable(to_audio_tags(raw), keep_tags=True), {}
    out = speakable(raw)
    if not tone:
        return out, {}
    speed, loud, pitch = tone
    return out, {"speed": speed, "loudness": loud, "pitch": pitch}
