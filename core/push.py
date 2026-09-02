"""Web Push —— 他想找你、或有事的时候，弹到你锁屏上。

照原项目 push.py 平移：读 push_subs 里所有订阅，VAPID 私钥签名后推送；
过期订阅（404/410）顺手清掉。两处不同都是「开箱即用」逼出来的：
  · 原项目的 VAPID 私钥是手动放好的 pem；这儿**第一次用到时自己生成**，
    存 data/vapid_private.pem（0600），公钥从它算出来给前端。
  · 库是 SQLite（跟聊天记忆同一个）。

★ 平台的实话（写给用的人，接口的 status 也会带）：
  安卓 Chrome/Edge 直接能推；iPhone 要 iOS 16.4 以上、**把这一页添加到主屏幕**、
  从主屏图标打开才行，而且站点得走 HTTPS（本机 localhost 除外）。
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path

_store = None
_PEM = Path(os.environ.get("LIANHUAN_DB", "data/lianhuan.db")).parent / "vapid_private.pem"
SUB = os.environ.get("VAPID_SUB", "mailto:admin@example.com")


def bind(store) -> None:
    global _store
    _store = store
    store.db.execute(
        "CREATE TABLE IF NOT EXISTS push_subs (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " endpoint TEXT UNIQUE NOT NULL, p256dh TEXT NOT NULL, auth TEXT DEFAULT '', ts REAL)")
    store.db.commit()


def _vapid():
    """拿 VAPID 密钥对；没有就当场生成一对存起来（只在第一次）。"""
    from py_vapid import Vapid
    if not _PEM.exists():
        v = Vapid()
        v.generate_keys()
        _PEM.parent.mkdir(parents=True, exist_ok=True)
        v.save_key(str(_PEM))
        os.chmod(_PEM, 0o600)
    return Vapid.from_file(str(_PEM))


def public_key() -> str:
    """给前端 pushManager.subscribe 用的公钥（base64url 的未压缩 EC 点）。"""
    from cryptography.hazmat.primitives import serialization
    v = _vapid()
    raw = v.public_key.public_bytes(serialization.Encoding.X962,
                                    serialization.PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def subscribe(sub: dict) -> bool:
    ep = sub.get("endpoint")
    keys = sub.get("keys") or {}
    if not ep or not keys.get("p256dh"):
        return False
    import time
    _store.db.execute(
        "INSERT INTO push_subs(endpoint,p256dh,auth,ts) VALUES(?,?,?,?) "
        "ON CONFLICT(endpoint) DO NOTHING",
        (ep, keys["p256dh"], keys.get("auth", ""), time.time()))
    _store.db.commit()
    return True


def unsubscribe(endpoint: str) -> int:
    """只删传进来的这一条 —— 别的设备一条不动（原项目同款语义）。"""
    n = _store.db.execute("DELETE FROM push_subs WHERE endpoint=?", (endpoint,)).rowcount
    _store.db.commit()
    return n


def sub_count() -> int:
    return _store.db.execute("SELECT count(*) n FROM push_subs").fetchone()["n"]


def send_push(title: str, body: str, url: str = "/") -> int:
    """推给所有订阅的端。返回发出去几条；404/410 的死订阅顺手清掉。"""
    from pywebpush import webpush, WebPushException
    payload = json.dumps({"title": title, "body": body, "url": url}, ensure_ascii=False)
    sent, dead = 0, []
    rows = list(_store.db.execute("SELECT id, endpoint, p256dh, auth FROM push_subs"))
    for s in rows:
        info = {"endpoint": s["endpoint"], "keys": {"p256dh": s["p256dh"], "auth": s["auth"]}}
        try:
            webpush(info, payload, vapid_private_key=str(_PEM),
                    vapid_claims={"sub": SUB}, ttl=86400)
            sent += 1
        except WebPushException as e:
            code = getattr(getattr(e, "response", None), "status_code", None)
            if code in (404, 410):
                dead.append(s["id"])
            else:
                print("[push] err:", code, str(e)[:120], flush=True)
        except Exception as e:
            print("[push] err:", str(e)[:120], flush=True)
    for d in dead:
        _store.db.execute("DELETE FROM push_subs WHERE id=?", (d,))
    if dead:
        _store.db.commit()
    return sent
