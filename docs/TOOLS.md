# IntelliAgent 工具系统文档

本文档详细说明 IntelliAgent 中所有可用的工具及其使用方法。

## 概览

IntelliAgent 提供两类工具，通过统一的 `ToolRegistry` 接口访问：

1. **内置工具** (`core.builtin_tools`) 
   - 直接 Python 实现
   - 无需 MCP 依赖
   - 6 个基础工具：文件、目录、命令执行等
   - 开箱即用，性能最优

2. **外部工具** (MCP 服务) 
   - 通过 Model Context Protocol 集成
   - 第三方远程服务（可选）
   - 灵活扩展，按需配置

所有工具都返回统一的 JSON 格式响应，便于处理和集成。

## 架构说明

```
IntelliAgent 系统
    │
    └─ ToolRegistry (工具注册中心)
           │
           ├─ 内置工具（直接 Python）
           │  └─ core.builtin_tools 模块
           │     ├─ run_shell
           │     ├─ read_file
           │     ├─ write_file
           │     ├─ list_dir
           │     ├─ delete_file
           │     └─ file_exists
           │
           └─ MCP 外部工具（可选）
              └─ mcp_config.json 配置
                 ├─ filesystem
                 ├─ github
                 ├─ brave-search
                 └─ ...其他服务
```

---

## 内置工具（Built-in Tools）

### 1. run_shell - 执行终端命令

执行系统 shell 命令并返回输出结果。

**签名**:
```python
async def run_shell(cmd: str) -> str
```

**参数**:
| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| cmd | string | ✓ | 要执行的 shell 命令，支持管道、重定向等 shell 语法 |

**返回值**:

成功响应:
```json
{
  "status": "ok",
  "output": "命令的标准输出或标准错误",
  "returncode": 0
}
```

错误响应:
```json
{
  "status": "error",
  "error": "错误描述",
  "code": "ERROR_CODE"
}
```

**可能的错误代码**:
- `EMPTY_COMMAND` - 命令参数为空或仅包含空格
- `TIMEOUT` - 命令执行超时（超过 30 秒）
- `EXECUTION_ERROR` - 命令执行失败

**约束条件**:
- 命令执行超时：30 秒
- 支持复杂 shell 表达式（管道、重定向等）

**使用示例**:
```python
# 列出目录
run_shell("ls -la /tmp")
# 输出：文件列表

# 创建文件
run_shell("echo 'Hello' > /tmp/test.txt")

# 运行 Python 代码
run_shell("python -c 'print(1+1)'")
# 输出：2

# 搜索文件
run_shell("find . -name '*.py' | head -10")
```

---

### 2. read_file - 读取文件内容

读取指定路径的文本文件内容。

**签名**:
```python
async def read_file(path: str) -> str
```

**参数**:
| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| path | string | ✓ | 文件路径（绝对路径或相对路径） |

**返回值**:

成功响应:
```json
{
  "status": "ok",
  "content": "文件的完整内容（或截断后的内容）",
  "size": 1024,
  "file_size": 2048,
  "truncated": false
}
```

错误响应:
```json
{
  "status": "error",
  "error": "错误描述",
  "code": "ERROR_CODE"
}
```

**可能的错误代码**:
- `EMPTY_PATH` - 路径参数为空
- `FILE_NOT_FOUND` - 文件不存在
- `IS_DIRECTORY` - 目标是目录而非文件
- `PERMISSION_DENIED` - 无读取权限
- `READ_ERROR` - 读取失败

**约束条件**:
- 内容限制：50,000 字符
- 超过限制会被截断，并在末尾附加截断提示
- 使用 UTF-8 编码，无效字符会被替换

**使用示例**:
```python
# 读取 Markdown 文件
read_file("README.md")

# 读取配置文件
read_file("/etc/hosts")

# 读取源代码
read_file("./src/main.py")

# 读取 JSON 文件
read_file("config.json")
```

---

### 3. write_file - 写入文件内容

将内容写入指定路径的文件。

**签名**:
```python
async def write_file(path: str, content: str) -> str
```

**参数**:
| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| path | string | ✓ | 文件路径（绝对路径或相对路径） |
| content | string | ✓ | 要写入的文件内容 |

**返回值**:

成功响应:
```json
{
  "status": "ok",
  "message": "文件已写入: filename.txt",
  "path": "/absolute/path/to/filename.txt",
  "size": 1024
}
```

错误响应:
```json
{
  "status": "error",
  "error": "错误描述",
  "code": "ERROR_CODE"
}
```

