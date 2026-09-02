"""任务寄存器 —— 治「刷新 = 处决」。

## 这块治的是什么病

最直觉的写法是把模型进程放在 SSE 生成器肚子里。那样有个隐蔽的坑：
人一刷新 / 切后台 / 网络抖一下，服务端框架会掐掉生成器，`finally` 里就把
**正在说话的模型当场杀了** —— 半截话落库，而前端还在满屏安慰「后端还在跑别重发」（它信错了）。

现在的做法：**每条消息一个 job**，模型由后台任务持有、自己活到说完；
SSE 只是观众席，观众走了只死观众。回来 `attach(after=N)` 从第 N 个事件续播，一个字不丢。

这段是从原项目整段搬过来的（那边跑了几个月），只去掉了它特有的分房间逻辑。

## 用它

    job = registry.new("你好")
    job.task = asyncio.create_task(registry.run(job, engine, turn, on_done=落库))
    return StreamingResponse(registry.watch(job), media_type="text/event-stream")

    # 断了再回来：
    return StreamingResponse(registry.watch(job, after=已看过几个), ...)
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import AsyncIterator, Awaitable, Callable

from .engines.base import Engine, Turn
from .protocol import DONE, ERROR, GONE, HEARTBEAT, RECV, SAY, sse, strip_marks


def _kind(event: str) -> str:
    """从一条 SSE 里读出事件类型。

    ★ 别用 `'"s"' in event[:16]` 那种切片匹配 —— 前 16 个字符只到 `data: {"type": "`，
      名字还没开始，判断永远是 False。这个坑真咬过：AI 说的话一条都没落库，
      而界面上一切正常（因为屏幕上的气泡是流式来的，不是从库里读的），
      直到刷新页面才发现半边对话消失了。解析一次，别数字符。
    """
    try:
        return json.loads(event[6:]).get("type", "")
    except Exception:
        return ""

#: 说完多久出寄存器。之后靠聊天记录兜底 —— 寄存器只管「还在说的」那几条
KEEP_AFTER_DONE = 1800
#: 长考时多久喂一口心跳。比常见的反向代理空闲上限小一截就行
HEARTBEAT_EVERY = 15


@dataclass
class Job:
    id: str
    message: str
    events: list[str] = field(default_factory=list)
    done: bool = False
    ts: float = field(default_factory=time.time)
    wake: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task | None = None
    #: 说出去的那几句，收尾时拼起来落库
    said: list[str] = field(default_factory=list)
    #: 这一轮是不是摔了（引擎抛异常 / 被掐）。★ 摔了的**半截话不作为正式回复落库**
    failed: bool = False


class JobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        #: 不走 job 的模型任务在跑几个（redo / 主动说话 / 蒸馏 / 通话）
        self._other = 0

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def active(self, limit: int = 3) -> list[dict]:
        """回前台先问一嘴：有没有还没说完的话。"""
        out = [{"job": j.id, "msg": j.message[:60], "done": j.done,
                "n": len(j.events), "ts": j.ts} for j in self._jobs.values()]
        out.sort(key=lambda x: -x["ts"])
        return out[:limit]

    def live_count(self) -> int:
        """还在跑的模型任务有几个（★ 包括不走 job 的那些：redo / 主动说话 / 蒸馏 / 通话）。
        换档案（replace 导入）之前要问这一嘴 —— 有人正在说话时换档案，
        那条回复会接到别人的原文后面。

        ★ 0831（GPT 四轮 P0-03）：原来只数 self._jobs —— 而 redo、主动消息、蒸馏、
          全双工通话都不进这张表，「没有聊天 job」≠「没有模型任务」。"""
        return sum(1 for j in self._jobs.values() if not j.done) + self._other

    @contextlib.contextmanager
    def activity(self, what: str = ""):
        """给不走 job 的模型任务用：`with jobs.activity("redo"): …`
        进来 +1、出去 -1，这段时间 live_count() 看得见它。"""
        self._other += 1
        try:
            yield
        finally:
            self._other = max(0, self._other - 1)

    def new(self, message: str) -> Job:
        now = time.time()
        for k in [k for k, j in self._jobs.items() if j.done and now - j.ts > KEEP_AFTER_DONE]:
            self._jobs.pop(k, None)
        job = Job(id=uuid.uuid4().hex[:12], message=(message or "")[:200])
        self._jobs[job.id] = job
        return job

    def push(self, job: Job, event: str) -> None:
        job.events.append(event)
        # ★ 先换新的再叫醒旧的。反过来写会漏事件：
        #   叫醒之后、换新之前那一瞬间挤进来的事件，等的人会睡过头错过。
        old, job.wake = job.wake, asyncio.Event()
        old.set()

    async def run(self, job: Job, engine: Engine, turn: Turn,
                  on_done: Callable[[Job], Awaitable[None]] | None = None) -> None:
        """任务本体。没人看也照跑到底。

        ★ `finally` 现在**只在真说完或真出错时**走，不再被「观众离席」触发 ——
          这正是这个寄存器存在的理由。
        """
        try:
            async for ev in engine.stream(turn):
                kind = _kind(ev)
                if kind == HEARTBEAT:
                    continue      # 心跳不入册：观众席自己会保活，补播时也不该回放一堆空拍
                job.events.append(ev)
                if kind == SAY:
                    job.said.append(ev)
                old, job.wake = job.wake, asyncio.Event()
                old.set()
        except asyncio.CancelledError:
            job.failed = True
            self.push(job, sse(SAY, text="（这条我停下了。）"))
            raise
        except Exception as e:
            # 老实说摔了，别装作说完了
            job.failed = True
            self.push(job, sse(ERROR, text=f"这条我半路摔了一跤：{type(e).__name__}。上面要是没说完，再叫我一声。"))
        finally:
            job.done = True
            job.ts = time.time()
            job.wake.set()
            try:
                await engine.close()
            except Exception:
                pass
            if on_done is not None:
                try:
                    await on_done(job)      # ★ 落库在这儿：断网也要落
                except Exception as e:
                    print("[jobs] 收尾落库失败：", e, flush=True)

    @staticmethod
    def _for_audience(ev: str) -> str:
        """观众席出口：SAY 里的 ‹…› 带内标记剥掉再给人看。
        events 里存的是原文 —— 落库那头（on_done）要靠原文记账。
        剥空了就换成心跳（观众协议里心跳=无事发生），事件序号不能变 —— 补播按下标续。"""
        kind = _kind(ev)
        if kind != SAY:
            return ev
        try:
            d = json.loads(ev[6:])
        except Exception:
            return ev
        t = strip_marks(d.get("text") or "")
        if not t:
            return sse(HEARTBEAT)
        if t == (d.get("text") or ""):
            return ev
        d["text"] = t
        return sse(SAY, **{k: v for k, v in d.items() if k != "type"})

    async def watch(self, job: Job, after: int = 0) -> AsyncIterator[str]:
        """观众席。从第 after 个事件续播，跟到 done。"""
        i = max(0, int(after))
        if i == 0:
            # ★ 先把 job id 给观众：断线后才 attach 得回来（0831 GPT 二轮 P0）。
            #   它**不算一个事件**：不进 job.events、前端也不推进 seen ——
            #   补播是按 events 的下标续的，多一条就全错位（这条有测试盯着）。
            yield sse(RECV, job=job.id)
        while True:
            wake = job.wake        # ★ 先抓再放：抓完哪怕立刻来新事件，旧 wake 也会被 set，不会睡过头
            while i < len(job.events):
                yield self._for_audience(job.events[i])
                i += 1
            if job.done:
                break
            try:
                await asyncio.wait_for(wake.wait(), timeout=HEARTBEAT_EVERY)
            except asyncio.TimeoutError:
                yield sse(HEARTBEAT)

    async def watch_id(self, job_id: str, after: int = 0) -> AsyncIterator[str]:
        """按 id 重新坐回观众席。任务已经不在了就回 gone，让前端转轮询兜底。"""
        job = self.get(job_id)
        if job is None:
            yield sse(GONE)
            return
        async for ev in self.watch(job, after=after):
            yield ev

    def stop(self, job_id: str) -> bool:
        job = self.get(job_id)
        if job is None or job.done or job.task is None:
            return False
        job.task.cancel()
        return True
