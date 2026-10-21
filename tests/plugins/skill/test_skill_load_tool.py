"""skill_load 工具测试：按需加载正文、source_path 返回（修复旧 SkillTool 缺陷）与大体积保护（issue #62）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.plugins.skill import MAX_BODY_CHARS, Skill, SkillCatalog, skill_load_tool


def envelope(result: str) -> dict[str, Any]:
    data = json.loads(result)
    assert isinstance(data, dict)
    return data


def make_catalog(body: str = "完整指令正文") -> SkillCatalog:
    skill = Skill(
        name="demo",
        description="演示 skill",
        location=Path("/skills/demo/SKILL.md"),
        source_path=Path("/skills/demo"),
        body=body,
    )
    return SkillCatalog((skill,))


class TestSkillLoadResult:
    async def test_load_result_contains_source_path_to_support_file_references(self) -> None:
        """source_path 随加载结果返回（旧 SkillTool 只回 name/body，无法引用 skill 附带文件）。"""
        data = envelope(await skill_load_tool(make_catalog()).run(name="demo"))

        assert data["status"] == "ok"
        assert data["name"] == "demo"
        assert data["description"] == "演示 skill"
        assert data["source_path"] == "/skills/demo"
        assert data["body"] == "完整指令正文"
        assert data["truncated"] is False

    async def test_unknown_skill_returns_error_envelope(self) -> None:
        data = envelope(await skill_load_tool(make_catalog()).run(name="missing"))

        assert data["status"] == "error"
        assert data["code"] == "UNKNOWN_SKILL"

    def test_parameters_are_native_json_schema(self) -> None:
        spec = skill_load_tool(make_catalog())

        assert spec.name == "skill_load"
        assert spec.parameters["type"] == "object"
        assert set(spec.parameters["properties"]) == {"name"}
        assert spec.parameters["required"] == ["name"]


class TestBodyLengthProtection:
    async def test_oversized_body_is_truncated_and_flagged(self) -> None:
        oversized = "x" * (MAX_BODY_CHARS + 100)

        data = envelope(await skill_load_tool(make_catalog(body=oversized)).run(name="demo"))

        assert data["status"] == "ok"
        assert len(data["body"]) == MAX_BODY_CHARS
        assert data["body_length"] == len(oversized)
        assert data["truncated"] is True

    async def test_body_at_limit_is_not_truncated(self) -> None:
        at_limit = "x" * MAX_BODY_CHARS

        data = envelope(await skill_load_tool(make_catalog(body=at_limit)).run(name="demo"))

        assert data["body"] == at_limit
        assert data["body_length"] == MAX_BODY_CHARS
        assert data["truncated"] is False
