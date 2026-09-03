"""开到网络上时的那道门 —— 默认整个不生效。

## 为什么是这个形状

作者定的那张表（部署形态 → 要不要认证）：

| 形态 | 数据在哪 | 认证 |
|---|---|---|
| 纯本地（默认，只听 127.0.0.1） | 你自己这台机器 | **不要**。屏幕锁了就是锁了，再加密码是多余的 |
| 开到网络上（`--lan`） | 还是你这台，但**知道地址的人都能进** | **必须要** |

所以：不加 `--lan`，下面一行代码都不会拦你；加了 `--lan` 而没有密码，**服务直接不启动**。
「先开着，回头再加密码」这种事不留口子 —— 那个「回头」永远不会来。

## 另一条跟密码无关的硬线

**能让这台机器执行命令的接口默认只在纯本机模式开放。**
登记一条 MCP server ＝ 在你电脑上起一个进程。那种事不该由「网络上知道密码的人」决定：
密码会泄、会被猜、会被同一个 wifi 上的人肩窥，而命令执行不给第二次机会。
本机的人本来就能开终端，对他们这条不是限制。
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
import secrets as _rand

#: cookie 的名字和寿命（30 天，跟「手机上别老让我重登」这件事折中）
COOKIE = "lh_auth"
ANDROID_COOKIE = "lh_android"
MAXAGE = 30 * 86400

#: 只认本机的路径。**认证也不放行**，理由见模块头
LOCAL_ONLY = {"/api/mcp/add", "/api/mcp/del"}


def command_path(path: str) -> bool:
    """Endpoints that can install or launch local code never accept LAN callers."""
    return path in LOCAL_ONLY or (path.startswith("/api/packs/") and path.endswith("/setup"))

#: 口令的最短长度。★ 16 不是拍脑袋：这道门开在公网上，谁都能敲，
#: 而它后面是一整个家（聊天、记忆、日记）。短口令在这种位置上等于没有。
MIN_LEN = 16

#: 我们自己在文档和一键部署链接里写过的占位串。**它们不许当真口令用** ——
#: 写在公开 README 里的字，全世界都读得到。
PLACEHOLDERS = {"改成你的口令", "your-password", "changeme", "change-me", "password", "口令"}


def weak(pw: str) -> str:
    """这句口令能不能用。能用回空串，不能用回一句人话（给启动时打印）。"""
    pw = (pw or "").strip()
    if not pw:
        return "空的"
    if pw in PLACEHOLDERS or pw.lower() in PLACEHOLDERS:
        return "这是文档里的占位串，全世界都看得到，换一句你自己的"
    if len(pw) < MIN_LEN:
        return f"太短了（{len(pw)} 个字符，至少要 {MIN_LEN} 个）"
    return ""


#: 失败几次锁多久。★ 没有这一层，16 位口令也架不住不限次数的猜。
FAIL_MAX = 5
LOCK_SEC = 600

_state: dict = {"on": False, "token": ""}
#: 每个来源地址的失败记录：addr -> [失败次数, 锁到什么时候]
_fails: dict = {}


def _now() -> float:
    return time.time()


def locked(addr: str) -> int:
    """这个地址还要等几秒才能再试。0 = 现在可以试。

    ★ `rec[1] == 0` 是「攒着失败但还没锁」，**不是**「锁过期了」——
      分不清这两件事的话，每次查询都会把失败计数清掉，于是永远数不到上限。
      （这条是自带的限流测试当场逮到的。）"""
    rec = _fails.get(addr or "")
    if not rec or rec[1] <= 0:
        return 0
    left = int(rec[1] - _now())
    if left <= 0:
        _fails.pop(addr or "", None)          # 锁真的过期了，记录清掉，从头数
        return 0
    return left


#: 最多记多少个地址。★ 没有这个上限，换着 IP 敲就是往内存里灌东西。
MAX_TRACKED = 4096


def _prune() -> None:
    """记录太多了：把已经不锁人的清掉；还清不动就整个倒掉重来（宁可放过，不能撑爆）。"""
    if len(_fails) <= MAX_TRACKED:
        return
    now = _now()
    for k in [k for k, v in _fails.items() if v[1] <= now]:
        _fails.pop(k, None)
    if len(_fails) > MAX_TRACKED:
        _fails.clear()


def note_fail(addr: str) -> int:
    """记一次失败，回「还要等几秒」（没到次数就是 0）。"""
    a = addr or ""
    _prune()
    rec = _fails.get(a) or [0, 0.0]
    rec[0] += 1
    if rec[0] >= FAIL_MAX:
        rec[1] = _now() + LOCK_SEC
        rec[0] = 0                       # 锁上之后重新数，别让它越锁越久
    _fails[a] = rec
    return locked(a)


def note_ok(addr: str) -> None:
    """进对了，把这个地址的失败记录清掉。"""
    _fails.pop(addr or "", None)



def local_addr(host: str) -> bool:
    """这次请求是不是从本机来的。

    默认只信 socket 上的对端地址。只有 `client_addr()` 认出的显式可信反代，
    才能把 X-Forwarded-For 送进这里。
    """
    return (host or "") in {"127.0.0.1", "::1", "localhost", ""}


def client_addr(peer: str, forwarded_for: str = "") -> str:
    """只在显式列出的反代后面采用 X-Forwarded-For；默认永远只信 socket。"""
    trusted = {x.strip() for x in os.environ.get("LIANHUAN_TRUSTED_PROXIES", "").split(",") if x.strip()}
    if (peer or "") in trusted and forwarded_for:
        # 只取可信反代自己追加的最右一段；客户端可伪造的左侧 XFF 不能用来刷新限流。
        return forwarded_for.rsplit(",", 1)[-1].strip()
    return peer or ""


def allow_local_commands() -> bool:
    """开了网络门时，回环也可能是反代；必须显式允许它执行本机命令。"""
    return os.environ.get("LIANHUAN_ALLOW_LOCAL_COMMANDS", "").strip().lower() in {"1", "true", "yes"}


def check_android_cookie(value: str) -> bool:
    """完整体每次启动换一张票；没有票的本机进程也进不来。"""
    token = os.environ.get("LIANHUAN_ANDROID_TOKEN", "")
    return bool(token and value) and hmac.compare_digest(value, token)


def salt() -> str:
    """给密码加的盐。第一次用的时候生成，之后存在 secrets.json 里（0600）。"""
    from . import secrets as _sec
    s = _sec.get("LAN_SALT")
    if not s:
        s = _rand.token_hex(16)
        _sec.set_many({"LAN_SALT": s})
    return s


def _hash(pw: str) -> str:
    return hashlib.sha256((salt() + "::" + pw).encode("utf-8")).hexdigest()


def arm(pw: str) -> None:
    """装上这道门。只有 main() 在 --lan 且拿到密码时才调。

    ★ 口令不合格就**抛异常**，不是打个警告继续跑 —— 「先开着回头再改」那个回头永远不会来。"""
    bad = weak(pw)
    if bad:
        raise ValueError(bad)
    _state["on"] = True
    _state["token"] = _hash(pw)


def on() -> bool:
    return bool(_state["on"])


def check_cookie(v: str) -> bool:
    """★ 用 compare_digest，不用 == —— 别把比较耗时漏出去。"""
    return bool(v) and hmac.compare_digest(v, _state["token"])


def check_password(pw: str) -> str:
    """密码对就回 cookie 值，不对回空串。"""
    t = _hash(pw or "")
    return t if hmac.compare_digest(t, _state["token"]) else ""


#: 登录页。**一个外部资源都不引**（没有 CDN、没有字体、没有图）——
#: 这一页出现的时候，人还没进门，不该为它去连任何别的地方。
LOGIN_HTML = """<!doctype html><html lang="zh"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>连环 · 先报个门</title>
<style>
:root{color-scheme:light dark}
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
  background:#f6f2ec;color:#2b2724;font:16px/1.7 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
