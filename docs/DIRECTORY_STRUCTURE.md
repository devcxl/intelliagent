# 目录结构说明

```
intelliagent/
├── src/                          # 源代码主目录
│   ├── __init__.py
│   ├── agent/                    # Agent 核心逻辑
│   │   ├── __init__.py
│   │   ├── react_engine.py       # ReAct 循环引擎
│   │   └── executor.py           # 任务执行器
│   ├── tools/                    # 工具系统
│   │   ├── __init__.py
│   │   ├── builtin_tools.py      # 内置工具
│   │   └── tool_registry.py      # 工具注册中心
│   ├── llm/                      # LLM 客户端
│   │   ├── __init__.py
│   │   └── llm_client.py         # OpenAI LLM 客户端封装
│   ├── memory/                   # 记忆和上下文
│   │   ├── __init__.py
│   │   ├── memory.py             # 记忆管理
│   │   └── context.py            # 上下文管理
│   ├── skills/                   # 技能系统
│   │   ├── __init__.py
│   │   ├── skill.py              # 技能基类
│   │   ├── skill_manager.py      # 技能管理器
│   │   ├── skill_loader.py       # 技能加载器
│   │   ├── skill_system.py       # 技能系统
│   │   └── skill_integration.py  # 技能集成
│   └── web/                      # Web 后端
│       ├── __init__.py
│       ├── server.py             # FastAPI 服务器
│       └── database.py           # 数据库操作
├── frontend/                     # Web 前端
│   ├── src/                      # 前端源代码
│   ├── public/                   # 静态资源
│   ├── dist/                     # 构建输出
│   ├── package.json
│   └── vite.config.ts
├── tests/                        # 测试代码
│   ├── __init__.py
│   ├── unit/                     # 单元测试
│   │   ├── __init__.py
│   │   ├── test_builtin_tools.py
│   │   ├── test_pdca_integration.py
│   │   ├── test_react_engine.py
│   │   ├── test_skill.py
│   │   ├── test_skill_new.py
│   │   └── test_tool_validation.py
│   └── integration/              # 集成测试
│       └── __init__.py
├── scripts/                      # 脚本和工具
│   ├── start-web.sh              # 启动 Web UI（生产模式）
│   ├── start-web-dev.sh          # 启动 Web UI（开发模式）
│   └── verify-web.sh             # Web 环境验证脚本
├── config/                       # 配置文件
│   └── mcp_config.json.example   # MCP 配置示例
├── docs/                         # 文档
│   ├── QUICK_START.md
│   ├── TOOLS.md
│   ├── TOOL_INTEGRATION.md
│   ├── SKILL_GUIDE.md
│   └── ...
├── utils/                        # 工具模块
│   ├── config.py                 # 配置加载
│   └── logger.py                 # 日志工具
├── main.py                       # 主入口
├── requirements.txt              # Python 依赖
├── pytest.ini                    # 测试配置
└── README.md                     # 项目说明
```

## 目录结构变更说明

### 重组目标
- ✅ **标准化结构** - 采用 `src/` 作为主源码目录，符合 Python 最佳实践
- ✅ **按功能分层** - 在 `src/` 内按业务模块组织（agent、tools、llm、memory、skills、web）
- ✅ **按技术栈分离** - 前端独立到根目录 `frontend/`，后端保留在 `src/web/`
- ✅ **清理混乱** - 根目录仅保留配置、脚本和文档

### 主要变更

| 原路径 | 新路径 | 说明 |
|--------|--------|------|
| `core/` | `src/` | 核心代码移至 src/ |
| `core/react_engine.py` | `src/agent/react_engine.py` | ReAct 引擎 |
| `core/executor.py` | `src/agent/executor.py` | 执行器 |
| `core/builtin_tools.py` | `src/tools/builtin_tools.py` | 内置工具 |
| `core/tool_registry.py` | `src/tools/tool_registry.py` | 工具注册中心 |
| `core/llm_client.py` | `src/llm/llm_client.py` | LLM 客户端 |
| `core/memory.py` | `src/memory/memory.py` | 记忆管理 |
| `core/context.py` | `src/memory/context.py` | 上下文管理 |
| `core/skill*.py` | `src/skills/skill*.py` | 技能系统 |
| `web/server.py` | `src/web/server.py` | Web 后端 |
| `web/database.py` | `src/web/database.py` | 数据库操作 |
| `web/frontend/` | `frontend/` | 前端独立到根目录 |
| `test/` | `tests/` | 测试目录标准化 |

### 导入路径更新

所有 Python 文件的导入路径已从 `from core.` 更新为 `from src.`：

```python
# 旧版本
from core.llm_client import LLMClient
from core.react_engine import ReactEngine
from core.memory import Memory

# 新版本
from src.llm.llm_client import LLMClient
from src.agent.react_engine import ReactEngine
from src.memory.memory import Memory
```

### 配置文件更新

- `pytest.ini`: `testpaths = test` → `testpaths = tests`
- 脚本文件已更新路径引用：
  - `scripts/start-web.sh`
  - `scripts/start-web-dev.sh`
  - `scripts/verify-web.sh`

## 迁移后验证

### 验证导入
```bash
python3 -c "from src.agent.react_engine import ReactEngine"
python3 -c "from src.tools.tool_registry import ToolRegistry"
python3 -c "from src.llm.llm_client import LLMClient"
python3 -c "from src.memory.memory import Memory"
python3 -c "from src.skills.skill import CodeSkill"
```

### 运行测试
```bash
pytest tests/unit/
```

### 启动 Web UI
```bash
./scripts/start-web.sh
```

## 回滚方案

如需回滚到旧结构，请恢复以下目录：
- 恢复 `core/` 目录结构
- 恢复 `test/` 目录
- 恢复 `web/` 目录
- 还原所有导入路径 `from src.` → `from core.`
