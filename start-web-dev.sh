#!/bin/bash

# IntelliAgent Web UI 开发模式启动脚本

# 激活虚拟环境
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

echo "=========================================="
echo "🚀 启动 IntelliAgent Web UI（开发模式）"
echo "=========================================="
echo ""

# 启动前端开发服务器
cd web/frontend

echo "📦 启动前端开发服务器..."
echo "前端地址: http://localhost:5173"
echo ""

npm run dev &
FRONTEND_PID=$!

# 返回项目根目录
cd ../..

echo "🔧 启动后端 FastAPI 服务器..."
echo "后端地址: http://localhost:8000"
echo ""

# 启动后端服务器
export WEB_ENV=development
python web/server.py &
BACKEND_PID=$!

# 等待任意键退出
echo "=========================================="
echo "✅ 服务器已启动"
echo "前端: http://localhost:5173"
echo "后端: http://localhost:8000"
echo ""
echo "按 Ctrl+C 停止所有服务器"
echo "=========================================="

# 捕获 Ctrl+C 信号
trap "kill $FRONTEND_PID $BACKEND_PID; exit" INT TERM

# 等待进程结束
wait
