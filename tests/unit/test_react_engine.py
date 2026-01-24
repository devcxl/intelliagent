#!/usr/bin/env python3
"""
ReAct 循环引擎单元测试
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from src.agent.react_engine import ReactEngine


@pytest.fixture
def mock_engine():
    """创建 Mock ReactEngine 实例"""
    llm = Mock()
    tools = Mock()
    memory = Mock()
    context = Mock()
    
    engine = ReactEngine(
        llm_client=llm,
        tools=tools,
        memory=memory,
        context=context,
        max_iterations=10
    )
    
    # 确保 Mock 工具正确设置
    engine.tools.get_tool.return_value = lambda **kwargs: {'status': 'ok', 'result': 'test result'}
    
    return engine


class TestReactEngineBasicRun:
    """测试 ReactEngine 基本运行流程"""
    
    def test_react_engine_immediate_completion(self, mock_engine):
        """测试 LLM 返回完成信号的情况"""
        mock_engine.llm_client.generate_react_thought.return_value = {
            'reasoning': '任务已完成',
            'is_complete': True,
            'answer': '测试答案'
        }
        
        result = mock_engine.run('测试任务')
        
        assert result['success'] == True
        assert result['iterations'] == 1
        assert result['answer'] == '测试答案'
        assert mock_engine.llm_client.generate_react_thought.call_count == 1
    
    def test_react_engine_max_iterations_reached(self, mock_engine):
        """测试达到最大迭代次数的情况"""
        mock_engine.llm_client.generate_react_thought.return_value = {
            'reasoning': '需要继续',
            'is_complete': False,
            'action': {'tool': 'read_file', 'args': {'path': 'test.txt'}}
        }
        mock_engine.tools.get_tool.return_value = {'status': 'ok', 'result': 'test content'}
        
        result = mock_engine.run('测试任务')
        
        assert result['success'] == False
        assert result['iterations'] == 10
        assert '达到最大迭代次数' in result['summary']
        assert mock_engine.llm_client.generate_react_thought.call_count == 10
    
    def test_react_engine_tool_call_failure(self, mock_engine):
        """测试工具调用失败的处理"""
        mock_engine.llm_client.generate_react_thought.return_value = {
            'reasoning': '需要读取文件',
            'is_complete': False,
            'action': {'tool': 'read_file', 'args': {'path': 'test.txt'}}
        }
        mock_engine.tools.get_tool.side_effect = Exception('工具执行失败')
        
        result = mock_engine.run('测试任务')
        
        assert result['success'] == False
        # ReactEngine 会继续重试直到达到最大迭代次数
        assert '达到最大迭代次数' in result['summary']
        assert mock_engine.memory.add_observation.call_count == 10  # 每次迭代都会记录


class TestReactEngineToolCalls:
    """测试 ReactEngine 工具调用"""
    
    def test_react_engine_single_tool_call(self, mock_engine):
        """测试单次工具调用"""
        mock_engine.llm_client.generate_react_thought.side_effect = [
            {
                'reasoning': '需要写入文件',
                'is_complete': False,
                'action': {'tool': 'write_file', 'args': {'path': 'test.txt', 'content': 'hello'}}
            },
            {
                'reasoning': '任务完成',
                'is_complete': True,
                'answer': '文件已创建'
            }
        ]
        
        mock_engine.tools.get_tool.return_value = {'status': 'ok', 'message': '文件已创建'}
        
        result = mock_engine.run('测试任务')
        
        assert result['success'] == True
        assert result['answer'] == '文件已创建'
        assert mock_engine.memory.add_observation.call_count == 1
        assert mock_engine.memory.clear_memory.call_count == 1
    
    def test_react_engine_multiple_iterations(self, mock_engine):
        """测试多次迭代的场景"""
        call_count = 0
        
        def generate_thought_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            
            if call_count < 5:
                return {
                    'reasoning': f'思考步骤 {call_count}',
                    'is_complete': False,
                    'action': {'tool': 'read_file', 'args': {'path': f'file_{call_count}.txt'}}
                }
            else:
                return {
                    'reasoning': '任务完成',
                    'is_complete': True,
                    'answer': '所有文件已处理'
                }
        
        mock_engine.llm_client.generate_react_thought.side_effect = generate_thought_side_effect
        
        results = []
        for i in range(5):
            result = {'status': 'ok', 'result': f'content_{i}'}
            results.append(result)
        mock_engine.tools.get_tool.return_value = results.pop(0) if results else None
        
        result = mock_engine.run('测试任务')
        
        assert result['success'] == True
        assert result['iterations'] == 5
        assert result['answer'] == '所有文件已处理'


class TestReactEngineContext:
    """测试 ReactEngine 上下文管理"""
    
    def test_react_engine_clears_memory(self, mock_engine):
        """测试运行前清空记忆"""
        mock_engine.llm_client.generate_react_thought.return_value = {
            'reasoning': '测试',
            'is_complete': True,
            'answer': '完成'
        }
        
        result = mock_engine.run('测试任务')
        
        assert mock_engine.memory.clear_memory.call_count == 1
        assert result['success'] == True
    
    def test_react_engine_adds_task_to_context(self, mock_engine):
        """测试任务添加到上下文"""
        mock_engine.llm_client.generate_react_thought.return_value = {
            'reasoning': '测试',
            'is_complete': True,
            'answer': '完成'
        }
        
        mock_engine.run('测试任务')
        
        mock_engine.context.add_context.assert_called_once_with(
            '用户任务: 测试任务'
        )
