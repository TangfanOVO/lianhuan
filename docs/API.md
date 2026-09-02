# API 契约

后端只需要实现这几条。**照着做，你可以把后端换成任何东西** —— 自己写的、
别人的服务、或者干脆不要后端（数据留浏览器里）。

`core/server.py` 本身就是一份参考实现（七百多行，一半是注释），照着抄最快。

---

## 说话

### `POST /chat`

```jsonc
// 请求
{
  "message":    "你好",
  "session_id": "可选，续上一段会话",

  // ── 上下文边界（0831 加的）。不带这几个＝普通文字聊天，行为跟以前一样 ──
  "src":     "call",        // 可选。'call' = 这一轮走电话那条线
  "call_id": "一通一个",     // 可选。**每通电话一个**，挂断再拨必须换一个新的
  "machine": false          // 可选。true = 这句是**程序拼给模型看的**，不是人说出口的话
}
```

**为什么要有后面这三个**（0831 自查，捕获真实请求验过的）：

后端原来只认 `message` 和 `session_id`，取上下文靠一条光秃秃的
`ORDER BY id DESC LIMIT 25`。于是：

- 打电话时读得到**三天前的文字聊天**；「新电话是新线程」这句话在请求里不成立
- 程序拼的场景提示（「翻一下空间」那种）被当成**人说过的原话**读回去
- 同一批话既写进 `system` 又写进 `history`，**进了两遍**，模型会以为人在重复自己

所以：

| 字段 | 管什么 | 不管什么 |
|---|---|---|
| `src` / `call_id` | 这一轮读**哪条线**的上下文。电话只读**本通**，文字只读文字 | — |
| `machine` | 这句算不算「人真说出口的话」。`true` 的永远不进上下文 | 不管界面 |

★ `machine` 和界面上的「藏起来」是**两件事**，别合并：用户也会把自己真说过的一句
收起来（`POST /api/chat/{id}/hide`），那只是不想看见，不是没说过。
合并的话，用户收起来的真话就从模型的上下文里消失了。

★ 实现这套契约的后端，取上下文时要过滤 `spoken=1` 并按 `channel`/`call_id` 分线；
`GET /api/export` 的每条 turn 会带 `tools`/`hidden`/`spoken`/`channel`/`call_id`，
`POST /api/import` 必须把它们原样写回去（漏掉 `tools` 就等于把工具审计痕迹抹了）。
老的导出文件没有这几个字段，导入时给默认值即可。

回一条 **SSE 流**（`text/event-stream`）。每条事件长这样：

```
data: {"type":"…", …}\n\n
```

| type | 字段 | 什么意思 |
|---|---|---|
| `stage` | `text` | 他在干嘛。**一行人话**，不是转圈菊花 |
| `os` | `delta` | 思考链的增量 |
| `s` | `text` | **一句话**（完整的一句，不是字符增量） |
| `tool_live` | `name` | 工具刚启动，名字先报出来 |
| `tool` / `tool_done` | `name` | 工具在跑 / 跑完了 |
| `error` | `text` | 出事了，**要老实说** |
| `done` | `session_id` | 说完了 |
| `hb` | — | 心跳，前端忽略 |

★ **`s` 是「一句」不是「一段」。** 一条回复由好几句组成，一句一个气泡，边想边冒。
落库时用 `|||` 把几句连起来存，前端读的时候拆回去 —— 这样刷新前后看到的一模一样。

★ **长考时必须发心跳。** 一分钟不吐字节，中间的反向代理会按「空闲」把连接掐了。

### `GET /chat/attach?job=<id>&after=<n>`

同样的 SSE，但**从第 n 个事件续播**。用来治「刷新 = 处决」：

模型跑在后台任务里，SSE 只是观众席。人刷新 / 切后台 / 断网，只死观众不死他；
回来接着看，一个字不丢。**这是这个项目最值得抄的一块。**

### `GET /api/chat/active` · `POST /api/chat/stop`

前者回还没说完的任务（回前台先问一嘴），后者掐掉一条。

---

## 数据

| | |
|---|---|
| `GET /api/turns?limit=` | 最近的对话，**时间正序** |
| `GET /api/persona` · `POST` | 人设 `{ai:{name,text}, human:{name,text}}` |
| `GET /api/settings` · `POST` | 设置。★ **key 一律不出这道门**，连读都不行 |
| `GET /api/export` | 整个家打包成 JSON。不加密不混淆 |
| `POST /api/import` | 导入。`mode: "merge"`（默认）/ `"replace"`（要带 `confirm:true`） |

### 搬家格式