**可能的错误代码**:
- `EMPTY_PATH` - 路径参数为空
- `EMPTY_CONTENT` - 内容参数为空或非字符串
- `CONTENT_TOO_LARGE` - 内容大小超过 1MB 限制
- `INVALID_PATH` - 路径无效或目标已存在且为目录
- `PERMISSION_DENIED` - 无写入权限
- `WRITE_ERROR` - 写入失败

**约束条件**:
- 内容限制：1,000,000 字符（1MB）
- 自动创建不存在的父目录
- 使用 UTF-8 编码
- 如果文件已存在，会被覆盖

**使用示例**:
```python
# 创建简单文本文件
write_file("test.txt", "Hello World")

# 创建 JSON 文件
write_file("/tmp/output.json", '{"key": "value"}')

# 创建 Python 代码文件
write_file("./src/config.py", "CONFIG = {'debug': True}")

# 创建嵌套目录中的文件（父目录自动创建）
write_file("./data/output/result.txt", "Result content")
```

---

### 4. list_dir - 列出目录内容

列出指定目录中的文件和子目录。

**签名**:
```python
async def list_dir(path: str = ".") -> str
```

**参数**:
| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| path | string | ✗ | 目录路径，默认为当前目录 "." |

**返回值**:

成功响应:
```json
{
  "status": "ok",
  "items": [
    {"name": "file.txt", "type": "file", "size": 1024},
    {"name": "subdir", "type": "directory"},
    {"name": "another.py", "type": "file", "size": 2048}
  ],
  "count": 3,
  "directory": "/absolute/path/to/directory",
  "truncated": false
}
```

错误响应:
```json
{
  "status": "error",
  "error": "错误描述",
  "code": "ERROR_CODE"
}
```

**可能的错误代码**:
- `NOT_FOUND` - 目录不存在
- `NOT_A_DIRECTORY` - 路径指向文件而非目录
- `PERMISSION_DENIED` - 无读取权限
- `LIST_ERROR` - 列表操作失败

**约束条件**:
- 最多返回 1,000 项
- 超过限制会在 `truncated` 字段标记
- 目录项不包含 `size` 字段
- 按名称字母顺序排序

**使用示例**:
```python
# 列出当前目录
list_dir(".")

# 列出特定目录
list_dir("/tmp")

# 列出源代码目录
list_dir("./src")

# 解析结果
result = list_dir(".")
items = json.loads(result)
for item in items["items"]:
    print(f"{item['name']} ({item['type']})")
```

---

### 5. delete_file - 删除文件

删除指定路径的文件。

**签名**:
```python
async def delete_file(path: str) -> str
```

**参数**:
| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| path | string | ✓ | 文件路径 |

**返回值**:

成功响应:
```json
{
  "status": "ok",
  "message": "文件已删除: filename.txt",
  "path": "/absolute/path/to/filename.txt"
}
```

错误响应:
```json
{
  "status": "error",
  "error": "错误描述",
  "code": "ERROR_CODE"
}
```

**可能的错误代码**:
- `EMPTY_PATH` - 路径参数为空
- `NOT_FOUND` - 文件不存在
- `IS_DIRECTORY` - 目标是目录而非文件（禁止删除目录）
- `PERMISSION_DENIED` - 无删除权限
- `DELETE_ERROR` - 删除失败

**约束条件**:
- 仅支持删除文件，不支持删除目录
- 删除后无法恢复

**使用示例**:
```python
# 删除临时文件
delete_file("temp.txt")

# 删除缓存文件
delete_file("/tmp/cache.json")

# 删除输出文件
delete_file("./output/result.txt")
```

---

### 6. file_exists - 检查文件或目录是否存在

检查指定路径是否存在，并返回类型信息。

**签名**:
```python
async def file_exists(path: str) -> str
```

**参数**:
| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| path | string | ✓ | 文件或目录路径 |

**返回值**:

文件/目录存在:
```json
{
  "status": "ok",
  "exists": true,
  "type": "file"
}
```

文件/目录不存在:
```json
{
  "status": "ok",
  "exists": false
}
```

错误响应:
```json
{
  "status": "error",
  "error": "错误描述",
  "code": "ERROR_CODE"
}
```

**可能的错误代码**:
- `EMPTY_PATH` - 路径参数为空
- `CHECK_ERROR` - 检查操作失败

**使用示例**:
```python
# 检查文件是否存在
file_exists("README.md")
# 返回：{"status": "ok", "exists": true, "type": "file"}

# 检查目录是否存在
file_exists("/tmp")
# 返回：{"status": "ok", "exists": true, "type": "directory"}

# 检查不存在的路径
file_exists("./nonexistent.txt")
# 返回：{"status": "ok", "exists": false}
```

---

## 工具返回值格式

所有工具返回 JSON 格式的字符串，必须解析后使用：

