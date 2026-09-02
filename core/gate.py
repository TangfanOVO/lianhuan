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

**能让这台机器执行命令的接口，只认本机 —— 认证过了也不行。**
登记一条 MCP server ＝ 在你电脑上起一个进程。那种事不该由「网络上知道密码的人」决定：
密码会泄、会被猜、会被同一个 wifi 上的人肩窥，而命令执行不给第二次机会。
本机的人本来就能开终端，对他们这条不是限制。
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets as _rand

#: cookie 的名字和寿命（30 天，跟「手机上别老让我重登」这件事折中）
COOKIE = "lh_auth"
MAXAGE = 30 * 86400

#: 只认本机的路径。**认证也不放行**，理由见模块头
LOCAL_ONLY = {"/api/mcp/add", "/api/mcp/del"}

_state: dict = {"on": False, "token": ""}


def local_addr(host: str) -> bool:
    """这次请求是不是从本机来的。

    ⚠ 只信 socket 上的对端地址，**不看任何请求头** —— X-Forwarded-For 那类
      是客户端能随便写的，拿它判本机等于没判。
      （代价：真放在反向代理后面时，所有请求都算「不是本机」，那反而是安全的一边。）
    """
    return (host or "") in {"127.0.0.1", "::1", "localhost", ""}


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
    """装上这道门。只有 main() 在 --lan 且拿到密码时才调。"""
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
  else { e.textContent = '口令不对。'; document.getElementById('p').select(); }
});
</script>
</html>"""
