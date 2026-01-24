#!/bin/bash

# IntelliAgent Web UI 启动脚本

# 激活虚拟环境
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

echo "=========================================="
echo "🚀 启动 IntelliAgent Web UI（生产模式）"
echo "=========================================="
echo ""

# 检查前端是否已构建
if [ ! -d "web/frontend/dist" ]; then
    echo "❌ 前端尚未构建，开始构建..."
    cd web/frontend
    npm install
    npm run build
    cd ../..
    echo "✅ 前端构建完成"
    echo ""
fi

# 设置环境变量
export WEB_ENV=production

# 启动 FastAPI 服务器
echo "🌐 启动 FastAPI 服务器..."
echo "访问地址: http://localhost:8000"
echo ""

python web/server.py
