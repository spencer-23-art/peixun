FROM python:3.11-slim

WORKDIR /app

# 设置国内 pip 源加速并安装依赖
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple uvicorn fastapi python-multipart openpyxl

# 复制必要代码和静态资源
COPY main.py start_server.py /app/
COPY static/ /app/static/
COPY shiti/ /app/shiti/

# 容器内部暴露 8000 端口
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
