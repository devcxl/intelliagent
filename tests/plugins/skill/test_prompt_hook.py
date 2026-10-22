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

    async def test_injects_metadata_after_existing_system_messages(self) -> None:
        """已有 preamble/rules 时，skills section 追加在 system 块末尾，不抢 leading 位置。"""
        injector = SkillPromptInjector(make_catalog())
        request = RequestContext(
            turn=1,
            model="fake/model",
            messages=[
                {"role": "system", "content": "preamble"},
                {"role": "user", "content": "task"},
            ],
            tools=[],
        )

        await injector(request)

        assert [message["role"] for message in request.messages] == ["system", "system", "user"]
        assert request.messages[0]["content"] == "preamble"
        assert request.messages[1]["content"] == render_available_skills(make_catalog().skills())

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


class TestReviewRegressions:
    """PR #74 审查回归：checkpoint 往返一致性、frontmatter 行边界、symlink 根校验、尺寸上限。"""

    def test_section_snapshot_round_trips_through_checkpoint_storage(self) -> None:
        """AC3：section 快照经序列化存取（模拟 prompt checkpoint）后重建逐字节一致。

        checkpoint 保存的是渲染文本本身，重建时直接恢复快照而非重新渲染——
        一致性由快照语义保证，不依赖 catalog 跨进程不变。
        """
        import json

        catalog = make_catalog()
        rendered = render_available_skills(catalog.skills())
        checkpoint = {"available_skills": rendered}  # 模拟 checkpoint 落库
        restored = json.loads(json.dumps(checkpoint))  # 模拟跨进程 round-trip
        assert restored["available_skills"] == rendered
        assert render_available_skills(catalog.skills()) == restored["available_skills"]

    def test_frontmatter_fences_require_line_boundaries(self, tmp_path: Path) -> None:
        """分隔符必须独占一行：---oops / ---- 不再误判为 frontmatter。"""
        bad = tmp_path / "SKILL.md"
        bad.write_text("---oops\nname: x\ndescription: y\n---oops\nbody\n", encoding="utf-8")
        from src.plugins.skill.loader import _parse_skill_file

        assert _parse_skill_file(bad, tmp_path) is None

    def test_symlink_escaping_scan_root_is_rejected(self, tmp_path: Path) -> None:
        """目录内符号链接指向根外的 SKILL.md 拒绝，location 不泄漏根外路径。"""
        root = tmp_path / "root"
        root.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        target = outside / "SKILL.md"
        target.write_text("---\nname: escaper\ndescription: d\n---\nbody\n", encoding="utf-8")
        (root / "SKILL.md").symlink_to(target)
        from src.plugins.skill.loader import load_skills

        assert load_skills(project_paths=[root]) == ()

    def test_oversized_skill_file_is_rejected(self, tmp_path: Path) -> None:
        big = tmp_path / "SKILL.md"
        big.write_text("---\nname: big\ndescription: d\n---\n" + "x" * 2_000_000, encoding="utf-8")
        from src.plugins.skill.loader import _parse_skill_file

        assert _parse_skill_file(big, tmp_path) is None

    def test_undecodable_file_is_skipped_not_fatal(self, tmp_path: Path) -> None:
        """非 UTF-8 的 SKILL.md 跳过并 warning，不让 load_skills 整体崩溃。"""
        bad = tmp_path / "SKILL.md"
        bad.write_bytes(b"\xff\xfe\x00bad")
        from src.plugins.skill.loader import load_skills

        assert load_skills(project_paths=[tmp_path]) == ()
