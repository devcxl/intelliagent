# 快速入门指南 - IntelliAgent 工具系统

欢迎使用 IntelliAgent 工具系统！本指南将帮助你快速开始使用内置工具和外部工具。

---

## 📋 目录

1. [环境准备](#环境准备)
2. [运行示例](#运行示例)
3. [核心概念](#核心概念)
4. [工具使用](#工具使用)
5. [常见问题](#常见问题)
6. [下一步](#下一步)

---

## 环境准备

### 1. 克隆或导航到项目目录

```bash
cd /Users/felix/IdeaProjects/intelliagent
```

### 2. 创建并激活虚拟环境

```bash
# 创建虚拟环境（如果还没有）
python3 -m venv .venv

# 激活虚拟环境
source .venv/bin/activate  # macOS/Linux
# 或
.venv\Scripts\activate     # Windows
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

验证安装是否成功：

```bash
python -c "import mcp; print('MCP 安装成功')"
```

### 4. 配置环境变量

检查项目根目录是否有 `.env` 文件，如没有，参考 `.env.example` 创建：

```bash
# 复制示例配置
cp .env.example .env

# 编辑 .env 文件，添加必要的 API 密钥
# 例如：OPENAI_API_KEY=your-key-here
```

**关键环境变量：**
- `OPENAI_API_KEY` - OpenAI API 密钥（必需）
- `OPENAI_MODEL` - 使用的 OpenAI 模型（默认: gpt-4）
- `MCP_CONFIG_FILE` - MCP 配置文件路径（默认: mcp_config.json）
- `MAX_PDCA_CYCLES` - PDCA 循环最大次数（默认: 3）
- `MAX_RETRY_PER_STEP` - 每步重试次数（默认: 3）

---

## 运行示例

### 快速示例：运行 example.py

这个脚本演示了所有 6 个内置工具的实际使用场景：

```bash
python example.py
```

**示例内容：**
1. ✅ 执行 Shell 命令（run_shell）
2. ✅ 文件读写操作（read_file, write_file）
3. ✅ 目录列表（list_dir）
4. ✅ 文件管理工作流（delete_file, file_exists）
5. ✅ 错误处理最佳实践
6. ✅ 高级 Shell 用法
7. ✅ 真实场景示例

### 验证工具系统

运行验证测试（不需要 MCP 依赖）：

```bash
python test/test_tool_validation.py
```

**预期输出：**
```
✅ 通过: 16
❌ 失败: 0
🎉 所有检查通过！
```

### 运行单元测试

如果已安装 MCP 依赖，可以运行完整的单元测试：

```bash
python test/test_builtin_tools.py
```

或使用 pytest：

```bash
pytest test/test_builtin_tools.py -v
```

---

## 核心概念

### 什么是内置工具？

IntelliAgent 提供了 6 个内置工具，用于文件管理、目录浏览和命令执行：

| 工具 | 功能 | 典型用途 |
|------|------|--------|
| `run_shell` | 执行系统命令 | 运行脚本、编译、测试 |
| `read_file` | 读取文件内容 | 读取配置、代码、日志 |
| `write_file` | 写入/创建文件 | 修改配置、生成文件 |
| `list_dir` | 列出目录内容 | 浏览目录结构 |
| `delete_file` | 删除文件 | 清理临时文件 |
| `file_exists` | 检查文件/目录存在性 | 文件验证、条件判断 |

### 什么是外部工具？

IntelliAgent 通过 MCP（Model Context Protocol）支持集成外部工具，包括：

- **filesystem** - 高级文件系统操作
- **github** - GitHub API 集成
- **brave-search** - 互联网搜索
- **context7** - 编程文档查询
- **sequential-thinking** - 结构化思维

### 如何使用工具？

工具调用通常由 AI 智能体自动完成。在使用 IntelliAgent 的 PDCA 循环时：

1. **Plan（规划）** - AI 分析任务，决定需要哪些工具
2. **Do（执行）** - 执行工具操作
3. **Check（检查）** - 验证工具执行结果
4. **Act（行动）** - 根据结果调整策略

---

## 工具使用

### 基础用法

#### 1. 运行 Shell 命令

```python
from mcp_server import run_shell
import asyncio
import json

async def example():
    # 执行命令
    result = await run_shell("ls -la")
    
    # 解析结果（JSON 格式）
    data = json.loads(result)
    if data['status'] == 'ok':
        print(f"命令输出: {data['output']}")
        print(f"返回码: {data['returncode']}")
    else:
        print(f"错误: {data['error']}")
        print(f"错误代码: {data['code']}")

asyncio.run(example())
```

#### 2. 读取文件

```python
from mcp_server import read_file
import json

async def example():
    result = await read_file("README.md")
    data = json.loads(result)
    
    if data['status'] == 'ok':
        print(f"文件内容:\n{data['content']}")
        print(f"文件大小: {data['size']} 字符")
    else:
        print(f"错误: {data['error']}")

asyncio.run(example())
```

#### 3. 写入文件

```python
from mcp_server import write_file
import json

async def example():
    content = "Hello, IntelliAgent!"
    result = await write_file("/tmp/test.txt", content)
    data = json.loads(result)
    
    if data['status'] == 'ok':
        print(f"文件已创建: {data['path']}")
    else:
        print(f"错误: {data['error']}")

asyncio.run(example())
```

#### 4. 列出目录

```python
from mcp_server import list_dir
import json

async def example():
    result = await list_dir(".")
    data = json.loads(result)
    
    if data['status'] == 'ok':
        for item in data['items'][:5]:  # 显示前 5 个
            print(f"- {item['name']} ({item['type']})")
    else:
        print(f"错误: {data['error']}")

asyncio.run(example())
```

#### 5. 删除文件

```python
from mcp_server import delete_file
import json

async def example():
    result = await delete_file("/tmp/test.txt")
    data = json.loads(result)
    
    if data['status'] == 'ok':
        print(f"文件已删除: {data['path']}")
    else:
        print(f"错误: {data['error']}")

asyncio.run(example())
```

#### 6. 检查文件存在性

```python
from mcp_server import file_exists
import json

async def example():
    result = await file_exists("README.md")
    data = json.loads(result)
    
    if data['exists']:
        print(f"文件存在，类型: {data['type']}")
    else:
        print("文件不存在")

asyncio.run(example())
```

### 错误处理

所有工具都返回统一的 JSON 格式响应：

**成功响应：**
```json
{
  "status": "ok",
  "output": "...",
  "returncode": 0,
  ...其他字段...
}
```

**错误响应：**
```json
{
  "status": "error",
  "error": "错误描述",
  "code": "ERROR_CODE"
}
```

**常见错误代码：**
- `EMPTY_COMMAND` / `EMPTY_PATH` / `EMPTY_CONTENT` - 参数为空
- `FILE_NOT_FOUND` / `NOT_FOUND` - 文件不存在
- `TIMEOUT` - 命令执行超时
- `PERMISSION_DENIED` - 权限不足
- `CONTENT_TOO_LARGE` - 内容超过大小限制
- `IS_DIRECTORY` / `NOT_A_DIRECTORY` - 类型错误

**处理错误的推荐方式：**

```python
import json

async def safe_read_file(path):
    result = await read_file(path)
    data = json.loads(result)
    
    if data['status'] == 'ok':
        return data['content']
    
    # 根据错误代码处理
    error_code = data.get('code', 'UNKNOWN')
    if error_code == 'FILE_NOT_FOUND':
        print(f"文件不存在: {path}")
    elif error_code == 'PERMISSION_DENIED':
        print(f"权限不足: {path}")
    elif error_code == 'CONTENT_TOO_LARGE':
        print(f"文件过大: {path}")
    else:
        print(f"未知错误: {data['error']}")
    
    return None
```

### 性能和限制

**默认限制：**
- Shell 命令超时: 30 秒
- 文件读取限制: 50 KB（50,000 字符）
- 文件写入限制: 1 MB（1,000,000 字符）
- 目录列表限制: 1,000 个项目

**调整限制：**

编辑 `mcp_server.py` 顶部的配置常量：

```python
SHELL_COMMAND_TIMEOUT = 30      # 改为需要的秒数
FILE_READ_MAX_SIZE = 50000      # 改为需要的字符数
FILE_WRITE_MAX_SIZE = 1000000   # 改为需要的字符数
DIR_LIST_MAX_ITEMS = 1000       # 改为需要的项目数
```

---

## 常见问题

### Q1: 如何在 IntelliAgent 中使用工具？

工具主要由 AI 智能体自动使用。通过以下方式触发：

```bash
python main.py "执行一个需要使用工具的任务"
```

AI 会自动选择合适的工具来完成任务。

### Q2: 如何添加新工具？

参考 `docs/TOOL_INTEGRATION.md` 中的"自定义 MCP 服务扩展"部分。

### Q3: 工具响应超时怎么办？

1. 检查 Shell 命令是否卡住
2. 增加 `SHELL_COMMAND_TIMEOUT` 的值
3. 拆分大文件操作

### Q4: 文件操作失败怎么办？

检查以下几点：
1. 文件/目录路径是否正确
2. 是否有足够的文件系统权限
3. 文件是否超过大小限制
4. 磁盘空间是否充足

### Q5: 如何调试工具问题？

启用详细日志：

```python
from utils.logger import logger

# 查看日志
logger.info("调试信息")
logger.error("错误信息")
```

查看完整日志输出：

```bash
python -u main.py "任务描述" 2>&1 | tee debug.log
```

### Q6: 可以并发调用工具吗？

可以，但建议小心处理并发访问同一文件的情况：

```python
import asyncio

async def parallel_operations():
    # 并发执行多个操作
    results = await asyncio.gather(
        read_file("file1.txt"),
        read_file("file2.txt"),
        read_file("file3.txt")
    )
    return results
```

---

## 下一步

### 阅读完整文档

- **[工具系统文档](TOOLS.md)** - 所有工具的详细参考
- **[MCP 集成指南](TOOL_INTEGRATION.md)** - 集成外部工具的完整指南

### 实践示例

1. 运行 `example.py` 了解各工具的用法
2. 修改 `example.py` 中的示例，尝试不同的场景
3. 在自己的项目中集成工具

### 高级用途

- 配置外部 MCP 工具（GitHub, 搜索等）
- 创建自定义工具集成
- 构建自动化工作流

### 获取帮助

- 查看项目 README
- 查看代码中的注释和文档字符串
- 检查日志输出找线索
- 提交问题或拉取请求

---

## 快速参考

### 常用命令

```bash
# 运行示例
python example.py

# 运行验证测试
python test/test_tool_validation.py

# 运行单元测试
pytest test/test_builtin_tools.py -v

# 运行主程序
python main.py "任务描述"

# 查看帮助
python main.py --help
```

### 项目结构

```
intelliagent/
├── mcp_server.py              # 内置工具实现
├── main.py                    # 主程序入口
├── example.py                 # 工具使用示例（你在这里）
├── core/                      # 核心模块
│   ├── llm_client.py
│   ├── planner.py
│   ├── executor.py
│   ├── checker.py
│   └── actor.py
├── docs/
│   ├── TOOLS.md               # 工具详细文档
│   ├── TOOL_INTEGRATION.md   # MCP 集成指南
│   └── QUICK_START.md         # 本文件
├── test/
│   ├── test_builtin_tools.py      # 单元测试
│   └── test_tool_validation.py    # 验证测试
└── README.md                  # 项目概览
```

---

## 总结

你已经了解了 IntelliAgent 工具系统的基础知识！现在可以：

✅ 理解内置工具的作用  
✅ 知道如何运行示例代码  
✅ 掌握错误处理的方法  
✅ 知道去哪里找更多信息  

**下一步:** 根据你的需求选择深入学习特定工具或集成外部工具。

祝你使用愉快！🚀
