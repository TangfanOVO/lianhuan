# 按需带走

连环的应用与自写功能维护在**一个主仓库**，避免同一修复在十几个仓漂移；第三方完整实现保留各自上游仓库链接。
需要分类带走时，用机器可读清单（`lianhuan.layers.json`）和取件器生成独立目录。

## 先看，再拿

```bash
npm run packs:list
```

每一条都写着 **truth** —— 它真正完成了什么、没配外部服务时会怎样。
先读那一行，再决定要不要。

---

## 一 · 按功能带走

| 取件 ID | 是什么 | 形态 |
|---|---|---|
| `function/runtime` | 内核 · 起得来的最小一份 | 独立包 |
| `function/engines` | 引擎 · 接什么模型说话 | 独立包 |
| `function/localdata` | 本地账本 | 独立包 |
| `function/memory` | 连续性与记忆 | 独立包 |
| `function/hands` | 工具与执行结果 | 独立包 |
| `function/speech` | 神态与语气 | 独立包 |
| `function/views` | 聊天与记忆的视图 | 独立包 |
| `function/calls` | 打电话与全双工 | 应用切片 |
| `function/proactive` | 主动找你与提醒 | 独立包 |
| `function/homelife` | 写作 · 心情 · 梗库 · 玩具厅 | 独立包 |
| `function/homeplus` | 家什与台账 | 独立包 |
| `function/reading` | 共读 | 独立包 |
| `function/engawa` | Engawa 固定上游、安装器、MCP 白名单与檐廊入口 | 上游集成 |
| `function/kaomoji-drawer` | 颜文字抽屉 | 适配 |
| `function/qq-bridge` | 接一个聊天前端 | 适配 |
| `function/obsidian-memory` | 把记忆存进你自己的笔记库 | 适配 |
| `function/android` | 安卓外壳 | 应用切片 |

「独立包」＝自己能站住；「应用切片」＝离不开宿主，拿走的是那一段实现不是一个能跑的东西；
「适配」＝对某个外部上游的接法。

## 二 · 按外观和交互带走

| 取件 ID | 是什么 | 许可 |
|---|---|---|
| `frontend/tokens` | 配色与明暗 | MIT |
| `frontend/ambience` | 环境效果 | MIT |
| `frontend/water` | 水面待机 | MIT |
| `frontend/physics` | 丝线 · 纸夹 · 散摞 | MIT |
| `frontend/paper` | 纸的材质 | MIT |
| `frontend/parts` | 卡片 · 抽屉 · 面板 | MIT |
| `frontend/shelf` | 书架 | MIT |
| `frontend/glyphcloud` | 记忆字云 | MIT |
| `frontend/robot` | 桌面机器人的面板 | MIT |
| `frontend/ui-kit` | 前端积木总包 | MIT |
| `frontend/shell` | 完整前端壳 | AGPL-3.0-only |

★ 这几块是**纯前端**：零依赖、零网络、不认识后端。每块都有能双击打开的 `demo.html`。

## 三 · 组合方案

| 取件 ID | 是什么 |
|---|---|
| `profile/whole-home` | 整屋 |
| `profile/local-home` | 不接模型的本地版 |
| `profile/frontend-only` | 只要前端 |
| `profile/appearance-only` | 只要外观和交互 |
| `profile/full-source` | 完整源码（直接 clone） |

---

## 取走

```bash
# 只要一块视觉积木
npm run pack:take -- frontend/ambience /absolute/new-folder

# 要整套前端积木（九块 ＋ 最小外壳示例）
npm run pack:take -- frontend/ui-kit /absolute/new-folder

# 要一个不接模型也能跑的本地版
npm run pack:take -- profile/local-home /absolute/new-folder
```

**目标必须是绝对路径，而且必须还不存在。** 取件器不往已有目录里倒东西，
中途出错会把目标整个删掉重来 —— 半截的副本比没有更坏。

取完了在副本里：

```bash
cd /absolute/new-folder
cat TAKEAWAY.md      # 带上了什么、能干什么、不能干什么
npm install && npm run build && npm test    # 纯前端那几种
```

## 不会给你什么

- `.env`、密钥、证书、keystore
- 数据库、真实聊天、登录态
- `node_modules` / `dist` / `build` / 缓存 / `.bak` 备份 / 验收报告
- **界面 ≠ 已接通。** 带了通话界面不代表语音能用 —— 每条的 `truth` 才算数

## 推荐的完整上游

- 轻量共读前端与实现保留；完整阅读器见 [Readest](https://github.com/readest/readest)。
- 网易云共听保留连环前端；完整实现见 [music-together](https://github.com/Yueby/music-together)。
- 这些链接是因为上游更完整，不表示本仓把自己的正常功能藏起来。

## 许可

| | |
|---|---|
| 完整连环应用 | **AGPL-3.0-only** |
| `blocks/` 那几块纯前端积木 | **MIT**（各自目录里有 LICENSE） |

取件器按内容自动定根许可：**全是 MIT 就给 MIT；只要混进一条 AGPL，整份就是 AGPL。**
宽的不能盖住严的，反过来可以。

MIT 积木装回完整应用里的时候，完整应用**照旧**按 AGPL 分发 —— 那不冲突，
AGPL 的东西消费 MIT 的东西本来就合法。

第三方组件保留它们各自的许可与署名（见 `THIRD_PARTY_NOTICES.md`），
不会因为整仓是 AGPL 就把上游的 MIT / Apache / 字体 / 图标声明删掉。

## 为什么 AGPL

短版：想要「别人别拿去闭源卖」，而 CC BY-NC 那类**不是开源许可**，
边界模糊到吓人，结果是想卖的照样卖、想好好用的不敢用。长版在 `docs/LICENSE-WHY.md`。