@media (prefers-color-scheme:dark){body{background:#171513;color:#e8e0d8}}
.box{width:min(92vw,340px)}
h1{font-size:19px;font-weight:600;margin:0 0 6px}
p{font-size:13px;line-height:1.75;color:#8a7f74;margin:0 0 18px}
input{width:100%;box-sizing:border-box;font:inherit;font-size:16px;padding:12px 14px;
  border:1px solid #d9cec1;border-radius:11px;background:#fffdfa;color:inherit}
@media (prefers-color-scheme:dark){input{background:#221f1c;border-color:#3a342e}}
input:focus-visible{outline:2px solid #b4472e;outline-offset:2px}
button{width:100%;margin-top:12px;font:inherit;font-size:15px;padding:12px;cursor:pointer;
  border:1px solid rgba(180,71,46,.38);border-radius:11px;background:rgba(180,71,46,.12);color:#b4472e}
.err{font-size:13px;color:#b4472e;margin-top:10px;min-height:20px}
</style>
<div class="box">
  <h1>先报个门</h1>
  <p>这台机器把家开到了网络上，所以要一句口令。<br>密码是启动的人自己设的。</p>
  <form id="f"><input id="p" type="password" autocomplete="current-password"
    placeholder="口令" autofocus><button type="submit">进去</button></form>
  <div class="err" id="e"></div>
</div>
<script>
document.getElementById('f').addEventListener('submit', async function(ev){
  ev.preventDefault();
  const e = document.getElementById('e');
  e.textContent = '看一眼…';
  const r = await fetch('/api/login', {method:'POST', headers:{'content-type':'application/json'},
    body: JSON.stringify({password: document.getElementById('p').value})}).then(r=>r.json()).catch(()=>null);
  if (r && r.ok) location.href = '/';
  else if (r && r.locked) e.textContent = r.error || '错太多次了，等一会儿再试。';
  else { e.textContent = '口令不对。'; document.getElementById('p').select(); }
});
</script>
</html>"""
