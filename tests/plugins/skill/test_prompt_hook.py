"""skill prompt 注入 hook 测试：元数据 section 进请求、正文不注入、注入字节级稳定（issue #62、pi §3.5）。"""

from __future__ import annotations

from pathlib import Path

from src.core.turn_hooks import RequestContext
from src.plugins.skill import Skill, SkillCatalog, SkillPromptInjector, render_available_skills

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


def make_request() -> RequestContext:
    return RequestContext(turn=1, model="fake/model", messages=[{"role": "user", "content": "task"}], tools=[])


class TestSectionInjection:
    async def test_injects_metadata_section_as_leading_system_message(self) -> None:
        injector = SkillPromptInjector(make_catalog())
        request = make_request()

        await injector(request)

        assert request.messages[0]["role"] == "system"
        assert request.messages[0]["content"] == render_available_skills(make_catalog().skills())
        assert request.messages[1] == {"role": "user", "content": "task"}

    async def test_body_is_not_injected_into_request(self) -> None:
        """正文按需加载：注入的只有 name/description/location，skill 正文不进 prompt。"""
        injector = SkillPromptInjector(make_catalog())
        request = make_request()

        await injector(request)

        contents = [str(message.get("content")) for message in request.messages]
        assert all(BODY_MARKER not in content for content in contents)

    async def test_injection_is_byte_stable_across_requests(self) -> None:
        """稳定 section：每次请求注入同一份字节（不随会话进展漂移，prefix cache 友好）。"""
        injector = SkillPromptInjector(make_catalog())
        first, second = make_request(), make_request()

        await injector(first)
        await injector(second)

        assert first.messages[0]["content"] == second.messages[0]["content"]

    async def test_empty_catalog_injects_nothing(self) -> None:
        injector = SkillPromptInjector(SkillCatalog(()))
        request = make_request()

        await injector(request)

        assert request.messages == [{"role": "user", "content": "task"}]
