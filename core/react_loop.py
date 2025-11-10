#!/usr/bin/env python3
"""
ReAct 循环模块
实现 Reason + Act 循环逻辑
"""
from utils.logger import logger


def react_loop(step, tools, memory):
    """
    执行 ReAct 循环

    Args:
        step: 任务步骤 {'id': int, 'goal': str, 'tool': str, 'args': dict}
        tools: 工具注册中心
        memory: 记忆模块
    """
    tool_name = step.get("tool", "none")
    args = step.get("args", {})

    logger.info(f"🧩 调用工具: {tool_name} 参数: {args}")

    try:
        if tool_name == "none" or not tool_name:
            logger.warning("⚠️ 未指定工具，跳过执行")
            memory.add_observation({
                "step": step["id"],
                "goal": step["goal"],
                "status": "skipped",
                "reason": "未指定工具"
            })
            return

        # 初始化工具注册中心（如果需要）
        if not hasattr(tools, '_initialized') or not tools._mcp_registry._initialized:
            tools.initialize()

        # 获取工具
        tool_func = tools.get_tool(tool_name)

        # 执行工具
        result = tool_func(**args)

        logger.info(f"✅ 工具执行成功: {result}")

        # 保存观察结果
        memory.add_observation({
            "step": step["id"],
            "goal": step["goal"],
            "tool": tool_name,
            "args": args,
            "result": result,
            "status": "success"
        })

    except Exception as e:
        logger.error(f"执行失败: {e}")
        memory.add_observation({
            "step": step["id"],
            "goal": step["goal"],
            "tool": tool_name,
            "error": str(e),
            "status": "failed"
        })

