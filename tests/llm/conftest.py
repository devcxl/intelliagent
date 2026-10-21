"""测试夹具：录制型传输与 fake/real 双路径后端装配。"""

from __future__ import annotations

import os
from collections.abc import Iterator

import litellm
import pytest

from src.llm.client import ProviderClient
from src.llm.protocols.litellm_adapter import LitellmAdapter
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
def client(recorder: Recorder) -> ProviderClient:
    """录制传输上的客户端；退避只记录不等待。"""
    return ProviderClient(LitellmAdapter(), sleep=recorder.sleep)


@pytest.fixture(params=["fake", "real"])
def backend(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Iterator[Backend]:
    """双路径后端：fake（录制传输）与 real（真实 litellm）。

    real 路径是显式 opt-in（integration marker + OPENAI_API_KEY），默认测试集不触网
    （CONTRIBUTING：避免真实 LLM/网络调用；PR #68 审查 Standards 轴 high）。
    """
    if request.param == "fake":
        rec = Recorder()
        monkeypatch.setattr(litellm, "completion", rec.completion)
        yield FakeBackend(recorder=rec, client=ProviderClient(LitellmAdapter(), sleep=rec.sleep))
    else:
        if not request.node.get_closest_marker("integration"):
            pytest.skip("真实路径需显式 opt-in：pytest -m integration（避免默认触网）")
        if not os.environ.get("OPENAI_API_KEY"):
            pytest.skip("需要 OPENAI_API_KEY 环境变量（真实 litellm 路径）")
        yield RealBackend(client=ProviderClient(LitellmAdapter()))
