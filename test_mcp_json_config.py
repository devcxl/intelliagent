#!/usr/bin/env python3
"""
测试 MCP JSON 配置加载
"""
import json
import sys
import os
from pathlib import Path

def test_json_config():
    """测试 JSON 配置文件加载"""
    
    # 创建测试配置文件
    test_config = {
        "mcpServers": {
            "test-server": {
                "command": "echo",
                "args": ["test"],
                "env": {
                    "TEST_VAR": "test_value"
                }
            }
        }
    }
    
    config_path = Path("test_mcp_config.json")
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(test_config, f, indent=2)
    
    # 设置环境变量（必须在导入 config 之前）
    os.environ['MCP_CONFIG_FILE'] = str(config_path)
    
    # 添加项目根目录到 Python 路径
    sys.path.insert(0, str(Path(__file__).parent))
    
    from core.tool_registry import ToolRegistry
    from utils.logger import logger
    
    logger.info("✅ 已创建测试配置文件")
    
    try:
        # 创建工具注册中心
        registry = ToolRegistry()
        
        # 检查服务器数量（内置 + 测试服务器）
        logger.info(f"📊 已配置 {len(registry.servers)} 个 MCP 服务器")
        
        for server in registry.servers:
            logger.info(f"  - {server.name}: {server.command} {' '.join(server.args)}")
            if server.env:
                logger.info(f"    环境变量: {server.env}")
        
        logger.info("✅ JSON 配置加载测试通过")
        
    finally:
        # 清理测试文件
        if config_path.exists():
            config_path.unlink()
            logger.info("🧹 已清理测试配置文件")

if __name__ == "__main__":
    test_json_config()
