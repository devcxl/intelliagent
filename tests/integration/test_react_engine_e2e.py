#!/usr/bin/env python3
"""
ReactEngine 端到端测试 — 使用真实 LLM（需要 OPENAI_API_KEY）。

运行方式：
    pytest tests/integration/test_react_engine_e2e.py -v -s

跳过条件：未设置 OPENAI_API_KEY 环境变量时自动 skip。
"""

import os

import pytest

from src.core.react_engine import ReactEngine
from src.llm.llm_client import LLMClient
from src.tools.registry import _default_registry, register_agent_team_tools


@pytest.fixture(scope="module")
def llm_client():
    # E2E 测试只接受真实环境变量，避免 intelliagent.json 中其他 provider 配置误触发真实调用。
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("需要 OPENAI_API_KEY 环境变量")
    return LLMClient(
        api_key=api_key,
        base_url=os.environ.get("OPENAI_API_BASE"),
        model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
    )


@pytest.fixture(scope="module")
def engine(llm_client):
    # 直接构造 ReactEngine 时必须显式接入工具注册表，保持 core 层无默认工具副作用。
    register_agent_team_tools()
    return ReactEngine(llm_client=llm_client, tools_registry=_default_registry)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_simple_calculation(engine):
    """简单计算：模型直接回复，不调用工具。"""
    result = await engine.run("计算 1+2+3 的和，直接告诉我答案，不要调用任何工具")

    assert result["success"] is True
    assert "6" in result["answer"]
    assert result["num_turns"] >= 1
    assert result["total_tokens"] > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tool_call_read_file(engine):
    """单次工具调用：读取文件。"""
    result = await engine.run(
        "读取文件 pyproject.toml 的内容，告诉我这个项目叫什么名字。注意：文件路径是 pyproject.toml，在当前工作目录下。"
    )

    assert result["success"] is True
    assert result["num_turns"] >= 2
    assert result["total_tokens"] > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tool_call_write_and_read(engine):
    """多步工具调用：写入文件 → 读取验证。"""
    result = await engine.run(
        "1. 用 write_file 创建一个文件 /tmp/intelliagent_e2e_test.txt，内容是 'hello from e2e test'\n"
        "2. 用 read_file 读取这个文件验证内容正确\n"
        "3. 告诉我验证结果"
    )

    assert result["success"] is True
    assert result["num_turns"] >= 3
    assert result["total_tokens"] > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tool_call_shell(engine):
    """Shell 工具调用。"""
    result = await engine.run("用 run_shell 执行命令 'echo hello world'，把输出结果告诉我")

    assert result["success"] is True
    assert "hello world" in result["answer"].lower()
    assert result["num_turns"] >= 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_task_write_and_plan(engine):
    """task_write 工具：任务规划。"""
    result = await engine.run(
        "用 task_write 工具列出以下任务的步骤，然后告诉我计划是什么：\n"
        "任务：创建一个 Python 脚本来计算斐波那契数列前 10 项\n"
        "只需要列出计划，不需要实际执行。"
    )

    assert result["success"] is True
    assert result["num_turns"] >= 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_safety_net_repeat_detection(engine):
    """安全网：连续重复调用检测。"""
    engine.max_consecutive_repeats = 3
    result = await engine.run(
        "反复用 read_file 读取同一个不存在的文件 /tmp/nonexistent_xyz_123.txt，每次都读取同一个文件，不要停。"
    )

    assert result["success"] is False
    assert "安全网触发" in result.get("summary", "")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_iter_steps_streaming(engine):
    """流式生成器：验证事件类型顺序。"""
    events = []
    async for event in engine.iter_steps(
        "计算 2+2 等于多少，直接告诉我答案，不要调用任何工具",
        max_tokens=10000,
        max_consecutive_repeats=5,
    ):
        events.append(event)

    types = [e["type"] for e in events]
    assert types[0] == "answer"
    assert types[-1] == "answer"
    assert "4" in events[-1]["data"]["answer"]
