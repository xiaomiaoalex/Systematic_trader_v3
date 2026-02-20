FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY . .

# 创建目录
RUN mkdir -p data logs

# 暴露端口
EXPOSE 8080

# 启动命令
CMD ["python", "main.py"]
