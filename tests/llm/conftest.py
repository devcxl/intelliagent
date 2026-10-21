"""测试夹具：录制型传输与 fake/real 双路径后端装配。"""

from __future__ import annotations

import os
from collections.abc import Iterator

import litellm
import pytest

from src.llm.litellm_client import LiteLLMClient
from tests.llm.backends import Backend, FakeBackend, RealBackend
from tests.llm.recorded import Recorder

litellm.suppress_debug_info = True


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    """安装录制型传输，替换 litellm.completion 入口。"""
    rec = Recorder()
    monkeypatch.setattr(litellm, "completion", rec.completion)
    return rec


@pytest.fixture
def client(recorder: Recorder) -> LiteLLMClient:
    """录制传输上的客户端；退避只记录不等待。"""
    return LiteLLMClient(sleep=recorder.sleep)


@pytest.fixture(params=["fake", "real"])
def backend(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Iterator[Backend]:
    """双路径后端：fake（录制传输）与 real（真实 litellm，skip-if-no-key）。"""
    if request.param == "fake":
        rec = Recorder()
        monkeypatch.setattr(litellm, "completion", rec.completion)
        yield FakeBackend(recorder=rec, client=LiteLLMClient(sleep=rec.sleep))
    else:
        if not os.environ.get("OPENAI_API_KEY"):
            pytest.skip("需要 OPENAI_API_KEY 环境变量（真实 litellm 路径）")
        yield RealBackend(client=LiteLLMClient())
