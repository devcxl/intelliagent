"""skill 内置插件（issue #62）：元数据进 prompt 稳定 section，正文按需加载，source_path 支持引用文件。"""

from src.plugins.skill.catalog import SkillCatalog
from src.plugins.skill.loader import load_skills
from src.plugins.skill.model import Skill
from src.plugins.skill.plugin import SkillPlugin
from src.plugins.skill.prompt import SkillPromptInjector
from src.plugins.skill.section import render_available_skills
from src.plugins.skill.tool import MAX_BODY_CHARS, skill_load_tool

__all__ = [
    "MAX_BODY_CHARS",
    "Skill",
    "SkillCatalog",
    "SkillPlugin",
    "SkillPromptInjector",
    "load_skills",
    "render_available_skills",
    "skill_load_tool",
]
