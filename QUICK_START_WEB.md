# Web UI 快速开始

## 验证环境

```bash
./verify-web.sh
```

✅ 已验证：
- 虚拟环境
- Python 依赖
- 前端构建
- 静态资源

## 一键启动

### 生产模式（推荐）

```bash
./start-web.sh
```

访问: http://localhost:8000

### 开发模式（支持热更新）

```bash
./start-web-dev.sh
```

访问:
- 前端: http://localhost:5173
- 后端: http://localhost:8000

## 手动启动

### 前端开发

```bash
cd web/frontend
npm install    # 首次运行
npm run dev    # 开发模式
npm run build  # 生产构建
```

### 后端服务

```bash
# 生产模式
WEB_ENV=production python web/server.py

# 开发模式（使用旧界面）
python web/server.py
```

## 界面布局

```
┌─────────────────────────────────────────┐
│ IntelliAgent  |  ● 已连接              │
├──────────┬──────────────────────────────┤
│ 会话列表  │  执行日志                   │
│          │                            │
│ 会话 1   │  💭 Thought...             │
│ 会话 2   │  🔧 Action: run_shell      │
│ + 新建   │  👁 Observation: 成功       │
│          │  🎉 Answer: ...            │
├──────────┴──────────────────────────────┤
│  任务输入...                            │
│  [运行任务] [停止] [清空]               │
└─────────────────────────────────────────┘
```

## 快捷键

- `Ctrl + Enter`: 快速提交任务

## 会话操作

- **新建**: 点击左侧 `+` 按钮
- **切换**: 点击会话卡片
- **删除**: 悬停会话卡片后点击 `🗑️` 按钮

## 已验证功能

- ✅ 服务器正常启动
- ✅ 静态文件正常返回
- ✅ HTML 页面正确加载
- ✅ JS/CSS 资源可访问

## 注意事项

1. **首次使用**：确保已配置 `.env` 文件中的 `OPENAI_API_KEY`
2. **端口占用**：确保 8000 端口未被占用
3. **浏览器测试**：前端交互功能需要在浏览器中测试

## 详细文档

- [实际验证报告](VERIFICATION.md)
- [Web UI 使用说明](web/WEB_UI.md)
- [优化总结](web/SUMMARY.md)
- [项目 README](README.md)
