#!/usr/bin/env python3
"""
Skill 集成 - 与 ReAct 引擎的集成

功能：
1. 将 Skill 描述提供给 LLM
2. 处理 LLM 的 Skill 调用请求
3. 执行 Skill 工作流
4. 记录执行历史和统计
"""

from typing import Dict, List, Optional, Any, Tuple, Union
from .skill_loader import SkillLoader
from .skill_system import Skill, SkillRegistry
from utils.logger import logger


class SkillExecutionHistory:
    """Skill 执行历史记录"""
    
    def __init__(self):
        """初始化历史记录"""
        self.history: List[Dict[str, Any]] = []
    
    def record(
        self,
        skill_id: str,
        skill_name: str,
        parameters: Dict[str, Any],
        result: Dict[str, Any]
    ) -> None:
        """
        记录一次执行
        
        Args:
            skill_id: Skill ID
            skill_name: Skill 名称
            parameters: 执行参数
            result: 执行结果
        """
        from datetime import datetime
        
        self.history.append({
            'timestamp': datetime.now().isoformat(),
            'skill_id': skill_id,
            'skill_name': skill_name,
            'parameters': parameters,
            'result': result,
            'success': result.get('success', False)
        })
    
    def get_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近的执行历史"""
        return self.history[-limit:]
    
    def get_stats(self) -> Dict[str, Any]:
        """获取执行统计"""
        if not self.history:
            return {
                'total_executions': 0,
                'successful': 0,
                'failed': 0,
                'success_rate': 0.0
            }
        
        successful = sum(1 for h in self.history if h['success'])
        total = len(self.history)
        
        return {
            'total_executions': total,
            'successful': successful,
            'failed': total - successful,
            'success_rate': successful / total if total > 0 else 0.0
        }
    
    def clear(self) -> None:
        """清除历史"""
        self.history.clear()


class SkillIntegration:
    """
    Skill 集成 - 与 ReAct 引擎的集成接口
    """
    
    def __init__(self, skills_dir: Optional[str] = None):
        """
        初始化 Skill 集成
        
        Args:
            skills_dir: Skills 目录路径，默认为 .claude/skills
        """
        from pathlib import Path
        
        skills_path = Path(skills_dir) if skills_dir else None
        self.loader = SkillLoader(skills_path)
        self.history = SkillExecutionHistory()
        self.executor = SkillExecutor(skills_path)
        self._loaded = False
    
    def initialize(self) -> None:
        """初始化 - 加载所有 Skills"""
        if not self._loaded:
            self.loader.load_all()
            self._loaded = True
            logger.info(f"✅ Skill 集成初始化完成 ({self.loader.registry.count()} 个 Skills)")

    def get_skill_count(self) -> int:
        """获取已加载的 Skill 数量"""
        self.initialize()
        return self.loader.registry.count()


    def get_full_skill_details(self) -> Dict[str, Any]:
        """返回完整的 Skill 详情（含 SKILL.md 内容和资源）"""
        self.initialize()
        skills = self.loader.list_all()
        return {
            "skills": [
                {
                    "id": skill.skill_id,
                    "name": skill.metadata.name,
                    "metadata": skill.metadata.to_dict(),
                    "skill_md": skill.resources.get("SKILL.md", ""),
                    "resources": skill.resources,
                }
                for skill in skills
            ]
        }
    
    def get_available_skills_for_llm(self) -> str:
        """
        获取 LLM 可用的 Skills 描述
        
        用于在 LLM 提示中提供 Skills 列表
        
        Returns:
            Markdown 格式的 Skills 描述
        """
        self.initialize()
        return self.loader.get_available_skills_description()

    def get_full_skills_for_llm(self) -> str:
        """获取所有 Skill 的完整定义（不推荐默认使用，可能过大）"""
        self.initialize()
        skills = self.loader.list_all()
        if not skills:
            return ""
        parts = []
        for skill in skills:
            parts.append(self.get_full_skill_content(skill.skill_id))
        return "\n\n".join(parts)

    def get_full_skill_content(self, skill_id: str) -> str:
        """获取指定 Skill 的完整 SKILL.md 及资源内容"""
        self.initialize()
        skill = self.loader.get(skill_id)
        if not skill:
            return ""
        parts = [f"## {skill.metadata.name} (ID: {skill.skill_id})"]
        skill_md = skill.resources.get("SKILL.md", "")
        if skill_md:
            parts.append(skill_md.strip())
        for res_name, res_content in skill.resources.items():
            if res_name == "SKILL.md":
                continue
            parts.append(f"### Resource: {res_name}\n{res_content.strip()}")
        return "\n\n".join(parts)
    
    def get_skill_descriptions_for_tools(self) -> List[Dict[str, Any]]:
        """
        获取所有 Skills 的工具描述（供 ReAct 使用）
        
        Returns:
            Skills 工具描述列表
        """
        self.initialize()
        
        tools = []
        for skill in self.loader.list_all():
            # 跳过禁止 LLM 调用的 Skills
            if skill.metadata.disable_model_invocation:
                continue
            
            tools.append({
                'type': 'skill',
                'name': skill.skill_id,
                'description': f"{skill.metadata.name}: {skill.metadata.description}",
                'skill_id': skill.skill_id,
                'metadata': skill.metadata.to_dict()
            })
        
        return tools
    
    def suggest_skills_for_task(
        self,
        task_description: str,
        top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """
        为任务推荐合适的 Skills
        
        Args:
            task_description: 任务描述
            top_k: 推荐数量
        
        Returns:
            推荐 Skills 的详细信息列表
        """
        self.initialize()
        
        skills = self.loader.discover_relevant_skills(task_description, top_k=top_k)
        
        return [
            {
                'id': skill.skill_id,
                'name': skill.metadata.name,
                'description': skill.metadata.description,
                'category': skill.metadata.category,
                'tags': skill.metadata.tags,
                'workflows': [w.to_dict() for w in skill.workflows]
            }
            for skill in skills
        ]
    
    def describe_skill_for_llm(self, skill_id: str) -> str:
        """
        生成 Skill 的 LLM 友好描述
        
        用于详细向 LLM 说明如何使用 Skill
        
        Args:
            skill_id: Skill ID
        
        Returns:
            Skill 的详细描述（Markdown 格式）
        """
        self.initialize()
        
        skill = self.loader.get(skill_id)
        if not skill:
            return f"❌ Skill 不存在: {skill_id}"
        
        return skill.to_llm_description()
    
    def invoke_skill(
        self,
        skill_id: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        调用 Skill
        
        这是 LLM 请求执行 Skill 时的主入口
        
        Args:
            skill_id: Skill ID
            parameters: 执行参数
        
        Returns:
            执行结果字典，包含：
            - success: bool - 是否成功
            - result: Any - 执行结果
            - error: str - 错误信息（如果失败）
        """
        self.initialize()
        
        parameters = parameters or {}
        
        skill = self.loader.get(skill_id)
        if not skill:
            result = {
                'success': False,
                'error': f'Skill 不存在: {skill_id}'
            }
            self.history.record(skill_id, '', parameters, result)
            return result
        
        # 检查是否禁止 LLM 调用
        if skill.metadata.disable_model_invocation:
            result = {
                'success': False,
                'error': f'Skill {skill_id} 已禁用 LLM 调用'
            }
            self.history.record(skill_id, skill.metadata.name, parameters, result)
            return result
        
        try:
            # 执行 Skill（这里可以扩展以支持实际的执行逻辑）
            result = self._execute_skill_internal(skill, parameters)
            
            # 记录执行历史
            self.history.record(skill.skill_id, skill.metadata.name, parameters, result)
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Skill {skill_id} 执行失败: {e}")
            result = {
                'success': False,
                'error': str(e)
            }
            self.history.record(skill_id, skill.metadata.name, parameters, result)
            return result
    
    def _execute_skill_internal(
        self,
        skill: Skill,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        内部执行 Skill
        
        可以扩展此方法以支持不同的执行策略
        
        Args:
            skill: Skill 对象
            parameters: 执行参数
        
        Returns:
            执行结果
        """
        # 这里是基础的执行逻辑
        # 实际的实现可以根据 Skill 类型调用不同的执行器
        
        logger.info(f"🚀 执行 Skill: {skill.metadata.name} (ID: {skill.skill_id})")
        
        # 检查工作流
        if skill.workflows and parameters.get('workflow'):
            workflow_name = parameters.get('workflow')
            workflow = next(
                (w for w in skill.workflows if w.name == workflow_name),
                None
            )
            
            if workflow:
                logger.info(f"   工作流: {workflow_name}")
                logger.info(f"   步骤: {len(workflow.steps)}")
                return {
                    'success': True,
                    'result': {
                        'skill_name': skill.metadata.name,
                        'workflow': workflow_name,
                        'steps_count': len(workflow.steps),
                        'message': f'成功执行 {workflow_name} 工作流 ({len(workflow.steps)} 步)'
                    }
                }
        
        # 基础执行（无工作流）
        return {
            'success': True,
            'result': {
                'skill_name': skill.metadata.name,
                'message': f'成功执行 Skill: {skill.metadata.name}'
            }
        }
    
    def invoke_workflow(
        self,
        skill_id: str,
        workflow_name: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        调用 Skill 中的特定工作流
        
        Args:
            skill_id: Skill ID
            workflow_name: 工作流名称
            parameters: 执行参数
        
        Returns:
            执行结果
        """
        self.initialize()
        
        parameters = parameters or {}
        parameters['workflow'] = workflow_name
        
        return self.invoke_skill(skill_id, parameters)
    
    def get_execution_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取执行历史"""
        return self.history.get_history(limit)
    
    def get_execution_stats(self) -> Dict[str, Any]:
        """获取执行统计"""
        return self.history.get_stats()
    
    def search_skills(
        self,
        query: str = "",
        tags: Optional[List[str]] = None,
        category: Optional[str] = None
    ) -> List[Skill]:
        """
        搜索 Skills
        
        Args:
            query: 搜索关键词
            tags: 标签过滤
            category: 分类过滤
        
        Returns:
            匹配的 Skill 列表
        """
        self.initialize()
        return self.loader.search(query=query, tags=tags, category=category)
    
    def list_skills_by_category(self, category: str) -> List[Skill]:
        """按分类列出 Skills"""
        self.initialize()
        return self.loader.list_by_category(category)
    
    def list_skills_by_tag(self, tag: str) -> List[Skill]:
        """按标签列出 Skills"""
        self.initialize()
        return self.loader.list_by_tag(tag)
    
    def get_skill_registry(self) -> SkillRegistry:
        """获取 Skill 注册表"""
        self.initialize()
        return self.loader.get_skill_registry()
    
    def reload_skills(self) -> int:
        """
        重新加载所有 Skills
        
        Returns:
            加载的 Skill 数量
        """
        self.loader.reload()
        self._loaded = True
        return self.loader.registry.count()
    

class SkillRecommender:
    """Skill 推荐器（占位符实现）"""
    
    def __init__(self, skills_dir: Optional[str] = None):
        from pathlib import Path
        skills_path = Path(skills_dir) if skills_dir else None
        self.loader = SkillLoader(skills_path)
    
    def recommend(self, task_description: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """根据任务推荐 Skills"""
        self.loader.load_all()
        skills = self.loader.discover_relevant_skills(task_description, top_k=top_k)
        return [
            {
                'id': skill.skill_id,
                'name': skill.metadata.name,
                'description': skill.metadata.description,
                'category': skill.metadata.category,
                'tags': skill.metadata.tags
            }
            for skill in skills
        ]


class SkillExecutor:
    """Skill 执行器（占位符实现）"""
    
    def __init__(self, skills_dir: Optional[str] = None):
        from pathlib import Path
        skills_path = Path(skills_dir) if skills_dir else None
        self.loader = SkillLoader(skills_path)
        self.history = SkillExecutionHistory()
    
    def execute(self, skill_id: str, parameters: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
        """执行 Skill"""
        parameters = parameters or {}
        parameters.update(kwargs)  # 合并关键字参数
        
        skill = self.loader.get(skill_id)
        if not skill:
            result = {
                'success': False,
                'error': f'Skill 不存在: {skill_id}'
            }
            self.history.record(skill_id, '', parameters, result)
            return result
        
        try:
            # 这里调用 skill.execute() 的实际实现
            result = skill.execute(**parameters)
            self.history.record(skill_id, skill.metadata.name, parameters, result)
            return result
        except Exception as e:
            logger.error(f"Skill {skill_id} 执行失败: {e}")
            result = {
                'success': False,
                'error': str(e)
            }
            self.history.record(skill_id, skill.metadata.name, parameters, result)
            return result
    
    def get_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取执行历史"""
        return self.history.get_history(limit)

