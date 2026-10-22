"""skill prompt 注入 hook：prepareRequest 时把 `<available_skills>` 元数据 section 注入请求（issue #62）。"""

from __future__ import annotations

from src.core.turn_hooks import RequestContext
from src.plugins.skill.catalog import SkillCatalog
from src.plugins.skill.section import render_available_skills


class SkillPromptInjector:
    """prepareRequest 挂载回调：只注入元数据 section，正文由模型经 skill_load 按需加载（pi §3.5）。

    section 是 catalog 的纯函数渲染：每次请求注入同一份字节（稳定 section，不随 skill 加载变化）；
    注入只作用于本次请求视图，不写回引擎记录。
    """

    def __init__(self, catalog: SkillCatalog) -> None:
        self._catalog = catalog

    async def __call__(self, request: RequestContext) -> None:
        skills = self._catalog.skills()
        if not skills:
            return
        index = 0
        for message in request.messages:
            if message.get("role") != "system":
                break
            index += 1
        request.messages.insert(index, {"role": "system", "content": render_available_skills(skills)})
