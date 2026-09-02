# 上游来源

## 这套界面

纸面、秋溪、枫叶、丝线叠卡、重点色系统与房间排布是本项目的界面系统，源码与可拆前端积木均在仓库中。
默认角色名是中性的「伙伴」；配色、图标和环境效果可在 `blocks/base` 与 `blocks/ambience` 中替换。
演示数据全部虚构，不对应真人（见 [EXCLUDED.md](EXCLUDED.md)）。

## 别人的东西

这个项目里凡是**参考、改造、适配**别的开源项目做出来的功能，都在这儿记着。

**规矩**：能合法再分发且已完成的实现直接随包提供；上游更完整或需要独立安装时才指路。
本项目适配的问题请在本仓反馈，不要让上游作者替本仓实现背书。

> 状态说明：`已核` = 许可证查过了；`待核` = 还没查，用之前自己确认一下。
>
> ★ 光在这张表里写一句「MIT」是**不够的** —— MIT 自己要求把版权声明和许可正文
>   一起随发行带上。正文和逐个组件的版权行在 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 直接依赖（不改，正常用）

| 项目 | 用在哪 | 许可 | 状态 |
|---|---|---|---|
| [ThreeUI](https://github.com/MengTo/threeui)（Meng To） | 记忆字云：采样与形变配对的算法出自它的 Text on a Path II — Study 08「Morphing Glyph Cloud」；连线/透视深度/拾取高亮是本项目新增 | **MIT**（0830 核实：作者已开源，Community 部分含此件） | 已核 · 内置 |
| p5.js | 水面待机 | LGPL-2.1 | 已核 · 走 CDN，不打包；加载失败会自动降级 |
| html2canvas | 聊天存长图 | MIT | 已核 |
| Tabler Icons | 界面上几乎所有线条图标 | MIT | 已核 · 全部内联成 SVG |
| Font Awesome Free 6 | 一枚图标 | CC BY 4.0 | 已核 · **要署名**，见下 |
| LXGW WenKai | 中文字体 | SIL OFL 1.1 | 已核 |
| [fuyue-kaomoji-drawer](https://github.com/TangfanOVO/fuyue-kaomoji-drawer) | 颜文字抽屉（React 组件＋MCP，整套内置在 optional/kaomoji_drawer/） | **MIT** | 已核 · 上游作者自己发布的开源项目，直接内置 |

## 内置适配包（随仓提供）

| 上游 | 我们做了什么 | 许可 | 状态 |
|---|---|---|---|
| [Eveacla11/ears](https://github.com/Eveacla11/ears) | 通话的**上行链**（录音上传 → 服务端识别 → 出情感标签）整条参考它写的 | **MIT** | 已核 |
| [Pyruslili/Nocturne-Memory-Core](https://github.com/Pyruslili/Nocturne-Memory-Core) | 记忆分层里的「近场日记」那一层：每天蒸一篇，按递减字数配额拼进注入，第八天自然掉出去 | **MIT** | 已核 |
| [nonchaiovo/journey-cards](https://github.com/nonchaiovo/journey-cards) | 出门页的数据契约照它做的 | **MIT** | 已核（0831 实核：`Copyright (c) 2026 nonchaiovo`） |
| [tsuru0805/engawa-mcp](https://github.com/tsuru0805/engawa-mcp) | 固定提交的一键安装器、MCP 接入、12 项白名单与檐廊前端；运行时只落在本机 `.runtime/` | **MIT** | 已核 · 适配与许可随仓，安装后直接用 |

★ 通话其实有**两条**上行路，别混：
`ears` 那条是「录一段传上去再识别」；主力那条是**豆包端到端全双工**（一条 WebSocket 里同时做识别和发声），
两者的接法完全不同。见下。

## 要 key / 要花钱的外部服务

| 服务 | 干什么 | 注意 |
|---|---|---|
| 端到端全双工语音（如火山「豆包」的 duplex realtime dialogue） | 一条 WebSocket 里同时做识别和发声 —— 通话的主力路子 | `optional/callkit` 已含浏览器到自建服务、再到供应商的转发实现。key 在 **设置 › 功能包** 里填，只存在服务端 `data/secrets.json`；保存不等于厂商验通，必须实际拨打一轮确认 |
| ElevenLabs 流式转写与合成 | 英文实时转写、声音合成与打断 | 同上；实现与错误态在 `optional/callkit`，实际可用性取决于账号、模型、区域和额度 |

本仓包含适配实现和离线契约测试，永远不含 key。没有当前设备与有效账号证据时，只能写“实现/契约通过”，不能写成真厂商通话通过。

★ 全双工那条有个反直觉的用法值得记：它自己带脑子，但你**不要**它的脑子 ——
一收到「这句听完了」就立刻取消它的回复，让你自己带记忆的模型来答，
再把答案塞回去让它发声。否则你会有两个 AI 在抢话。


## 我们自己写的

这几块不是抄来的，是这个项目自己长出来的：

- **说话不掉线**：回复的生死不绑在 HTTP 连接上。模型在后台跑到说完，
  页面只是观众席 —— 刷新、切后台、网络抖动，回来能从头补播，一个字不丢。
- **记忆召回与注入**：多路召回 ＋ 分段拼装。
- **丝线叠卡**：Verlet ＋ 位置约束的绳子物理，卡片被线牵着。只算不画，渲染只有一条 SVG path。
- **枫叶水面待机**：开屏那条秋溪 —— 全程序化绘制（p5 画布），零图片资产，滑动解锁。
- **动效规格**：一整套参数，不是随手写的过渡。
- **通话嵌成一层**：回聊天不挂断。

## 保留前端、推荐更完整上游

本项目自己的需求较轻，因此以下两项保留连环这套前端和接口位置，同时诚实推荐完整实现：

- 共读：[Readest](https://github.com/readest/readest)（AGPL-3.0-or-later）。本仓内置轻量 txt 分章、批注和章节聊天，不冒充完整电子书阅读器。
- 网易云共听：[music-together](https://github.com/Yueby/music-together)（AGPL-3.0）。本仓保留一起听的前端，不打包非官方音源接口。

## 署名

- Font Awesome Free 6 —— CC BY 4.0，署名要求见 https://fontawesome.com/license/free
