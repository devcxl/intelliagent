"""skill 插件契约集成测试：经 PluginHost 注册 tool+hook 能力（ADR 0007），引擎运行中按需加载正文（issue #62）。"""

from __future__ import annotations

import json
from pathlib import Path

from src.core.engine import Engine
from src.core.plugin_host import CapabilityKind, PluginHost
from src.core.turn_hooks import PrepareRequestHook
from src.plugins.basic_tools import ToolSpec
from src.plugins.skill import Skill, SkillCatalog, SkillPlugin, render_available_skills
from tests.core.engine_support import FakeLLM, text_events, tool_call_events

BODY_MARKER = "BODY-MARKER-MUST-NOT-APPEAR"


def make_catalog() -> SkillCatalog:
    skill = Skill(
        name="demo",
        description="演示 skill",
        location=Path("/skills/demo/SKILL.md"),
        source_path=Path("/skills/demo"),
        body=BODY_MARKER,
    )
    return SkillCatalog((skill,))


class TestSkillPluginContract:
    def test_manifest_matches_registered_capabilities(self) -> None:
        plugin = SkillPlugin(make_catalog())

        declared = {(item.kind, item.name) for item in plugin.manifest.capabilities}

        assert declared == {(CapabilityKind.TOOL, "skill_load"), (CapabilityKind.HOOK, "available_skills")}
        assert plugin.manifest.name == "skill"
        assert plugin.manifest.api_version == 1

    def test_plugin_registers_tool_and_hook_via_plugin_host(self) -> None:
        host = PluginHost()

        host.load(SkillPlugin(make_catalog()))

        tool = host.get_capability(CapabilityKind.TOOL, "skill_load")
        assert isinstance(tool, ToolSpec)
        hook = host.get_capability(CapabilityKind.HOOK, "available_skills")
        assert isinstance(hook, PrepareRequestHook)


class TestEngineIntegration:
    async def test_body_loads_on_demand_and_section_stays_stable(self) -> None:
        """引擎全程：section 注入每次请求且字节一致；正文只经 skill_load 结果进入上下文，不整段塞 prompt。"""
        host = PluginHost()
        host.load(SkillPlugin(make_catalog()))
        llm = FakeLLM()
        llm.enqueue(*tool_call_events([("c1", "skill_load", json.dumps({"name": "demo"}))]))
        llm.enqueue(*text_events("done"))
        engine = Engine.from_host(host, llm=llm, model="fake/model")

        await engine.run("task")

        sections = [str(request.messages[0].get("content")) for request in llm.requests]
        assert sections == [render_available_skills(make_catalog().skills())] * 2
        first_request_text = "\n".join(str(message.get("content")) for message in llm.requests[0].messages)
        assert BODY_MARKER not in first_request_text
        tool_results = [message for message in engine.messages if message.get("role") == "tool"]
        assert len(tool_results) == 1
        data = json.loads(str(tool_results[0]["content"]))
        assert data["source_path"] == "/skills/demo"
        assert data["body"] == BODY_MARKER

    async def test_engine_sees_skill_load_schema_from_host(self) -> None:
        host = PluginHost()
        host.load(SkillPlugin(make_catalog()))
        llm = FakeLLM()
        llm.enqueue(*text_events("done"))
        engine = Engine.from_host(host, llm=llm, model="fake/model")

        await engine.run("task")

        tool_names = [schema["function"]["name"] for schema in llm.requests[0].tools or []]
        assert tool_names == ["skill_load"]
