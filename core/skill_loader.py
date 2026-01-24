#!/usr/bin/env python3
"""
Skill 加载器 - 从 .claude/skills 目录加载和管理 Skills

功能：
1. 扫描 .claude/skills 目录
2. 发现和加载 SKILL.md 文件
3. 索引和缓存 Skills
4. 提供搜索和过滤功能
"""

from pathlib import Path
from typing import Optional, List, Dict, Any
from .skill_system import Skill, SkillParser, SkillRegistry
from utils.logger import logger


class SkillLoader:
    """
    Skill 加载器
    
    负责从 .claude/skills 目录加载 Skills
    """
    
    DEFAULT_SKILLS_DIR = ".claude/skills"
    
    def __init__(self, skills_dir: Optional[Path] = None):
        """
        初始化加载器
        
        Args:
            skills_dir: Skills 目录路径，默认为 .claude/skills
        """
        if skills_dir is None:
            skills_dir = Path(self.DEFAULT_SKILLS_DIR)
        
        self.skills_dir = skills_dir.resolve()
        self.registry = SkillRegistry()
        self._loaded = False
    
    def load_all(self) -> List[Skill]:
        """
        加载所有 Skills
        
        扫描 .claude/skills 目录，加载每个子目录中的 SKILL.md
        
        Returns:
            加载成功的 Skill 列表
        """
        if self._loaded:
            logger.info(f"📚 Skills 已加载 ({self.registry.count()} 个)")
            return self.registry.list_all()
        
        if not self.skills_dir.exists():
            logger.warning(f"⚠️  Skills 目录不存在: {self.skills_dir}")
            return []
        
        logger.info(f"📚 正在从 {self.skills_dir} 加载 Skills...")
        
        loaded_skills = []
        
        # 遍历 skills 目录中的每个子目录
        for skill_dir in self.skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            
            skill_id = skill_dir.name
            
            # 查找 SKILL.md 文件
            skill_md_path = skill_dir / "SKILL.md"
            
            if not skill_md_path.exists():
                logger.warning(f"⚠️  找不到 SKILL.md: {skill_dir}")
                continue
            
            # 加载 Skill
            skill = SkillParser.create_skill_from_md(
                skill_id=skill_id,
                skill_md_path=skill_md_path,
                skill_dir=skill_dir
            )
            
            if skill:
                self.registry.register(skill)
                loaded_skills.append(skill)
        
        logger.info(f"✅ 成功加载 {len(loaded_skills)} 个 Skills")
        self._loaded = True
        
        return loaded_skills
    
    def load_skill(self, skill_id: str) -> Optional[Skill]:
        """
        加载单个 Skill
        
        Args:
            skill_id: Skill ID（目录名）
        
        Returns:
            Skill 对象，如果不存在或加载失败返回 None
        """
        skill_dir = self.skills_dir / skill_id
        
        if not skill_dir.exists():
            logger.warning(f"⚠️  Skill 目录不存在: {skill_dir}")
            return None
        
        skill_md_path = skill_dir / "SKILL.md"
        
        if not skill_md_path.exists():
            logger.warning(f"⚠️  找不到 SKILL.md: {skill_dir}")
            return None
        
        skill = SkillParser.create_skill_from_md(
            skill_id=skill_id,
            skill_md_path=skill_md_path,
            skill_dir=skill_dir
        )
        
        if skill:
            self.registry.register(skill)
            return skill
        
        return None
    
    def reload(self) -> List[Skill]:
        """
        重新加载所有 Skills（清除缓存）
        
        Returns:
            加载的 Skill 列表
        """
        self._loaded = False
        self.registry = SkillRegistry()
        return self.load_all()
    
    def get(self, skill_id: str) -> Optional[Skill]:
        """获取已加载的 Skill"""
        return self.registry.get(skill_id)
    
    def get_by_name(self, name: str) -> Optional[Skill]:
        """按名称获取 Skill"""
        return self.registry.get_by_name(name)
    
    def list_all(self) -> List[Skill]:
        """列出所有已加载的 Skills"""
        if not self._loaded:
            self.load_all()
        return self.registry.list_all()
    
    def list_by_tag(self, tag: str) -> List[Skill]:
        """按标签列出 Skills"""
        if not self._loaded:
            self.load_all()
        return self.registry.list_by_tag(tag)
    
    def list_by_category(self, category: str) -> List[Skill]:
        """按分类列出 Skills"""
        if not self._loaded:
            self.load_all()
        return self.registry.list_by_category(category)
    
    def search(
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
        if not self._loaded:
            self.load_all()
        
        return self.registry.search(query=query, tags=tags, category=category)
    
    def discover_relevant_skills(
        self,
        task_description: str,
        top_k: int = 5
    ) -> List[Skill]:
        """
        发现与任务相关的 Skills
        
        根据任务描述的关键词找到相关 Skills
        
        Args:
            task_description: 任务描述
            top_k: 返回数量
        
        Returns:
            相关 Skills 列表（按相关度排序）
        """
        if not self._loaded:
            self.load_all()
        
        all_skills = self.registry.list_all()
        
        # 计算每个 Skill 与任务的相关度
        scored_skills = []
        task_words = set(task_description.lower().split())
        
        for skill in all_skills:
            # 跳过禁止 LLM 调用的 Skills
            if skill.metadata.disable_model_invocation:
                continue
            
            score = self._calculate_relevance(
                skill,
                task_description,
                task_words
            )
            
            if score > 0:
                scored_skills.append((skill, score))
        
        # 按相关度排序
        scored_skills.sort(key=lambda x: x[1], reverse=True)
        
        return [skill for skill, _ in scored_skills[:top_k]]
    
    @staticmethod
    def _calculate_relevance(
        skill: Skill,
        task_description: str,
        task_words: set
    ) -> float:
        """
        计算 Skill 与任务的相关度
        
        Args:
            skill: Skill 对象
            task_description: 任务描述
            task_words: 任务关键词集合
        
        Returns:
            相关度分数 (0.0 - 1.0)
        """
        score = 0.0
        
        # 1. 名称匹配 (权重 0.4)
        skill_name_words = set(skill.metadata.name.lower().split())
        name_overlap = len(task_words & skill_name_words) / max(
            len(task_words | skill_name_words), 1
        )
        score += name_overlap * 0.4
        
        # 2. 描述匹配 (权重 0.3)
        desc_words = set(skill.metadata.description.lower().split())
        desc_overlap = len(task_words & desc_words) / max(
            len(task_words | desc_words), 1
        )
        score += desc_overlap * 0.3
        
        # 3. 标签匹配 (权重 0.2)
        if skill.metadata.tags:
            task_desc_lower = task_description.lower()
            tag_matches = sum(
                1 for tag in skill.metadata.tags
                if tag.lower() in task_desc_lower
            )
            tag_score = min(tag_matches / len(skill.metadata.tags), 1.0)
            score += tag_score * 0.2
        
        # 4. 工作流数量 (权重 0.1)
        workflow_bonus = min(len(skill.workflows) / 5.0, 1.0)
        score += workflow_bonus * 0.1
        
        return min(score, 1.0)
    
    def get_available_skills_description(self) -> str:
        """
        获取所有可用 Skills 的描述
        
        用于提供给 LLM
        
        Returns:
            Skill 列表描述（Markdown 格式）
        """
        if not self._loaded:
            self.load_all()
        
        skills = self.registry.list_all()
        
        if not skills:
            return "暂无可用 Skills"
        
        descriptions = []
        
        for skill in skills:
            desc = f"**{skill.metadata.name}** (ID: {skill.skill_id})"
            desc += f"\n  {skill.metadata.description}"
            
            if skill.metadata.tags:
                desc += f"\n  Tags: {', '.join(skill.metadata.tags)}"
            
            if skill.workflows:
                desc += "\n  Workflows:"
                for workflow in skill.workflows:
                    desc += f"\n    - {workflow.name}: {workflow.description}"
            
            descriptions.append(desc)
        
        return "\n\n".join(descriptions)
    
    def get_skill_registry(self) -> SkillRegistry:
        """获取 Skill 注册表"""
        if not self._loaded:
            self.load_all()
        return self.registry
    
    def export_skills_index(self) -> Dict[str, Dict[str, Any]]:
        """
        导出 Skills 索引（用于序列化）
        
        Returns:
            Skills 索引字典
        """
        if not self._loaded:
            self.load_all()
        
        index = {}
        for skill in self.registry.list_all():
            index[skill.skill_id] = skill.to_dict()
        
        return index