```jsonc
{
  "lianhuan": 1,
  "persona": { "ai": {...}, "human": {...} },
  "memories": [ { "content": "…", "layer": "L1", "tags": [], "ts": 0 } ],
  "turns":    [ { "role": "user", "content": "…", "think": "", "ts": 0 } ]
}
```

**故意做得好手写。** 你自己的东西你得看得懂 —— 想从别的地方导进来，
写个小脚本转成这个形状就行。

---

## 三个不能省的规矩

**① 记忆在主链路上，不是工具。** 每次说话之前无条件先过一遍召回，
把该记得的直接摆在模型面前。做成工具的话，它得先意识到自己该记得什么 ——
可绝大多数时候它根本不知道自己忘了。

**② 落库在收尾里，不在 SSE 里。** 人关了页面那段也必须走，
否则「说到一半被刷新」= 那一轮全丢。

**③ 没接通就说没接通。** 引擎有两个标志位：
`ready`（点了有反应吗）和 `stub`（那个反应是真的吗）。
两种都要在界面上标出来，**不许拿假数据冒充能用**。

---

## 不要后端行不行

行，两种走法：

- **本机模型**（Ollama / LM Studio）：引擎指向 `localhost`，数据放浏览器里
- **本机 CLI**：用你已经登录的官方客户端当子进程，不用 key

这两种都没有「key 要藏哪儿」的问题 —— 那正是这一薄层后端存在的唯一理由。

---

## 蒸馏（对话 → 记忆）

四段，缺一段库就会越长越脏：**提取 → 审批 → 去重 → 升层**。

### `GET /api/distill`

```jsonc
{ "config": { "every_turns": 20, "max_per_run": 3, "auto_keep": false,
              "dup_at": 0.75, "to_l2": 5, "to_l3": 15 },
  "cursor": 34, "turns": 36, "behind": 2,
  "latent": { "new": 1, "kept": 3, "dropped": 2 },
  "layers": { "L1": 5, "L2": 3, "L3": 1 } }
```

`behind` ＝ 还没提过的对话有几轮。攒够 `every_turns` 就会在后台自己跑一趟。
**`every_turns: 0` ＝ 彻底关掉**（它自己也要花模型的钱，所以必须关得掉）。

### `POST /api/distill/run` `{force?: true}`

跑一趟：拿没提过的对话让模型挑几条 → 查重 → 落进「潜在」。
★ **不入库**。回 `{ok, picked, auto_kept, cursor, read_turns}`。

### `GET /api/latent?view=new|kept|dropped`

```jsonc
{ "items": [{ "id": 7, "content": "他不吃香菜", "layer": "L2",
              "why": "忌口，长期事实",
              "dup_of": 3, "dup_score": 0.86, "dup_content": "他点外卖每次备注不要香菜",
              "status": "new", "ts": 1788… }],
  "counts": { "new": 1, "kept": 3, "dropped": 2 } }
```

`dup_of` 是**提示，不是动作** —— 系统从不自动合并，合不合是人的事。

### `POST /api/latent/{id}/keep` · `/drop` · `/unkeep`

`keep` 落进记忆库；`drop` 沉掉；`unkeep` 撤回（把入库那条删掉，候选退回待审）。
★ 敢做 `unkeep`，是因为 `keep` 只是照抄一条进库 —— 没合并没改写，撤得干净。

### `POST /api/distill/promote`

够数的往上升一层（L1→L2→L3）。**升层不改内容，所以不问人。**
依据是「被召回过几次」：召回发生在主链路上，每次 `build_injection` 用到哪几条就记一笔。

### `POST /api/distill/config`

改上面那六个阈值中的任意几个，回改完的整份配置。

---

## 通话

### 两条路，不是一条

> ★ **这一节 0831 重写过。** 原来写的是另一套架构（模块在 `optional/duplex`、
> 上游自己当脑子、人设塞进 `session.instructions`、WS 是 `/api/duplex/ws`、
> 落库 `session_id=duplex`），而且链到一个**不存在的** `optional/duplex/README.md`。
> 那套实现早就不在了。外部验收（0831）抓的 P1-06。**照代码改文档，不是改代码迎合文档。**

