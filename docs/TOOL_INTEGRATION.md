# MCP 工具集成指南

本文档说明如何在 IntelliAgent 中集成和使用外部 MCP（Model Context Protocol）服务。

## 概览

IntelliAgent 支持通过 MCP 协议集成外部工具和服务。这使得系统可以轻松扩展，支持各种第三方功能，如文件系统操作、搜索、GitHub 集成等。

### 架构

```
┌─────────────────┐
│  IntelliAgent   │
│   核心系统      │
└────────┬────────┘
         │
    ┌────┴─────────────────────┬──────────────────┐
    │                          │                  │
    ▼                          ▼                  ▼
┌─────────────┐          ┌──────────┐      ┌──────────────┐
│ 内置工具    │          │ stdio    │      │ HTTP/SSE     │
│(mcp_server) │          │ 本地进程 │      │ 远程服务     │
└─────────────┘          └──────────┘      └──────────────┘
   (6 个)                 (filesystem,      (brave-search,
   - run_shell          github,etc)        context7,etc)
   - read_file
   - write_file
   - list_dir
   - delete_file
   - file_exists
```

---

## 配置外部 MCP 服务

### 配置文件位置

配置文件默认位于项目根目录：
```
mcp_config.json
```

### 配置文件格式

```json
{
  "mcpServers": {
    "服务器名称": {
      "type": "stdio|http|sse",
      // ... 根据类型填写相应配置
    }
  }
}
```

---

## 连接方式详解

### 1. stdio - 本地进程通信

适用于本地可执行的 MCP 服务。

**配置格式**:
```json
{
  "mcpServers": {
    "filesystem": {
      "type": "stdio",
      "command": "npx",
      "args": ["@modelcontextprotocol/server-filesystem"],
      "env": {}
    }
  }
}
```

**参数说明**:
| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| type | string | ✓ | 必须为 "stdio" |
| command | string | ✓ | 可执行命令（npx、node、python 等） |
| args | array | ✓ | 命令参数 |
| env | object | ✗ | 环境变量（可选） |

**示例 - Node.js MCP 服务**:
```json
{
  "filesystem": {
    "type": "stdio",
    "command": "npx",
    "args": ["@modelcontextprotocol/server-filesystem"],
    "env": {}
  }
}
```

**示例 - Python MCP 服务**:
```json
{
  "custom_tool": {
    "type": "stdio",
    "command": "python",
    "args": ["custom_mcp_server.py"],
    "env": {
      "PYTHON_UNBUFFERED": "1"
    }
  }
}
```

### 2. HTTP - HTTP 连接

适用于通过 HTTP 提供的远程 MCP 服务。

**配置格式**:
```json
{
  "mcpServers": {
    "remote_service": {
      "type": "http",
      "url": "https://api.example.com/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_API_KEY"
      }
    }
  }
}
```

**参数说明**:
| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| type | string | ✓ | 必须为 "http" |
| url | string | ✓ | MCP 服务的 HTTP 地址 |
| headers | object | ✗ | 自定义 HTTP 请求头（认证等） |

### 3. SSE - 服务器发送事件

适用于支持 SSE 的流式 MCP 服务。

**配置格式**:
```json
{
  "mcpServers": {
    "streaming_service": {
      "type": "sse",
      "url": "https://stream.example.com/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_API_KEY"
      }
    }
  }
}
```

**参数说明**:
| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| type | string | ✓ | 必须为 "sse" |
| url | string | ✓ | SSE 服务的 URL |
| headers | object | ✗ | 自定义 HTTP 请求头（认证等） |

---

## 已知可用的 MCP 服务

### Filesystem (文件系统)

**提供的功能**:
- 高级文件读写操作
- 目录创建和删除
- 文件搜索
- 权限管理

**配置示例**:
```json
{
  "filesystem": {
    "type": "stdio",
    "command": "npx",
    "args": ["@modelcontextprotocol/server-filesystem"]
  }
}
```

**要求**:
- Node.js ≥ 14
- npm 或 yarn

### GitHub

**提供的功能**:
- 仓库信息查询
- Issue 和 PR 操作
- 代码搜索
- 工作流管理

