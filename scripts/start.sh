#!/bin/bash
cd "$(dirname "$0")/.."

echo "启动后端..."
cd backend && python main.py &
sleep 2

echo "启动前端..."
cd ../frontend/src && python -m http.server 3000 &

echo "服务已启动: http://localhost:3000"
wait
