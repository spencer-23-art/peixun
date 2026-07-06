FROM python:3.13-slim

WORKDIR /app

# 换 Debian 国内源（阿里源）加速 apt-get 安装
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/* 2>/dev/null || true && \
    sed -i 's/security.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/* 2>/dev/null || true && \
    sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list 2>/dev/null || true && \
    sed -i 's/security.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list 2>/dev/null || true

# 安装 OpenCV 和 ONNXRuntime 运行所需的系统级 C++ 运行时及图形基础库
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libxcb1 \
    libx11-xcb1 \
    libx11-6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*


# 复制依赖说明并使用国内源加速安装
COPY requirements.txt /app/
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# 复制代码、静态文件和登记卡模板
COPY main.py ocr_handler.py start_server.py /app/
COPY app/ /app/app/
COPY static/ /app/static/
COPY 登记卡.docx /app/

# 容器内部暴露 8000 端口
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]


