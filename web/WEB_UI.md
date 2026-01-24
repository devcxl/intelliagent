# Web UI 使用说明

## 架构

新的 Web UI 采用现代化的技术栈：

- **前端**: Vite + React + TypeScript + Tailwind CSS + shadcn/ui
- **后端**: FastAPI (Python) + WebSocket
- **构建**: Vite 生产构建

## 布局

```
┌─────────────────────────────────────────────────────────────┐
│                      头部 (Header)                           │
│  IntelliAgent  |  连接状态                                   │
├──────────┬──────────────────────────────────────────────────┤
│          │                                                 │
│  侧边栏   │            主内容区                             │
│          │                                                 │
│ 会话列表  │  执行日志                                        │
│          │                                                 │
│          │  - 日志条目                                       │
│          │  - 实时更新                                       │
│          │                                                 │
├──────────┴──────────────────────────────────────────────────┤
│                                                          │
│          底部输入框                                          │
│  任务输入 | 运行任务 | 停止任务 | 清空日志                      │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

## 启动方式

### 方式 1: 生产模式（推荐）

使用构建后的静态文件，性能最佳：

```bash
./start-web.sh
```

访问: http://localhost:8000

### 方式 2: 开发模式

前端支持热更新，适合开发调试：

```bash
./start-web-dev.sh
```

访问:
- 前端开发服务器: http://localhost:5173
- 后端 FastAPI: http://localhost:8000

### 方式 3: 手动启动

**后端**:
```bash
WEB_ENV=production python web/server.py
```

**前端开发** (可选):
```bash
cd web/frontend
npm run dev
```

## 功能特性

### 会话管理

- ✅ 创建新会话
- ✅ 切换会话
- ✅ 删除会话
- ✅ 实时显示会话状态（运行中、完成、错误）
- ✅ 显示会话创建/更新时间

### 日志查看

- 💭 Thought: LLM 思考过程
- 🔧 Action: 工具调用信息
- 👁 Observation: 执行结果
- 🎉 Answer: 最终答案
- ❌ Error: 错误信息

### 任务控制

- 🚀 运行任务: 提交新的任务
- ⏹️ 停止任务: 中断当前执行
- 🗑️ 清空日志: 清除日志显示
- ⌨️ 快捷键: Ctrl + Enter 快速提交

### WebSocket 实时通信

- 实时接收执行日志
- 自动重连机制
- 连接状态指示

## 文件结构

```
web/
├── server.py                    # FastAPI 后端服务器
├── frontend/                    # 前端项目
│   ├── src/
│   │   ├── components/          # React 组件
│   │   │   ├── ui/              # shadcn/ui 组件
│   │   │   ├── Sidebar.tsx      # 侧边栏
│   │   │   ├── LogViewer.tsx    # 日志查看器
│   │   │   └── InputArea.tsx    # 输入框
│   │   ├── hooks/               # React Hooks
│   │   │   └── useWebSocket.ts  # WebSocket Hook
│   │   ├── lib/                 # 工具函数
│   │   │   └── utils.ts         # cn 函数
│   │   ├── App.tsx              # 主应用组件
│   │   ├── main.tsx             # 入口文件
│   │   └── index.css            # 全局样式
│   ├── dist/                    # 构建输出（生产模式）
│   └── package.json             # 依赖配置
└── static/                      # 旧静态文件（向后兼容）
    ├── index.html
    ├── js/
    └── css/
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `WEB_ENV` | 运行环境 (`production` / `development`) | `development` |
| `WEB_HOST` | 后端监听地址 | `0.0.0.0` |
| `WEB_PORT` | 后端监听端口 | `8000` |

## 开发指南

### 安装前端依赖

```bash
cd web/frontend
npm install
```

### 构建前端

```bash
npm run build
```

### 前端开发

```bash
npm run dev
```

### 添加新的 shadcn/ui 组件

```bash
npx shadcn@latest add [component-name]
```

## 向后兼容

旧的静态文件仍保留在 `web/static/` 目录下，通过 `WEB_ENV=development` 可以继续使用旧界面。

## 注意事项

1. 首次运行生产模式需要先构建前端（启动脚本会自动处理）
2. 前端开发服务器默认运行在 `http://localhost:5173`
3. 后端 FastAPI 默认运行在 `http://localhost:8000`
4. WebSocket 地址会根据当前协议自动选择 `ws://` 或 `wss://`
