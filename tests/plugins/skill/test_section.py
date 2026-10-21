"""`<available_skills>` prompt section 纯函数测试：只含元数据、字节级稳定、可快照重建（issue #62、pi §3.5）。"""

from __future__ import annotations

from pathlib import Path

from src.plugins.skill import Skill, render_available_skills


def make_skill(name: str, description: str, body: str = "DO-NOT-INJECT-BODY") -> Skill:
    """构造不依赖文件系统的 Skill（section 渲染只看元数据）。"""
    return Skill(
        name=name,
        description=description,
        location=Path(f"/skills/{name}/SKILL.md"),
        source_path=Path(f"/skills/{name}"),
        body=body,
    )


class TestSectionContent:
    def test_section_contains_name_description_location_only(self) -> None:
        skill = make_skill("alpha", "第一个 skill", body="BODY-MARKER-MUST-NOT-APPEAR")

        section = render_available_skills((skill,))

        assert section.startswith("<available_skills>")
        assert section.endswith("</available_skills>")
        assert "<name>alpha</name>" in section
        assert "<description>第一个 skill</description>" in section
        assert "<location>/skills/alpha/SKILL.md</location>" in section
        # 正文不进 section——按需加载，不全量塞入 prompt
        assert "BODY-MARKER-MUST-NOT-APPEAR" not in section

    def test_xml_special_characters_are_escaped(self) -> None:
        skill = make_skill("alpha", "a < b & c > d")

        section = render_available_skills((skill,))

        assert "<description>a &lt; b &amp; c &gt; d</description>" in section

    def test_empty_catalog_renders_deterministic_wrapper(self) -> None:
        assert render_available_skills(()) == "<available_skills>\n</available_skills>"


class TestSectionStability:
    def test_generation_is_pure_and_snapshot_rebuildable(self) -> None:
        """同输入同输出（字节级稳定）：压缩的 prompt checkpoint 重建 section 快照一致。"""
        skills = (make_skill("alpha", "第一个"), make_skill("beta", "第二个"))
        expected = (
            "<available_skills>\n"
            "  <skill>\n"
            "    <name>alpha</name>\n"
            "    <description>第一个</description>\n"
            "    <location>/skills/alpha/SKILL.md</location>\n"
            "  </skill>\n"
            "  <skill>\n"
            "    <name>beta</name>\n"
            "    <description>第二个</description>\n"
            "    <location>/skills/beta/SKILL.md</location>\n"
            "  </skill>\n"
            "</available_skills>"
        )

        assert render_available_skills(skills) == expected
        assert render_available_skills(skills) == expected

    def test_output_is_independent_of_input_order(self) -> None:
        first = make_skill("alpha", "第一个")
        second = make_skill("beta", "第二个")

        assert render_available_skills((first, second)) == render_available_skills((second, first))
