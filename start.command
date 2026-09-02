#!/usr/bin/env bash
# 连环 —— 双击这个就能跑（macOS / Linux）。
#
# 它做四件事：建虚拟环境 → 装依赖 → 起服务 → 打开浏览器。
# 都做过一遍之后，以后每次双击就是几秒的事。
#
# ★ 要接模型的话，先在同目录建一个 .env 文件（照 .env.example 写）。
#   key 只在这台机器上，不会进任何仓库、不会进数据库、不会进导出的备份。
set -euo pipefail
cd "$(dirname "$0")"

PY=$(command -v python3 || true)
if [ -z "$PY" ]; then
  echo "找不到 python3。"
  echo "macOS：装 Xcode 命令行工具（xcode-select --install）或去 python.org 下一个"
  echo "Linux：apt install python3 python3-venv / dnf install python3"
  read -rp "按回车关闭…" _; exit 1
fi

if [ ! -d .venv ]; then
  echo "· 第一次跑，先建个干净的环境（一分钟左右）…"
  "$PY" -m venv .venv
fi
./.venv/bin/pip install -q --disable-pip-version-check -r requirements.txt

# key 从 .env 读。★ 只在这个进程里，不写库、不写日志
if [ -f .env ]; then
  set -a; . ./.env; set +a
  echo "· 读到 .env 了"
fi

PORT="${PORT:-8420}"
URL="http://127.0.0.1:$PORT"
echo ""
echo "  连环跑起来了：$URL"
echo "  手机也要连的话，关掉这个窗口，改跑：./start.command --lan"
echo "  停下来：在这个窗口按 Ctrl+C"
echo ""

( sleep 1.5
  command -v open >/dev/null && open "$URL" 2>/dev/null \
    || (command -v xdg-open >/dev/null && xdg-open "$URL" 2>/dev/null) || true ) &

exec ./.venv/bin/python -m core.server --port "$PORT" "$@"
