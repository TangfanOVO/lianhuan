"""连环 · 安卓完整体的起点。Java 那边开机时调一次 start()，后端就在这个进程里跑起来。

数据全在应用自己的沙箱（filesDir/data）：SQLite、上传、secrets.json 都在那儿。
卸载 app 就一起没了；要搬家先在设置里导出 JSON。
"""
from __future__ import annotations

import os
import threading

_started: dict = {}


def start(files_dir: str, port: int = 8420) -> str:
    """把后端起在 127.0.0.1:port（只听本机，所以不装门、不要口令）。重复调用只返回地址。"""
    if _started.get("url"):
        return _started["url"]
    data = os.path.join(files_dir, "data")
    os.makedirs(data, exist_ok=True)
    os.environ.setdefault("LIANHUAN_DB", os.path.join(data, "lianhuan.db"))

    import uvicorn
    from core.server import app

    cfg = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", loop="asyncio")
    srv = uvicorn.Server(cfg)
    # ★ 不是主线程：uvicorn 在非主线程里会自己跳过信号处理，这正是这儿要的
    t = threading.Thread(target=srv.run, name="lianhuan-uvicorn", daemon=True)
    t.start()
    _started["url"] = f"http://127.0.0.1:{port}/"
    _started["server"] = srv
    return _started["url"]