```python
import json

result_str = run_shell("ls")
result = json.loads(result_str)

if result["status"] == "ok":
    print(result["output"])
else:
    print(f"错误: {result['error']} (代码: {result['code']})")
```

### 标准响应格式

**成功响应** (`status: "ok"`):
```json
{
  "status": "ok",
  "field1": "value1",
  "field2": "value2"
}
```

**错误响应** (`status: "error"`):
```json
{
  "status": "error",
  "error": "人类可读的错误描述",
  "code": "ERROR_CODE"
}
```

---

## 外部工具（MCP 服务）

除了内置工具外，IntelliAgent 还支持通过 MCP（Model Context Protocol）集成外部工具服务。

### 支持的服务类型

#### 连接方式

1. **stdio** - 本地进程通信
   - 通过标准输入输出与本地进程通信
   - 适用于 Node.js、Python 等本地工具

2. **HTTP/SSE** - 远程服务
   - 通过 HTTP 连接远程 MCP 服务
   - 支持自定义 Headers（如认证令牌）

### 已知的可用外部服务

#### 文件系统工具 (filesystem)
- 提供更高级的文件操作（读写、删除、搜索等）
- 包含目录操作（创建、删除、遍历）

#### GitHub 工具 (github)
- 访问 GitHub API 功能
- 查看仓库信息、发起 PR、创建 Issue 等

#### 搜索工具 (brave-search)
- 提供互联网搜索能力
- 返回相关搜索结果

#### Context7 工具 (context7)
- 查询编程库和框架的文档
- 提供代码示例和最佳实践

#### 思维工具 (sequential-thinking)
- 支持结构化的思维过程
- 用于复杂问题的逐步推理

### 配置外部 MCP 服务

详见 `docs/TOOL_INTEGRATION.md`

---

## 错误处理最佳实践

### 检查响应状态

```python
import json

response = tool_registry.get_tool("run_shell")("some command")
result = json.loads(response)

if result["status"] == "ok":
    # 处理成功情况
    print(result["output"])
else:
    # 处理错误情况
    error_code = result.get("code", "UNKNOWN")
    error_msg = result.get("error", "未知错误")
    logger.error(f"工具执行失败 [{error_code}]: {error_msg}")
```

### 按错误代码处理

```python
if result["status"] == "error":
    code = result["code"]
    
    if code == "FILE_NOT_FOUND":
        # 处理文件不存在的情况
        logger.info(f"文件不存在：{path}")
    elif code == "PERMISSION_DENIED":
        # 处理权限问题
        logger.error(f"权限不足：{path}")
    elif code == "TIMEOUT":
        # 处理超时
        logger.error("命令执行超时")
    else:
        # 处理其他错误
        logger.error(f"未知错误: {result['error']}")
```

---

## 性能和限制

### 默认限制

| 工具 | 限制 | 说明 |
|------|------|------|
| run_shell | 30 秒超时 | 命令执行最多 30 秒 |
| read_file | 50,000 字符 | 超过限制会被截断 |
| write_file | 1,000,000 字符 | 不支持超过 1MB 的文件 |
| list_dir | 1,000 项 | 目录超过 1,000 项会被截断 |

### 优化建议

1. **大文件处理**
   - 使用 `run_shell("head -n 100 file.txt")` 查看文件开头
   - 使用 `run_shell("wc -l file.txt")` 查看文件行数
   - 分块读取大文件

2. **目录列表**
   - 使用 `run_shell("ls -la | head -50")` 限制输出
   - 使用 `run_shell("find . -type f -name '*.py'")` 搜索特定文件

3. **命令执行**
   - 使用管道和重定向优化输出
   - 避免交互式命令
   - 使用 `2>/dev/null` 抑制错误输出（如不需要）

---

## 故障排查

### 常见问题

**Q: 为什么文件读取被截断了？**

A: 内容超过 50,000 字符限制。使用 `run_shell` 配合 `head`、`tail`、`grep` 等命令来查看文件的特定部分。

**Q: 如何处理包含特殊字符的文件名？**

A: 使用引号或转义。例如：
```python
run_shell("cat 'file with spaces.txt'")
read_file("file with spaces.txt")  # 自动处理
```

**Q: 为什么 run_shell 超时？**

A: 命令执行超过 30 秒。考虑：
- 优化命令性能
- 分解成多个简单命令
- 使用后台进程和管道

**Q: 如何安全地删除文件？**

A: 使用 `file_exists` 检查后再删除：
```python
if file_exists(path)["exists"]:
    delete_file(path)
```

---

## 相关文档

- [MCP 集成指南](docs/TOOL_INTEGRATION.md) - 如何配置和使用外部 MCP 服务
- [README.md](README.md) - 项目主文档
- [配置说明](.env.example) - 工具相关的环境变量

