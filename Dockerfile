# 连环 —— 一个容器就是整屋（薄后端 ＋ 前端）。
# 云上跑（Render / Koyeb / 任何能跑 Docker 的地方）都用这一份；本机双击 start.command 的人不需要它。
#
# ★ 容器里一律按「开到网络上」起（--lan）：进门要口令，口令从 LIANHUAN_PASSWORD 读。
#   没给口令它会拒绝启动 —— 「先开着回头再加密码」不留口子。
# ★ 数据（SQLite、上传、secrets.json）全在 /app/data。想保住记忆，把这个目录挂成持久盘。
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /app/data
ENV PORT=8420 \
    LIANHUAN_DB=/app/data/lianhuan.db \
    PYTHONUNBUFFERED=1
EXPOSE 8420
CMD ["sh", "-c", "python -m core.server --lan --port ${PORT:-8420}"]
