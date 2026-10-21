"""MCP 工具模型侧导出保真测试（US16）。"""

from __future__ import annotations

from src.core.engine import tool_schemas
from src.plugins.mcp.tools import McpTool
from tests.plugins.mcp.fakes import FakeConnection


class TestModelSideExportFidelity:
    """US16 高优先级回归（PR #73 审查 Spec high）：MCP inputSchema 经模型侧导出后嵌套保真。

    桥接路径是 engine.tool_schemas（原生 JSON Schema 全量透传）；旧 registry._to_openai_function
    的扁平化降级属 #64 删除的旧代码，不在本路径上。
    """

    def test_nested_schema_survives_model_side_export(self) -> None:
        nested_schema = {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["auto", "manual"]},
                "targets": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "flags": {"type": "array", "items": {"type": "integer"}},
                        },
                        "required": ["path"],
                    },
                },
            },
            "required": ["mode"],
        }
        tool = McpTool(
            name="mcp_srv_complex",
            server="srv",
            tool_name="complex",
            description="复杂工具",
            parameters=nested_schema,
            connection=FakeConnection(),
        )
        exported = tool_schemas({"mcp_srv_complex": tool})
        assert len(exported) == 1
        function = exported[0]["function"]
        assert function["parameters"] == nested_schema  # 嵌套/enum/items 原样到模型 payload
        assert function["parameters"]["properties"]["targets"]["items"]["properties"]["flags"]["items"] == {
            "type": "integer"
        }
