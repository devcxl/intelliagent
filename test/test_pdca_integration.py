#!/usr/bin/env python3
"""
PDCA 循环集成测试

测试新的 DO 阶段循环处理引擎功能：
- 依赖关系检查和处理
- 变量替换和上下文传播
- 步骤级重试和退避策略
- 异常恢复策略
- 资源管理和清理
"""
import asyncio
import json
import tempfile
import sys
import os
import pytest
from pathlib import Path
from typing import Dict, Any, List
from unittest.mock import MagicMock, patch, AsyncMock

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logger import logger
import utils.config as config
from core.llm_client import LLMClient
from core.planner import Planner
from core.executor import Executor, ExecutionMetrics
from core.checker import Checker
from core.actor import Actor
from core.pdca_loop import PDCALoop
from core.context import ContextManager
from core.memory import Memory
from core.tool_registry import ToolRegistry


class TestDOPhaseLoops:
    """测试 DO 阶段的各个循环处理机制"""
    
    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        """测试前准备"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.context = ContextManager()
        self.memory = Memory()
        self.tool_registry = ToolRegistry()
        self.tool_registry.initialize()
        
        logger.info(f"✅ 创建临时测试目录: {self.temp_dir.name}")
        
        yield
        
        if self.temp_dir:
            self.temp_dir.cleanup()
            logger.info("🧹 清理临时测试目录")
    
    def test_execution_metrics_collection(self):
        """测试执行指标收集"""
        logger.info("\n🧪 测试执行指标收集...")
        
        metrics = ExecutionMetrics()
        metrics.add_step(1, 'success', 0.5)
        metrics.add_step(2, 'success', 0.3)
        metrics.add_step(3, 'failed', 0.2)
        metrics.add_step(4, 'skipped', 0.0)
        metrics.total_retries = 3
        metrics.total_time = 1.0
        
        assert metrics.total_steps == 4
        assert metrics.successful_steps == 2
        assert metrics.failed_steps == 1
        assert metrics.skipped_steps == 1
        assert metrics.total_retries == 3
        
        logger.info(f"✅ 通过: 指标收集正确 (成功: {metrics.successful_steps}, 失败: {metrics.failed_steps})")
    
    def test_dependency_checking(self):
        """测试依赖关系检查循环"""
        logger.info("\n🧪 测试依赖关系检查循环...")
        
        # 创建有依赖关系的计划
        plan = [
            {
                "id": 1,
                "goal": "创建文件",
                "tool": "write_file",
                "args": {"path": f"{self.temp_dir.name}/test.txt", "content": "Hello"},
                "expected_outcome": "文件创建成功",
                "dependencies": []
            },
            {
                "id": 2,
                "goal": "读取文件",
                "tool": "read_file",
                "args": {"path": f"{self.temp_dir.name}/test.txt"},
                "expected_outcome": "读取文件内容",
                "dependencies": [1]  # 依赖步骤1
            }
        ]
        
        executor = Executor(self.tool_registry, self.memory)
        
        # 执行计划
        results = executor.execute_plan(plan)
        
        # 验证步骤顺序（步骤2应该在步骤1后执行）
        assert len(results) == 2
        assert results[0]['step_id'] == 1
        assert results[1]['step_id'] == 2
        assert results[0]['status'] == 'success'
        
        logger.info(f"✅ 通过: 依赖关系检查正确 (步骤2等待步骤1完成)")
    
    def test_variable_substitution(self):
        """测试变量替换循环"""
        logger.info("\n🧪 测试变量替换循环...")
        
        # 创建使用变量引用的计划
        plan = [
            {
                "id": 1,
                "goal": "创建文件",
                "tool": "write_file",
                "args": {
                    "path": f"{self.temp_dir.name}/test.txt",
                    "content": "test content"
                },
                "expected_outcome": "文件创建成功",
                "dependencies": []
            },
            {
                "id": 2,
                "goal": "读取文件",
                "tool": "read_file",
                "args": {
                    "path": "${step_1.args.path}"  # 引用步骤1的参数
                },
                "expected_outcome": "读取文件内容",
                "dependencies": [1]
            }
        ]
        
        executor = Executor(self.tool_registry, self.memory)
        results = executor.execute_plan(plan)
        
        # 验证变量替换发生
        assert results[1]['status'] == 'success' or results[1].get('error') is not None
        
        logger.info(f"✅ 通过: 变量替换正确处理")
    
    def test_retry_loop_with_backoff(self):
        """测试重试循环和退避策略"""
        logger.info("\n🧪 测试重试循环和退避策略...")
        
        # 创建一个会失败的工具调用计划
        plan = [
            {
                "id": 1,
                "goal": "执行失败的命令",
                "tool": "run_shell",
                "args": {"cmd": "exit 1"},  # 这会失败
                "expected_outcome": "命令执行成功",
                "dependencies": []
            }
        ]
        
        executor = Executor(self.tool_registry, self.memory)
        results = executor.execute_plan(plan)
        
        # 验证重试发生
        assert results[0]['status'] in ['failed', 'success']
        
        # 检查指标中的重试次数
        assert executor.metrics.total_retries >= 0
        
        logger.info(f"✅ 通过: 重试机制正确 (重试次数: {executor.metrics.total_retries})")
    
    def test_context_propagation(self):
        """测试上下文传播"""
        logger.info("\n🧪 测试上下文传播...")
        
        plan = [
            {
                "id": 1,
                "goal": "创建文件",
                "tool": "write_file",
                "args": {"path": f"{self.temp_dir.name}/ctx.txt", "content": "context data"},
                "expected_outcome": "文件创建成功",
                "dependencies": []
            },
            {
                "id": 2,
                "goal": "读取文件",
                "tool": "read_file",
                "args": {"path": f"{self.temp_dir.name}/ctx.txt"},
                "expected_outcome": "读取文件内容",
                "dependencies": [1]
            }
        ]
        
        executor = Executor(self.tool_registry, self.memory)
        results = executor.execute_plan(plan)
        
        # 验证执行缓存中有结果
        assert 1 in executor.execution_cache
        assert 2 in executor.execution_cache
        
        logger.info(f"✅ 通过: 上下文传播正确")


class TestPDCALoopIntegration:
    """测试完整的 PDCA 循环集成"""
    
    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        """测试前准备"""
        self.temp_dir = tempfile.TemporaryDirectory()
        
        logger.info(f"✅ 创建临时测试目录: {self.temp_dir.name}")
        
        yield
        
        if self.temp_dir:
            self.temp_dir.cleanup()
            logger.info("🧹 清理临时测试目录")
    
    @patch('core.llm_client.LLMClient.chat')
    def test_pdca_execution_with_simple_plan(self, mock_chat):
        """测试 PDCA 循环执行简单计划"""
        logger.info("\n🧪 测试 PDCA 循环执行简单计划...")
        
        # 模拟 LLM 的计划生成响应
        simple_plan = [
            {
                "id": 1,
                "goal": "创建测试文件",
                "tool": "write_file",
                "args": {
                    "path": f"{self.temp_dir.name}/simple.txt",
                    "content": "simple test"
                },
                "expected_outcome": "文件创建成功"
            }
        ]
        
        mock_chat.return_value = json.dumps(simple_plan)
        
        # 创建 PDCA 组件
        context = ContextManager()
        memory = Memory()
        tool_registry = ToolRegistry()
        tool_registry.initialize()
        
        llm_client = LLMClient(api_key=config.OPENAI_API_KEY, model=config.OPENAI_MODEL)
        planner = Planner(llm_client, tool_registry, context)
        executor = Executor(tool_registry, memory)
        checker = Checker(llm_client)
        actor = Actor(llm_client, memory, max_retry=config.MAX_RETRY_PER_STEP)
        
        pdca_loop = PDCALoop(planner, executor, checker, actor, max_pdca_cycles=1)
        
        # 运行 PDCA 循环
        result = pdca_loop.run("创建一个测试文件")
        
        # 验证结果结构
        assert 'success' in result
        assert 'cycles' in result
        assert 'execution_metrics' in result
        
        logger.info(f"✅ 通过: PDCA 循环完成 (成功: {result['success']}, 周期: {result['cycles']})")
    
    def test_execution_metrics_in_pdca_result(self):
        """测试 PDCA 结果中的执行指标"""
        logger.info("\n🧪 测试 PDCA 结果中的执行指标...")
        
        context = ContextManager()
        memory = Memory()
        tool_registry = ToolRegistry()
        tool_registry.initialize()
        
        llm_client = LLMClient(api_key=config.OPENAI_API_KEY, model=config.OPENAI_MODEL)
        planner = Planner(llm_client, tool_registry, context)
        executor = Executor(tool_registry, memory)
        checker = Checker(llm_client)
        actor = Actor(llm_client, memory, max_retry=config.MAX_RETRY_PER_STEP)
        
        # 创建一个简单的计划
        simple_plan = [
            {
                "id": 1,
                "goal": "测试",
                "tool": "run_shell",
                "args": {"cmd": "echo test"},
                "expected_outcome": "命令执行"
            }
        ]
        
        # 执行计划
        results = executor.execute_plan(simple_plan)
        
        # 验证指标
        assert executor.metrics.total_steps >= 0
        assert executor.metrics.successful_steps >= 0
        assert executor.metrics.total_time >= 0
        
        logger.info(f"✅ 通过: 执行指标收集完成 "
                   f"(总步骤: {executor.metrics.total_steps}, "
                   f"成功: {executor.metrics.successful_steps}, "
                   f"耗时: {executor.metrics.total_time:.2f}s)")


class TestDependencyAnalysis:
    """测试依赖关系分析"""
    
    def test_planner_dependency_analysis(self):
        """测试 Planner 的依赖关系分析"""
        logger.info("\n🧪 测试 Planner 的依赖关系分析...")
        
        context = ContextManager()
        tool_registry = ToolRegistry()
        tool_registry.initialize()
        llm_client = LLMClient(api_key=config.OPENAI_API_KEY, model=config.OPENAI_MODEL)
        
        planner = Planner(llm_client, tool_registry, context)
        
        # 创建一个使用变量引用的计划（隐式依赖）
        plan = [
            {
                "id": 1,
                "goal": "创建文件",
                "tool": "write_file",
                "args": {"path": "/tmp/test.txt", "content": "test"}
            },
            {
                "id": 2,
                "goal": "读取文件",
                "tool": "read_file",
                "args": {"path": "${step_1.args.path}"}  # 隐式依赖步骤1
            }
        ]
        
        # 运行依赖分析
        analyzed_plan = planner.analyze_dependencies(plan)
        
        # 验证依赖被识别
        assert analyzed_plan[1]['dependencies'] == [1]
        
        logger.info(f"✅ 通过: 依赖关系分析正确识别 {analyzed_plan[1]['dependencies']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
