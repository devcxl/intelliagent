# 测试和示例

本目录包含所有测试文件和使用示例。

## 📁 文件说明

### 测试文件

- **test_registry.py** - 工具注册中心完整测试
- **test_mcp.py** - MCP 协议测试
- **test_mcp_minimal.py** - MCP 最小化测试
- **check_mcp.py** - MCP 连接检查

### 示例文件

- **example_usage.py** - 快速上手示例（推荐从这里开始）
- **quick_test.py** - 快速测试脚本

## 🚀 运行测试

### 运行所有测试

```bash
# 方式 1: 使用 pytest
pytest tests/

# 方式 2: 直接运行
python3 tests/test_registry.py
```

### 运行示例

```bash
# 快速示例（推荐）
python3 tests/example_usage.py

# 快速测试
python3 tests/quick_test.py
```

### 运行特定测试

```bash
# 工具注册测试
python3 tests/test_registry.py

# MCP 测试
python3 tests/test_mcp.py

# MCP 连接检查
python3 tests/check_mcp.py
```

## 📝 测试覆盖

| 测试文件 | 覆盖范围 |
|---------|----------|
| test_registry.py | 工具注册、工具调用、资源管理 |
| test_mcp.py | MCP 协议通信、会话管理 |
| example_usage.py | 完整使用流程、最佳实践 |

## 🧪 添加新测试

1. 在 `tests/` 目录创建新文件，命名为 `test_*.py`
2. 导入需要的模块
3. 编写测试函数
4. 运行验证

示例：

```python
# tests/test_new_feature.py
from core.tool_registry import ToolRegistry

def test_new_feature():
    registry = ToolRegistry()
    registry.initialize()
    # 测试逻辑
    registry.cleanup()

if __name__ == "__main__":
    test_new_feature()
```

## ⚠️ 注意事项

1. **MCP Server 必须可用** - 确保 `mcp_server.py` 正常运行
2. **清理资源** - 测试结束后调用 `cleanup()`
3. **独立运行** - 每个测试应该能够独立运行

## 📖 相关文档

- [完整文档](../docs/README.md)
- [快速参考](../docs/QUICKREF.md)
- [架构文档](../docs/MCP_PURE_MODE.md)

---

**测试套件版本**: 1.0.0  
**最后更新**: 2025-11-03

