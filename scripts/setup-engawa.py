#!/usr/bin/env python3
"""Install the pinned MIT Engawa MCP into an ignored local runtime and register it.

No API key is read or accepted here.  The upstream commit and license are kept
in ``upstreams/engawa-mcp.lock.json`` and ``licenses/ENGAWA_MCP.txt``.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "upstreams" / "engawa-mcp.lock.json"
RUNTIME = ROOT / ".runtime" / "engawa"


def _python_version(command: str) -> tuple[int, int] | None:
    try:
        out = subprocess.run(
            [command, "-c", "import sys; print(sys.version_info[0], sys.version_info[1])"],
            check=True, capture_output=True, text=True, timeout=10,
        ).stdout.split()
        return int(out[0]), int(out[1])
    except Exception:
        return None


def find_python() -> str:
    """Engawa requires Python 3.11+; choose an installed interpreter explicitly."""
    candidates = [sys.executable, "python3.14", "python3.13", "python3.12", "python3.11", "python3"]
    seen: set[str] = set()
    for item in candidates:
        command = shutil.which(item) if not Path(item).is_absolute() else item
        if not command or command in seen:
            continue
        seen.add(command)
        version = _python_version(command)
        if version and version >= (3, 11):
            return command
    raise RuntimeError("Engawa 需要 Python 3.11 或更新版本；先安装新版 Python 再点一次")


def executable(runtime: Path = RUNTIME) -> Path:
    choices = (runtime / "bin" / "engawa-mcp", runtime / "Scripts" / "engawa-mcp.exe")
    return next((path for path in choices if path.is_file()), choices[0])


def register(command: Path, config_path: Path) -> None:
    """Write only the MCP command; this file contains no key and stays outside Git."""
    try:
        value = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        value = {}
    value.setdefault("mcpServers", {})["engawa"] = {
        "command": str(command),
        "args": [],
        "env": {"ENGAWA_CACHE_DIR": str(config_path.parent / "engawa-cache")},
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = config_path.with_suffix(config_path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(config_path)


def install() -> Path:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    commit = str(lock["commit"])
    python = find_python()
    RUNTIME.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([python, "-m", "venv", str(RUNTIME)], check=True)
    runtime_python = RUNTIME / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    subprocess.run([
        str(runtime_python), "-m", "pip", "install", "--disable-pip-version-check",
        f"git+https://github.com/tsuru0805/engawa-mcp.git@{commit}",
    ], check=True)
    command = executable()
    subprocess.run([str(command), "--check"], check=True, timeout=60)
    db = Path(os.environ.get("LIANHUAN_DB", str(ROOT / "data" / "lianhuan.db")))
    register(command, db.parent / "mcp.json")
    return command


def main() -> None:
    install()
    print("Engawa 已安装并登记；重启连环后，檐廊和 AI 的 12 件阅读工具会一起上线。")


if __name__ == "__main__":
    main()
