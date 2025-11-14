#!/usr/bin/env python3
"""
测试 ToolRegistry 使用 sequentialthinking 工具
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core.tool_registry import ToolRegistry
from utils.logger import logger


def test_sequential_thinking():
    """测试使用 sequentialthinking 工具"""
    logger.info("=" * 60)
    logger.info("开始测试 ToolRegistry 的 sequentialthinking 工具")
    logger.info("=" * 60)
    
    # 创建工具注册中心
    registry = ToolRegistry()
    registry.initialize()
    
    # 列出所有可用工具
    logger.info(f"\n可用工具列表: {registry.list_tools()}")
    
    # 检查 sequentialthinking 工具是否可用
    if "sequentialthinking" not in registry.list_tools():
        logger.error("❌ sequentialthinking 工具不可用")
        logger.info("请确保在 mcp_config.json 中配置了 sequential-thinking 服务器")
        return
    
    logger.info("\n✅ sequentialthinking 工具已就绪")
    
    # 测试用例1: 简单的数学问题
    logger.info("\n" + "=" * 60)
    logger.info("测试用例1: 解决数学问题")
    logger.info("=" * 60)
    
    tool = registry.get_tool("sequentialthinking")
    
    try:
        # 第一个思考步骤
        result = tool(
            thought="问题是: 如果一个商店有100个苹果，卖出了30%，又进货了50个，现在有多少个苹果？首先计算卖出的数量。",
            thoughtNumber=1,
            totalThoughts=4,
            nextThoughtNeeded=True
        )
        logger.info(f"思考步骤1结果: {result}")
        
        # 第二个思考步骤
        result = tool(
            thought="卖出了100 × 0.3 = 30个苹果，所以剩余100 - 30 = 70个苹果。",
            thoughtNumber=2,
            totalThoughts=4,
            nextThoughtNeeded=True
        )
        logger.info(f"思考步骤2结果: {result}")
        
        # 第三个思考步骤
        result = tool(
            thought="然后又进货了50个，所以现在有70 + 50 = 120个苹果。",
            thoughtNumber=3,
            totalThoughts=4,
            nextThoughtNeeded=True
        )
        logger.info(f"思考步骤3结果: {result}")
        
        # 最后一个思考步骤
        result = tool(
            thought="答案验证: 初始100个，卖出30个剩70个，进货50个得120个。计算正确，最终答案是120个苹果。",
            thoughtNumber=4,
            totalThoughts=4,
            nextThoughtNeeded=False
        )
        logger.info(f"最终结果: {result}")
        
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return
    
    # 测试用例2: 逻辑推理问题
    logger.info("\n" + "=" * 60)
    logger.info("测试用例2: 逻辑推理")
    logger.info("=" * 60)
    
    try:
        # 第一个思考步骤
        result = tool(
            thought="问题: 三个人A、B、C，其中一个总说真话，一个总说假话，一个随机。A说'B是说假话的'，B说'C是随机的'。推理出谁是谁。首先分析A的陈述。",
            thoughtNumber=1,
            totalThoughts=5,
            nextThoughtNeeded=True
        )
        logger.info(f"推理步骤1: {result}")
        
        # 第二个思考步骤
        result = tool(
            thought="如果A说真话，那么B说假话。但如果B说假话说'C是随机的'，那么C不是随机的，C应该是说真话的。但这与A说真话矛盾。",
            thoughtNumber=2,
            totalThoughts=5,
            nextThoughtNeeded=True
        )
        logger.info(f"推理步骤2: {result}")
        
        # 第三个思考步骤
        result = tool(
            thought="如果A说假话，那么B不是说假话的（即B是说真话或随机）。B说'C是随机的'，如果B说真话，那么C确实是随机的，A说假话，这样三个角色都分配了，逻辑成立。",
            thoughtNumber=3,
            totalThoughts=5,
            nextThoughtNeeded=True
        )
        logger.info(f"推理步骤3: {result}")
        
        # 第四个思考步骤
        result = tool(
            thought="验证: A说假话，B说真话，C是随机的。A说'B是说假话的'是假话✓，B说'C是随机的'是真话✓。逻辑一致。",
            thoughtNumber=4,
            totalThoughts=5,
            nextThoughtNeeded=True
        )
        logger.info(f"推理步骤4: {result}")
        
        # 最后一个思考步骤
        result = tool(
            thought="结论: A是说假话的人，B是说真话的人，C是随机说话的人。",
            thoughtNumber=5,
            totalThoughts=5,
            nextThoughtNeeded=False
        )
        logger.info(f"最终结论: {result}")
        
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return
    
    logger.info("\n" + "=" * 60)
    logger.info("✅ 所有测试完成")
    logger.info("=" * 60)
    
    # 清理资源
    registry.cleanup()


if __name__ == "__main__":
    test_sequential_thinking()
