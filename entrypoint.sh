#!/bin/sh
# 容器启动时安装依赖，再启动应用。
# 可选环境变量 PIP_INDEX_URL：指定内部 / 加速 PyPI 镜像，例如
#   PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
set -eu

echo "[entrypoint] 安装 Python 依赖 (requirements.txt) ..."
if [ -n "${PIP_INDEX_URL:-}" ]; then
  pip install -r requirements.txt --index-url "$PIP_INDEX_URL"
else
  pip install -r requirements.txt
fi

echo "[entrypoint] 启动 gunicorn: ${WEB_HOST:-0.0.0.0}:${WEB_PORT:-8000} (workers=${GUNICORN_WORKERS:-2})"
exec gunicorn wsgi:app \
  --bind "${WEB_HOST:-0.0.0.0}:${WEB_PORT:-8000}" \
  --workers "${GUNICORN_WORKERS:-2}" \
  --access-logfile - \
  --error-logfile -
