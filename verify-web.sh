#!/bin/bash
# Web UI 验证脚本

set -e

echo "=========================================="
echo "🔍 验证 Web UI 环境"
echo "=========================================="
echo ""

# 激活虚拟环境
if [ -d ".venv" ]; then
    source .venv/bin/activate
    echo "✅ 虚拟环境已激活"
else
    echo "❌ 虚拟环境不存在"
    exit 1
fi

# 检查 Python 依赖
echo ""
echo "检查 Python 依赖..."
python -c "import fastapi, uvicorn; print('✅ FastAPI 已安装')"
python -c "from utils.logger import logger; print('✅ utils.logger 可导入')"
python -c "from core.react_engine import ReactEngine; print('✅ ReactEngine 可导入')"

# 检查前端构建
echo ""
echo "检查前端构建..."
if [ -d "web/frontend/dist" ]; then
    echo "✅ 前端已构建"
    echo "   - index.html: $(test -f web/frontend/dist/index.html && echo '存在' || echo '缺失')"
    echo "   - assets/: $(test -d web/frontend/dist/assets && echo '存在' || echo '缺失')"
else
    echo "❌ 前端未构建"
    echo "   运行: cd web/frontend && npm install && npm run build"
    exit 1
fi

# 检查 Node.js 依赖
echo ""
echo "检查 Node.js 依赖..."
if [ -d "web/frontend/node_modules" ]; then
    echo "✅ Node.js 依赖已安装"
else
    echo "⚠️  Node.js 依赖未安装（不影响生产模式运行）"
fi

echo ""
echo "=========================================="
echo "✅ 验证通过！"
echo "=========================================="
echo ""
echo "启动方式："
echo "  生产模式: ./start-web.sh"
echo "  开发模式: ./start-web-dev.sh"
echo ""