**配置示例**:
```json
{
  "github": {
    "type": "stdio",
    "command": "npx",
    "args": ["@modelcontextprotocol/server-github"],
    "env": {
      "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_xxxxxxxxxxxxxxxxxxxx"
    }
  }
}
```

**要求**:
- GitHub 个人访问令牌 (Personal Access Token)
- 令牌需要 `repo` 和 `gist` 权限

**获取令牌**:
1. 访问 https://github.com/settings/tokens
2. 点击 "Generate new token"
3. 选择所需权限
4. 复制令牌并保存到 `.env` 中

### Brave Search (网络搜索)

**提供的功能**:
- 互联网搜索
- Web 结果聚合
- 新闻搜索

**配置示例**:
```json
{
  "brave-search": {
    "type": "stdio",
    "command": "npx",
    "args": ["@modelcontextprotocol/server-brave-search"],
    "env": {
      "BRAVE_API_KEY": "YOUR_API_KEY"
    }
  }
}
```

**要求**:
- Brave Search API 密钥
- 访问 https://api.search.brave.com/ 获取

### Context7 (编程文档查询)

**提供的功能**:
- 编程库和框架文档查询
- 代码示例搜索
- API 参考

**配置示例**:
```json
{
  "context7": {
    "type": "stdio",
    "command": "npx",
    "args": ["@modelcontextprotocol/server-context7"],
    "env": {
      "CONTEXT7_API_KEY": "YOUR_API_KEY"
    }
  }
}
```

### Sequential Thinking (思维过程)

**提供的功能**:
- 结构化思维支持
- 逐步推理过程
- 复杂问题分解

**配置示例**:
```json
{
  "sequential-thinking": {
    "type": "stdio",
    "command": "npx",
    "args": ["@modelcontextprotocol/server-sequential-thinking"]
  }
}
```

---

## 完整配置示例

### 最小化配置（仅内置工具）

```json
{
  "mcpServers": {}
}
```

### 推荐开发配置

```json
{
  "mcpServers": {
    "filesystem": {
      "type": "stdio",
      "command": "npx",
      "args": ["@modelcontextprotocol/server-filesystem"]
    },
    "github": {
      "type": "stdio",
      "command": "npx",
      "args": ["@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}"
      }
    }
  }
}
```

### 完整生产配置

```json
{
  "mcpServers": {
    "filesystem": {
      "type": "stdio",
      "command": "npx",
      "args": ["@modelcontextprotocol/server-filesystem"]
    },
    "github": {
      "type": "stdio",
      "command": "npx",
      "args": ["@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}"
      }
    },
    "brave-search": {
      "type": "stdio",
      "command": "npx",
      "args": ["@modelcontextprotocol/server-brave-search"],
      "env": {
        "BRAVE_API_KEY": "${BRAVE_API_KEY}"
      }
    },
    "context7": {
      "type": "stdio",
      "command": "npx",
      "args": ["@modelcontextprotocol/server-context7"],
      "env": {
        "CONTEXT7_API_KEY": "${CONTEXT7_API_KEY}"
      }
    }
  }
}
```

---

## 环境变量配置

### 方式 1: `.env` 文件（推荐）

在项目根目录创建 `.env` 文件：

```bash
# MCP 服务配置文件
MCP_CONFIG_FILE=mcp_config.json

# GitHub
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx

# Brave Search
BRAVE_API_KEY=your_api_key_here

# Context7
CONTEXT7_API_KEY=your_api_key_here
```

在 `mcp_config.json` 中使用 `${VARIABLE_NAME}` 引用：

```json
{
  "mcpServers": {
    "github": {
      "type": "stdio",
      "command": "npx",
      "args": ["@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}"
      }
    }
  }
}
```

### 方式 2: 直接环境变量

在运行 IntelliAgent 前设置环境变量：

```bash
export GITHUB_TOKEN=ghp_xxxx
export BRAVE_API_KEY=xxxx
python main.py "your task"
```

---

## 故障排查

### 检查配置有效性

