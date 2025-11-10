from core.react_loop import react_loop
from utils.logger import logger

class Executor:
    def __init__(self, tools, memory):
        self.tools = tools
        self.memory = memory

    def execute_plan(self, plan):
        logger.info("开始执行计划...")
        for step in plan:
            logger.info(f"➡️ 执行步骤 {step['id']}: {step['goal']}")
            react_loop(step, self.tools, self.memory)
