FROM python:3.11-slim

WORKDIR /app

# 安装 onnxruntime 依赖的 C++ 运行时库 libgomp1 (python-slim 镜像中默认缺失)
RUN apt-get update && apt-get install -y libgomp1 && rm -rf /var/lib/apt/lists/*

# 复制依赖说明并使用国内源加速安装
COPY requirements.txt /app/
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# 复制代码、静态文件、登记卡模板和试题库
COPY main.py ocr_handler.py start_server.py /app/
COPY static/ /app/static/
COPY shiti/ /app/shiti/
COPY 登记卡.docx /app/

# 容器内部暴露 8000 端口
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]


