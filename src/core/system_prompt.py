"""System prompt 构建：固定 preamble + rules + cwd + tools 的字节稳定 leading system message。

ADR 0010 的完整形态是“section 存储 + 增量 patch + transcript replay”；当前实现先落地
最小稳定前缀：所有 section 在启动时渲染成一条 system message，随 Conversation 持久化，
后续请求复用同一字节前缀（prefix caching 友好）。section 变更 patch 留待后续。
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

PREAMBLE = "You are IntelliAgent, a coding agent working in the user's workspace."
"""固定 preamble：不随任务或环境变化，保证请求前缀稳定。"""

RULES = (
    "- Inspect files before editing; use the provided tools instead of guessing.\n"
    "- Verify changes when possible and report failures honestly.\n"
    "- Never reveal secrets or credentials.\n"
    "- Keep changes scoped to the user's request."
)


def build_system_prompt(workspace: Path, tools: Iterable[str]) -> str:
    """渲染稳定的 system prompt。

    tools 只放名称（schema 仍由请求的 tools 字段承载），排序后输出，保证同一工具集
    得到逐字节相同的结果；cwd 取绝对路径。空工具集省略 tools section。
    """
    names = sorted(set(tools))
    sections = [
        PREAMBLE,
        f"<rules>\n{RULES}\n</rules>",
        f"<cwd>{workspace.resolve()}</cwd>",
    ]
    if names:
        sections.append("<tools>\n" + "\n".join(f"- {name}" for name in names) + "\n</tools>")
    return "\n\n".join(sections)