```bash
# 验证 JSON 格式
python -m json.tool mcp_config.json

# 查看 IntelliAgent 初始化日志
python main.py "test" 2>&1 | head -50
```

### 常见问题

#### Q: 为什么无法连接到 stdio 服务？

A: 检查以下内容：
1. 确认命令和参数正确
2. 确认本地已安装必要的工具（npx、python 等）
3. 查看错误日志了解具体原因
4. 尝试手动运行命令测试

```bash
npx @modelcontextprotocol/server-filesystem
```

#### Q: HTTP 服务连接超时？

A: 检查以下内容：
1. URL 是否正确且服务在线
2. 网络连接是否正常
3. 认证信息（Authorization header）是否正确
4. 服务是否需要代理配置

#### Q: "找不到工具"错误？

A: 配置已加载但工具无法使用：
1. 检查服务是否成功启动
2. 确认工具名称拼写正确
3. 查看初始化日志
4. 尝试重启 IntelliAgent

#### Q: 环境变量替换不工作？

A: 注意事项：
1. 使用 `${VAR_NAME}` 格式（不是 `$VAR_NAME`）
2. 确保 `.env` 文件存在且格式正确
3. 变量名必须完全匹配
4. 某些特殊字符需要转义

```json
// ✓ 正确
"env": {
  "GITHUB_TOKEN": "${GITHUB_TOKEN}"
}

// ✗ 错误
"env": {
  "GITHUB_TOKEN": "$GITHUB_TOKEN"
}
```

---

## 性能优化

### 减少启动时间

只配置需要的服务：

```json
{
  "mcpServers": {
    "filesystem": {
      "type": "stdio",
      "command": "npx",
      "args": ["@modelcontextprotocol/server-filesystem"]
    }
  }
}
```

### 网络优化

对于远程 HTTP/SSE 服务：

```json
{
  "remote-service": {
    "type": "http",
    "url": "https://api.example.com/mcp",
    "headers": {
      "Authorization": "Bearer YOUR_TOKEN",
      "Connection": "keep-alive"
    }
  }
}
```

---

## 安全考虑

### API 密钥管理

- **使用环境变量存储敏感信息**

```bash
# ✓ 安全做法
export GITHUB_TOKEN=ghp_xxxx
python main.py "task"

# ✗ 不安全：直接在配置文件中存储
# "GITHUB_TOKEN": "ghp_xxxx"  # 不要这样做
```

- **避免提交敏感配置到 Git**

```bash
# .gitignore
.env
mcp_config.json
```

### 权限最小化

为 API 密钥授予最小必要权限：

- GitHub: 使用 Fine-grained Personal Access Tokens
- Brave Search: 限制 API 请求量
- 其他服务: 查阅对应文档

---

## 与内置工具的区别

| 特性 | 内置工具 | 外部工具 |
|------|---------|--------|
| 依赖 | 无 | 需要额外安装 |
| 性能 | 快（无进程开销） | 稍慢（进程/网络） |
| 可用性 | 始终可用 | 需要正确配置 |
| 功能 | 基础文件/命令操作 | 高级功能 |
| 更新 | 跟随系统更新 | 独立更新 |

---

## 扩展：自定义 MCP 服务

### 创建 Python MCP 服务

```python
# custom_tool.py
from mcp.server import Server
from mcp.types import TextContent

server = Server("my-custom-tool")

@server.tool()
def my_custom_tool(param: str) -> str:
    """自定义工具说明"""
    return f"处理结果: {param}"

if __name__ == "__main__":
    import sys
    server.run(transport='stdio')
```

配置:
```json
{
  "custom-tool": {
    "type": "stdio",
    "command": "python",
    "args": ["custom_tool.py"]
  }
}
```

---

## 相关文档

- [工具系统文档](docs/TOOLS.md) - 内置工具详细说明
- [README.md](README.md) - 项目主文档
- [配置示例](.env.example) - 环境变量说明

---

## 获取帮助

如遇到问题，请：

1. 检查本文档的"故障排查"部分
2. 查看项目 Issue 或讨论
3. 参考相关 MCP 服务的官方文档
4. 检查项目日志（`LOG_LEVEL=DEBUG`）