| | 轮流说（`optional/callkit`） | 能插话 / 全双工（`optional/callkit/duplex.py`） |
|---|---|---|
| 谁在想 | 你配的引擎（DeepSeek / CLI / …） | **也是你配的引擎** —— 上游只借耳朵和嘴 |
| 怎么走 | 录音 → 转写 → `/chat` → 合成 | 音频进 → 上游 ASR 出字 → **立刻掐掉上游的脑子** → 问你的引擎 → 它的回复交回上游那张嘴念 |
| 能插话吗 | **不能** | **能**（上游一报「听见你开口了」，这一轮当场作废） |
| WebSocket | — | `/api/call/duplex` |
| 记忆和人设 | `build_injection` 进 `/chat` | 同一个 `build_injection`（`here="call"`）＋ 心情注入，**故意不给上游 instructions** |
| 上下文 | `channel=text` 的 48 小时段 | **只读本通电话**（`channel=call` ＋ 本通 `call_id`，最近 16 条） |
| 落库 | `channel=text` | `channel=call` ＋ 每通一个 `call_id`；开场旁白 `spoken=0` |
| 它的手 | `core/hands.py` 那批 | **同一批**（引擎自己在这一轮里执行），工具结果落进 `turns.tools` |
| 音频 | MediaRecorder（webm/opus）就够 | 必须 AudioWorklet 采 **16K 裸 PCM**；回来的是 24K |

**没有替换关系。** 没有豆包 key 的人照样用上面那条。

#### 全双工那条 WebSocket 上跑什么

浏览器 ←→ 这一层 ←→ 语音服务。**中继把上游协议翻译成一套自己的事件**，
浏览器只认这一套（两边各说一套是 0831 抓到的 P0-01：声音通了，字幕和转录一个都不显示）：

| 事件 | 谁发 | 什么意思 |
|---|---|---|
| `lianhuan.open` / `lianhuan.close` | 前端音频层自己 | 连上了 / 断了 |
| `lianhuan.listening` | 中继 | 上游听见你开口了 —— 把已经排上的声音停掉 |
| `lianhuan.heard` `{text}` | 中继 | 你刚说的那句转写出来了 |
| `lianhuan.said` `{text}` | 中继 | 他这一句（字幕） |
| `lianhuan.audio` `{audio}` | 中继 | 一块 24K PCM，接着播 |
| `lianhuan.spoken` | 中继 | 这一句念完了 |
| `lianhuan.tool` `{name, ok, done}` | 中继 | 他去动手了 / 动完了 |
| `error` `{error}` | 两边都可能 | 出错了，照实说 |

★ 加事件要**两边一起加**。`tests/test_duplex.py` 里有一张对账表：
中继发的每一种，页面或音频层必须有人接；页面也不许等没人发的事件。

★ **语气**：`speech.HINT` 会让模型写神态，`speech.for_engine(..., 'duplex')` 把神态从文本里
剥干净再交给上游。**语速/音量/音调那几个参数目前没有接到上游**（豆包全双工的协议这边还没做映射）
—— 也就是说全双工现在是**只有文本语气，声音参数不变**。`[sighs]` 那类标签只对轮流说的
ElevenLabs TTS 有效。别在界面上宣称神态会变成真实声音。

### `POST /api/listen` `{dataURL}` → `{text, feel}`

录音转文字。目前只有 ElevenLabs（`scribe_v1`），会按当前语言带上 `language_code`。

### `POST /api/tts` `{text, lang?}` → `audio/mpeg`

合成。**按语言挑引擎，不是按厂商**：

```
中文 → 豆包优先（中文听着更自然），没贴就用 ElevenLabs 的多语种模型
英文 → ElevenLabs 优先，没贴就用豆包
```

`lang` 不传就用当前设置。`TTS_PROVIDER` 环境变量写死了哪家的话，照他的来。

### `GET/POST /api/call/lang`

```jsonc
{ "lang": "zh", "zh": "volc", "en": "eleven",
  "eleven": true, "volc": true, "ok": true, "listen": "eleven" }
```

界面上**只让人选中文还是英文**，不问他用哪家。但 `zh`/`en` 这两个字段要照实显示 ——
只贴了一家 key 时两种语言都走那家，**人选了「英文」却不知道底下没接，那就是界面在骗他**。

⚠ 别跟 `/api/voice` 混：那是「音色调校」（语速/音高/音色/用谁的嗓子）那一族，另一件事。
（同一个名字登记两次的话，EP 表里后一条会**静默覆盖**前一条 —— 这个坑在这个项目里踩过两次。）

### ElevenLabs 的 key：几条真踩出来的

这几条不是从文档抄的，是撞出来的。程序在报错里会直接说，这儿再写一遍：

