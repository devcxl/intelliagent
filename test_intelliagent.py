#!/usr/bin/env python3
"""
IntelliAgent 系统测试
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from core.llm_client import LLMClient
from core.planner import Planner
from core.executor import Executor
from core.checker import Checker
from core.actor import Actor
from core.memory import Memory
from core.context import ContextManager


class TestLLMClient:
    """测试 LLM 客户端"""

    @patch('core.llm_client.OpenAI')
    def test_chat(self, mock_openai):
        """测试基础聊天功能"""
        # Mock OpenAI 响应
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="测试响应"))]
        mock_response.usage.total_tokens = 100
        
        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        client = LLMClient(api_key="test-key")
        result = client.chat([{"role": "user", "content": "测试"}])
        
        assert result == "测试响应"

    @patch('core.llm_client.OpenAI')
    def test_generate_plan(self, mock_openai):
        """测试计划生成"""
        plan_json = json.dumps({
            "plan": [
                {"id": 1, "goal": "测试", "tool": "run_shell", "args": {}}
            ]
        })
        
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content=plan_json))]
        mock_response.usage.total_tokens = 150
        
        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        client = LLMClient(api_key="test-key")
        plan = client.generate_plan("测试任务", ["run_shell"])
        
        assert len(plan) == 1
        assert plan[0]["goal"] == "测试"


class TestMemory:
    """测试记忆管理器"""

    def test_add_observation(self):
        """测试添加观察"""
        memory = Memory(experience_file="test_exp.json")
        memory.add_observation({"test": "data"})
        
        assert len(memory.observations) == 1
        assert memory.observations[0]["test"] == "data"

    def test_get_recent_context(self):
        """测试获取最近上下文"""
        memory = Memory(experience_file="test_exp.json")
        for i in range(10):
            memory.add_observation(f"obs_{i}")
        
        context = memory.get_recent_context(n=3)
        assert "obs_9" in context
        assert "obs_7" in context

    def test_save_experience(self, tmp_path):
        """测试保存经验"""
        exp_file = tmp_path / "test_exp.json"
        memory = Memory(experience_file=str(exp_file))
        
        experience = {
            "task": "测试任务",
            "plan": [],
            "execution_results": [],
            "check_results": [],
            "final_status": "success",
            "total_steps": 1,
            "passed_steps": 1,
            "average_score": 1.0
        }
        
        memory.save_experience(experience)
        
        # 验证文件已创建
        assert exp_file.exists()
        
        # 验证内容
        with open(exp_file, 'r') as f:
            saved_data = json.load(f)
            assert len(saved_data) == 1
            assert saved_data[0]["task"] == "测试任务"


class TestPlanner:
    """测试规划器"""

    def test_get_available_tools(self):
        """测试获取可用工具"""
        mock_llm = Mock()
        mock_tools = Mock()
        mock_tools._initialized = True
        mock_tools._mcp_registry._initialized = True
        mock_tools._mcp_registry._available_tools = {
            "tool1": Mock(),
            "tool2": Mock()
        }
        mock_context = Mock()

        planner = Planner(mock_llm, mock_tools, mock_context)
        tools = planner.get_available_tools()
        
        assert "tool1" in tools
        assert "tool2" in tools


class TestExecutor:
    """测试执行器"""

    def test_execute_step_success(self):
        """测试成功执行步骤"""
        mock_tools = Mock()
        mock_tools._initialized = True
        mock_tools._mcp_registry._initialized = True
        mock_tool = Mock(return_value={"status": "ok"})
        mock_tools.get_tool.return_value = mock_tool
        
        memory = Memory(experience_file="test_exp.json")
        executor = Executor(mock_tools, memory)
        
        step = {
            "id": 1,
            "goal": "测试",
            "tool": "test_tool",
            "args": {"param": "value"}
        }
        
        result = executor._execute_step(step)
        
        assert result["status"] == "success"
        assert "result" in result

    def test_execute_step_no_tool(self):
        """测试无工具的步骤"""
        mock_tools = Mock()
        memory = Memory(experience_file="test_exp.json")
        executor = Executor(mock_tools, memory)
        
        step = {
            "id": 1,
            "goal": "测试",
            "tool": "none",
            "args": {}
        }
        
        result = executor._execute_step(step)
        
        assert result["status"] == "skipped"


class TestChecker:
    """测试检查器"""

    def test_check_step_result_success(self):
        """测试检查成功的步骤"""
        mock_llm = Mock()
        mock_llm.check_result.return_value = {
            "passed": True,
            "score": 0.95,
            "feedback": "成功",
            "suggestion": ""
        }
        
        checker = Checker(mock_llm)
        
        step = {
            "id": 1,
            "goal": "测试",
            "expected_outcome": "成功"
        }
        
        exec_result = {
            "status": "success",
            "result": {"output": "完成"}
        }
        
        check_result = checker.check_step_result(step, exec_result)
        
        assert check_result["passed"] is True
        assert check_result["score"] == 0.95

    def test_check_step_result_failed(self):
        """测试检查失败的步骤"""
        mock_llm = Mock()
        checker = Checker(mock_llm)
        
        step = {"id": 1, "goal": "测试"}
        exec_result = {"status": "failed", "error": "错误"}
        
        check_result = checker.check_step_result(step, exec_result)
        
        assert check_result["passed"] is False
        assert check_result["needs_retry"] is True


class TestActor:
    """测试改进器"""

    def test_decide_action_success(self):
        """测试成功的决策"""
        mock_llm = Mock()
        memory = Memory(experience_file="test_exp.json")
        actor = Actor(mock_llm, memory)
        
        step = {"id": 1}
        exec_result = {"status": "success"}
        check_result = {"passed": True, "score": 1.0}
        
        action = actor.decide_action(step, exec_result, check_result)
        
        assert action["action"] == "continue"

    def test_decide_action_retry(self):
        """测试重试决策"""
        mock_llm = Mock()
        memory = Memory(experience_file="test_exp.json")
        actor = Actor(mock_llm, memory, max_retry=3)
        
        step = {"id": 1}
        exec_result = {"status": "failed"}
        check_result = {"passed": False, "needs_retry": True}
        
        action = actor.decide_action(step, exec_result, check_result)
        
        assert action["action"] == "retry"

    def test_decide_action_adjust_plan(self):
        """测试调整计划决策"""
        mock_llm = Mock()
        memory = Memory(experience_file="test_exp.json")
        actor = Actor(mock_llm, memory, max_retry=2)
        
        step = {"id": 1}
        exec_result = {"status": "failed"}
        check_result = {"passed": False, "needs_retry": True}
        
        # 模拟已经重试了最大次数
        actor.retry_counts[1] = 2
        
        action = actor.decide_action(step, exec_result, check_result)
        
        assert action["action"] == "adjust_plan"


class TestContext:
    """测试上下文管理器"""

    def test_add_and_get_context(self):
        """测试添加和获取上下文"""
        context = ContextManager()
        context.add_context("消息1")
        context.add_context("消息2")
        
        result = context.get_context()
        assert "消息1" in result
        assert "消息2" in result

    def test_clear_context(self):
        """测试清空上下文"""
        context = ContextManager()
        context.add_context("消息1")
        context.clear_context()
        
        assert len(context.history) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
