# ════════════════════════════════════════════════════════════
# cr-agent Dockerfile — Task 18.1
# Multi-stage build: builder(缓存依赖) → runtime(精简镜像)
# ════════════════════════════════════════════════════════════

# ── Stage 1: Builder ─────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# 先只复制依赖文件，充分利用 Docker 缓存层
COPY backend/requirements.txt .
COPY backend/pyproject.toml .

# 安装依赖到独立目录
RUN pip install --no-cache-dir --user -r requirements.txt

# ── Stage 2: Runtime ─────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# 从 builder 复制已安装的依赖
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# 复制应用代码
COPY backend/ ./backend/

# 暴露端口（Railway 会注入 $PORT，这里作为文档说明）
EXPOSE 8000

# Railway 注入 $PORT，我们用这个变量启动
# 本地测试时默认 8000
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
