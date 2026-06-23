"""SkillsConfig 和 PermissionEngine 集成测试。"""

from pathlib import Path

from src.config.unified_config import SkillsConfig, UnifiedConfig
from src.core.permission_engine import PermissionEngine


# ============================================================================
# SkillsConfig
# ============================================================================


def test_skills_config_defaults():
    """SkillsConfig 默认值正确。"""
    sc = SkillsConfig()
    assert sc.enabled is True
    assert sc.project_paths == [".agents/skills"]
    assert sc.user_paths == ["~/.config/opencode/skills"]


def test_skills_config_custom():
    """SkillsConfig 可自定义路径。"""
    sc = SkillsConfig(
        enabled=False,
        project_paths=["custom/path"],
        user_paths=["other/path"],
    )
    assert sc.enabled is False
    assert sc.project_paths == ["custom/path"]


def test_unified_config_has_skills():
    """UnifiedConfig 包含 skills 字段。"""
    uc = UnifiedConfig()
    assert hasattr(uc, "skills")
    assert uc.skills.enabled is True


def test_unified_config_load_with_skills(tmp_path):
    """从 JSON 加载时 skills 配置被正确解析。"""
    cfg_file = tmp_path / "test-config.json"
    cfg_file.write_text(
        '{"skills": {"enabled": false, "project_paths": ["custom/path"]}}'
    )
    uc = UnifiedConfig.load(cfg_file)
    assert uc.skills.enabled is False
    assert uc.skills.project_paths == ["custom/path"]


# ============================================================================
# PermissionEngine — skill 默认权限
# ============================================================================


def test_skill_default_permission_is_allow():
    """skill 工具默认权限为 allow。"""
    engine = PermissionEngine(
        rules=[],
        workspace=Path("/tmp"),
    )
    d = engine.check("skill", {"name": "any-skill"})
    assert d.action.value == "allow"