| 现象 | 真正的原因 |
|---|---|
| **400** `API key must be exactly N characters` | **复制不全**。key 只在**创建那一次**完整显示，后台再点「复制」拿到的不一定是整串 —— 重新建一把，用 `sk-` 开头那串完整的 |
| **401** 认不出这把 key | key 无效／过期／被停用／已经轮换过了；**也可能是权限没勾全** |
| 权限勾了还是 401 | 整条电话链至少要 **Voices read ＋ Text to Speech ＋ Speech to Text**。实在调不通就先建一把**不限制权限**的试，通了再往回收 |
| **403** | 多半是 IP 白名单不匹配 —— **白名单的事是 403 不是 401**，别对着 401 查白名单 |
| `'ascii' codec can't encode…` | key 里混进了中文或全角字符（粘贴时带进来的）。程序会在发出去之前拦下来说人话 |

---

## 全双工（选装）

```
GET  /api/duplex                            → {ok, missing, note}
WS   /api/call/duplex                       → 第一帧 {voice?}，之后走上面那张事件表
GET  /api/duplex/web/duplex.js|demo.html    → 浏览器那半 ＋ 一个自检页
```

★ **0831 更正**：这里原来写的是 `/api/duplex/ws`「之后原样对拷」——
实际路径是 `/api/call/duplex`，而且**不是原样对拷**：中继把上游协议翻译成
`lianhuan.*` 那一套（见上面那张表）。原样对拷是早先那版的做法，早就不是了。

**为什么必须是服务端代理**：① key 不进浏览器 ② 人设和记忆得有人拼（浏览器拿不到记忆库）
③ 工具得有人执行 ④ **上游那个脑子得有人去掐**（ASR 一出字就发 `response.cancel`，
不然它会自己抢答，你的人设和记忆全用不上）。

挂断后这一通的文本落进 `turns`：`channel="call"` ＋ 这一通自己的 `call_id`
（★ 不是早先写的 `session_id="duplex"`，那样所有电话共用一个线程，挂断再拨还接着上一通）。
开场那句是程序拼给模型看的，落库时 `spoken=0` —— 不算「你说过的话」。
工具结果跟着这一轮存进 `turns.tools`，刷新之后还追得了证。

### 自检页

`/api/duplex/web/demo.html` 分两段验：**先验音频那半**（不用 key、不连外网，
看采样率是不是 16000、放回来听听），再验整条链路。
接这条路最容易卡在音频格式上，所以那一段单独拎出来能自己跑。

---

## 语气：写在文本里的神态，变成真的语气

`core/speech.py`（零依赖，两条通话的路共用）。

写出来的话里常带神态：`「叹了口气」我知道了。`
以前这些是**整段剥掉**的 —— 剥掉是对的，念出来更糟（想象它一本正经念「叹了口气」）。
现在有的引擎认得懂表演指令，所以不该丢，该**翻译**。

| 引擎 | 吃什么 | 结果 |
|---|---|---|
| ElevenLabs **v3** | 方括号音频标签 | `[sighs] 我知道了。` |
| 其余（v2 / flash / 豆包 / 复刻音色） | 认不出标签 | `我知道了。` ＋ 语速音量音调三个数 |

★ **给不认标签的引擎留方括号 ＝ 它会把「[sighs]」念出来。** 所以默认剥，
只有明确是 v3 才留。开 v3：`ELEVEN_MODEL=eleven_v3`（贴在功能包页或环境变量）。

### 认得出来的神态

`[laughs]` `[chuckles]` `[sighs]` `[whispers]` `[scoffs]` `[pause]` `[softly]` `[excited]`

中英都认：「叹了口气」「压低声音」「顿了顿」，或者英文的 `*sighs*` `(whispering)`。
★ **认不出来的照旧丢掉，绝不硬凑** —— 凑错了它会照着演，比不演更怪。

### 另一条路：`〔tone:xxx〕`

不认标签的引擎走这个。`〔tone:重话〕这次真的不行。` →
文本剥干净，外加 `{speed:-28, loudness:-14, pitch:0.97}`。

八档：`哄 心疼 认真 重话 笑 逗 困 平`。

为什么调三个数而不是只调音量：**说重话之所以难听，是因为平推的嗓子做不出软化**。
真人是放慢、压低、留气口。（幅度小于 ±15 会被合成本身的随机波动淹掉，所以表里的数都拉得开。）

### 怎么用

```python
from core import speech
text, params = speech.for_engine(raw, "eleven_v3")   # → 带标签的文本，params 是空的
text, params = speech.for_engine(raw, "volc")        # → 干净文本 ＋ {"speed":…,"loudness":…,"pitch":…}
speech.HINT      # 告诉模型「神态可以写出来」的那句话。通话时拼进去，文字聊天不拼
```

`HINT` **不自动塞进人设** —— 写不写神态是使用者人设里的事，不该我们替所有人决定。
通话那两条路会拼上它（不然它不知道能这么写，这套翻译就白做了）。
