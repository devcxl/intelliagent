# IntelliAgent - 智能代理框架

> 基于 MCP (Model Context Protocol) 的完全异步智能代理框架

[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-1.18.0-green.svg)](https://github.com/modelcontextprotocol)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## 🎯 特性

- ✅ **完全 MCP 架构** - 不使用混合模式，纯 MCP 通信
- ✅ **异步优先** - 基于 asyncio 的高性能异步处理
- ✅ **工具丰富** - Shell、文件、测试、Git 等常用工具
- ✅ **类型安全** - 完整的类型提示和错误处理
- ✅ **易于扩展** - 模块化设计，轻松添加新工具

## 📦 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 运行示例

```bash
# 运行快速示例
python3 tests/example_usage.py

# 运行完整测试
python3 tests/test_registry.py
```

### 启动主程序

```bash
python3 main.py
```

## 📁 项目结构

```
intelliagent/
├── main.py                    # 主程序入口
├── mcp_server.py              # MCP 工具服务器
├── requirements.txt           # Python 依赖
├── core/                      # 核心模块
│   ├── tool_registry.py       # 工具注册中心
│   ├── tool_registry_mcp.py   # MCP 客户端
│   ├── planner.py             # 任务规划器
│   ├── executor.py            # 任务执行器
│   ├── context.py             # 上下文管理
│   └── memory.py              # 记忆管理
├── utils/                     # 工具函数
│   ├── logger.py              # 日志工具
│   └── config.py              # 配置管理
├── tests/                     # 测试和示例
│   ├── test_registry.py       # 工具注册测试
│   ├── test_mcp.py            # MCP 测试
│   ├── example_usage.py       # 使用示例
│   └── ...                    # 其他测试
└── docs/                      # 文档
    ├── README.md              # 完整文档
    ├── QUICKREF.md            # 快速参考
    ├── CHANGELOG.md           # 变更日志
    └── ...                    # 其他文档
```

## 🛠️ 可用工具

| 工具名称 | 描述 | 参数 |
|---------|------|------|
| `run_shell` | 执行 shell 命令 | `cmd: str` |
| `read_file` | 读取文件内容 | `path: str` |
| `write_file` | 写入文件内容 | `path: str, content: str` |
| `run_tests` | 运行 pytest 测试 | `test_path: str = "."` |
| `git_commit` | Git 提交代码 | `message: str` |

## 📚 文档

- [完整文档](docs/README.md) - 详细使用指南
- [快速参考](docs/QUICKREF.md) - 一页式速查
- [架构设计](docs/MCP_PURE_MODE.md) - 架构详解
- [变更日志](docs/CHANGELOG.md) - 版本历史

## 🧪 测试

```bash
# 运行所有测试
python3 -m pytest tests/

# 运行特定测试
python3 tests/test_registry.py
python3 tests/example_usage.py
```

## 📋 依赖

- Python 3.10+
- mcp >= 1.18.0
- anyio >= 4.11.0
- aiofiles >= 24.1.0
- python-dotenv >= 1.1.1
- pytest >= 8.3.3

## ⚙️ 配置

创建 `.env` 文件：

```bash
# MCP Server 配置
MCP_SERVER_COMMAND=python3
MCP_SERVER_SCRIPT=mcp_server.py

# 日志级别
LOG_LEVEL=INFO
```

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License

## 🔮 路线图

- [ ] 完善 ReAct 推理循环
- [ ] 集成更多 LLM
- [ ] 添加向量数据库支持
- [ ] 实现更多工具
- [ ] 性能优化
- [ ] 完整测试覆盖

---

**由 GitHub Copilot 辅助开发** - 2025-11-03
