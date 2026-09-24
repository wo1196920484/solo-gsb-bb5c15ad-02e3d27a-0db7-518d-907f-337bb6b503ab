FROM python:3.11-slim

# 不生成 .pyc、日志不缓冲
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 先装依赖，利用构建缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY app ./app

# 容器内固定监听 8000；宿主机端口由 compose 映射
EXPOSE 8000

# 容器级健康检查（不依赖 curl）
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"

# 一键启动：uvicorn 直接拉起 API（无外部依赖，无需额外初始化）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
