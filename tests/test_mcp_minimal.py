#!/usr/bin/env python3
"""
MCP 最小同步测试
"""
from core.tool_registry import ToolRegistry

def test_mcp_minimal_sync():
    tr = ToolRegistry()
    tools = tr.list_tools()
    assert len(tools) >= 1
    assert 'run_shell' in tools
    tr.cleanup()
    print('✅ MCP 最小同步测试通过')

if __name__ == '__main__':
    test_mcp_minimal_sync()
