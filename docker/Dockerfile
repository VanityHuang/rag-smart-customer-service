FROM python:3.11-slim

WORKDIR /app

# 更换 Debian 源为阿里云镜像（加速 apt 下载）
RUN sed -i 's|http://deb.debian.org/debian|https://mirrors.aliyun.com/debian|g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's|http://deb.debian.org/debian-security|https://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list.d/debian.sources

# 安装编译工具（stringzilla 等包需要）和 OpenCV 运行时依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    libxcb1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt -i https://mirrors.aliyun.com/pypi/simple/

# 预下载 PaddleOCR 模型（避免运行时首次调用出现下载延迟）
# 注：服务器内存不足导致构建时 segfault，取消预下载，首次运行时会自动拉取
# RUN python -c "from paddleocr import PaddleOCR; PaddleOCR(use_angle_cls=True, lang='ch', show_log=False)"

COPY . .

EXPOSE 8000

CMD ["uvicorn", "api.server:app", "--host", "0.0.0.0", "--port", "8000"]
