FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    WEB_HOST=0.0.0.0 \
    WEB_PORT=8000 \
    GUNICORN_WORKERS=2

WORKDIR /app

# 仅复制代码与依赖清单；依赖在容器启动时由 entrypoint 安装（见 README“工作方式”）
COPY requirements.txt entrypoint.sh ./
COPY wsgi.py ./
COPY app ./app

RUN chmod +x entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]
