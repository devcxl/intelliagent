#!/usr/bin/env python3
"""
基于 Claude Code 标准的 Skill 系统

实现功能：
1. 从 .claude/skills/{skill-name}/SKILL.md 加载 Skill 定义
2. 解析 YAML 前置元数据和 Markdown 内容
3. 支持工作流定义和资源文件引用
4. 提供 LLM 友好的 Skill 描述生成
5. 管理 Skill 的生命周期和执行
"""

import re
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from utils.logger import logger


@dataclass
class Workflow:
    """Workflow 定义"""
    name: str  # 工作流名称
    description: str  # 工作流描述
    steps: List[str] = field(default_factory=list)  # 执行步骤
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'description': self.description,
            'steps': self.steps
        }


@dataclass
class SkillMetadata:
    """Skill 元数据（从 SKILL.md 的 YAML 前置部分解析）"""
    id: str  # 来自目录名称
    name: str  # Skill 名称
    description: str  # Skill 描述
    version: str = "1.0.0"  # 版本号
    author: str = ""  # 作者
    tags: List[str] = field(default_factory=list)  # 标签
    category: str = "general"  # 分类
    disable_model_invocation: bool = False  # 是否禁止 LLM 调用
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'version': self.version,
            'author': self.author,
            'tags': self.tags,
            'category': self.category,
            'disable_model_invocation': self.disable_model_invocation
        }


class Skill:
    """
    Claude Code Skill 定义
    
    对应 .claude/skills/{skill-name}/ 目录结构：
    - SKILL.md          # 主定义文件（包含 YAML 前置和 Markdown 内容）
    - README.md         # 可选文档
    - *.md              # 其他资源文件
    - scripts/          # 可选脚本目录
    """
    
    def __init__(
        self,
        skill_id: str,
        metadata: SkillMetadata,
        content: str = "",
        resources: Optional[Dict[str, str]] = None,
        skill_dir: Optional[Path] = None
    ):
        """
        初始化 Skill
        
        Args:
            skill_id: Skill 唯一标识（来自目录名）
            metadata: Skill 元数据
            content: Markdown 内容（SKILL.md 的正文）
            resources: 资源文件映射 {filename: content}
            skill_dir: Skill 所在目录路径
        """
        self.skill_id = skill_id
        self.metadata = metadata
        self.content = content
        self.resources = resources or {}
        self.skill_dir = skill_dir
        self.workflows: List[Workflow] = []
        self.created_at = datetime.now().isoformat()
        
        # 从内容解析工作流
        self._parse_workflows()
    
    def _parse_workflows(self) -> None:
        """从 Markdown 内容解析工作流部分"""
        # 查找 ## Workflows 或 ## 工作流 部分
        # 匹配直到下一个 ## 或文件结束
        workflow_pattern = r'##\s+(?:Workflows|工作流)[\s\S]*?(?=\n##\s|\Z)'
        match = re.search(workflow_pattern, self.content)
        
        if not match:
            return
        
        workflow_section = match.group(0)
        
        # 解析每个工作流
        # 格式: ### WorkflowName\n描述\n步骤列表
        workflow_blocks = re.findall(
            r'###\s+(.+?)\n([\s\S]*?)(?=\n###\s|\Z)',
            workflow_section
        )
        
        for name, content in workflow_blocks:
            name = name.strip()
            
            # 提取描述（第一行）
            lines = content.strip().split('\n')
            description = lines[0] if lines else ""
            
            # 提取步骤（以 - 或 * 开头的行）
            steps = []
            for line in lines[1:]:
                stripped = line.strip()
                if stripped.startswith(('-', '*')):
                    # 移除列表标记和多余空白
                    step_text = stripped[1:].strip()
                    if step_text:
                        steps.append(step_text)
            
            workflow = Workflow(
                name=name,
                description=description,
                steps=steps
            )
            self.workflows.append(workflow)
    
    def get_resource(self, resource_name: str) -> Optional[str]:
        """
        获取资源文件内容
        
        Args:
            resource_name: 资源文件名（如 'README.md'）
        
        Returns:
            资源文件内容，如果不存在返回 None
        """
        return self.resources.get(resource_name)
    
    def list_resources(self) -> List[str]:
        """列出所有可用资源"""
        return list(self.resources.keys())
    
    def to_llm_description(self) -> str:
        """
        生成 LLM 友好的 Skill 描述
        
        用于提供给 LLM 作为工具描述
        """
        description = f"**Skill: {self.metadata.name}**\n"
        description += f"Description: {self.metadata.description}\n"
        
        if self.metadata.tags:
            description += f"Tags: {', '.join(self.metadata.tags)}\n"
        
        if self.metadata.category:
            description += f"Category: {self.metadata.category}\n"
        
        if self.workflows:
            description += "\n**Available Workflows:**\n"
            for workflow in self.workflows:
                description += f"- {workflow.name}: {workflow.description}\n"
                if workflow.steps:
                    for i, step in enumerate(workflow.steps, 1):
                        description += f"  {i}. {step}\n"
        
        # 添加资源文件列表
        if self.resources:
            resource_names = [name for name in self.resources.keys() if name != 'SKILL.md']
            if resource_names:
                description += f"\n**Resources:** {', '.join(resource_names)}\n"
        
        return description
    
    def to_dict(self) -> Dict[str, Any]:
        """将 Skill 转换为字典"""
        return {
            'id': self.skill_id,
            'metadata': self.metadata.to_dict(),
            'content': self.content,
            'workflows': [w.to_dict() for w in self.workflows],
            'resources': list(self.resources.keys()),
            'created_at': self.created_at
        }
    
    def validate(self) -> Tuple[bool, List[str]]:
        """
        验证 Skill 定义的完整性
        
        Returns:
            (is_valid, errors) 元组
        """
        errors = []
        
        # 必需字段检查
        if not self.skill_id:
            errors.append("Skill ID 不能为空")
        
        if not self.metadata.name:
            errors.append("Skill 名称不能为空")
        
        if not self.metadata.description:
            errors.append("Skill 描述不能为空")
        
        # 内容检查
        if not self.content and not self.resources.get('README.md'):
            errors.append("Skill 必须有内容或 README.md 文档")
        
        return len(errors) == 0, errors


class SkillParser:
    """Markdown 格式 Skill 解析器"""
    
    @staticmethod
    def parse_skill_md(content: str) -> Tuple[Dict[str, Any], str]:
        """
        解析 SKILL.md 文件内容
        
        格式：
        ---
        name: Skill 名称
        description: Skill 描述
        version: 1.0.0
        tags: [tag1, tag2]
        category: category_name
        ---
        
        # Markdown 内容
        ## Workflows
        ...
        
        Args:
            content: 文件内容
        
        Returns:
            (metadata_dict, markdown_content) 元组
        """
        # 解析 YAML 前置部分
        metadata = {}
        markdown_content = content
        
        # 检查是否有 YAML 前置
        if content.startswith('---'):
            try:
                # 找到第二个 ---
                parts = content.split('---', 2)
                if len(parts) >= 3:
                    yaml_content = parts[1]
                    markdown_content = parts[2].lstrip('\n')
                    
                    # 解析 YAML
                    metadata = yaml.safe_load(yaml_content) or {}
            except yaml.YAMLError as e:
                logger.warning(f"❌ YAML 解析失败: {e}")
                metadata = {}
        
        return metadata, markdown_content
    
    @staticmethod
    def create_skill_from_md(
        skill_id: str,
        skill_md_path: Path,
        skill_dir: Path
    ) -> Optional[Skill]:
        """
        从 SKILL.md 文件创建 Skill 对象
        
        Args:
            skill_id: Skill ID（来自目录名）
            skill_md_path: SKILL.md 文件路径
            skill_dir: Skill 目录路径
        
        Returns:
            Skill 对象，如果失败返回 None
        """
        try:
            # 读取 SKILL.md 文件
            skill_md_content = skill_md_path.read_text(encoding='utf-8')
            
            # 解析元数据和内容
            metadata_dict, markdown_content = SkillParser.parse_skill_md(skill_md_content)
            
            # 创建元数据对象
            name = metadata_dict.get('name', skill_id)
            description = metadata_dict.get('description', '')
            version = metadata_dict.get('version', '1.0.0')
            author = metadata_dict.get('author', '')
            tags = metadata_dict.get('tags', [])
            category = metadata_dict.get('category', 'general')
            disable_model_invocation = metadata_dict.get('disable_model_invocation', False)
            
            metadata = SkillMetadata(
                id=skill_id,
                name=name,
                description=description,
                version=version,
                author=author,
                tags=tags if isinstance(tags, list) else [],
                category=category,
                disable_model_invocation=disable_model_invocation
            )
            
            # 加载资源文件
            resources = {'SKILL.md': skill_md_content}
            
            # 加载目录中的其他 .md 文件
            for md_file in skill_dir.glob('*.md'):
                if md_file.name != 'SKILL.md':
                    try:
                        resources[md_file.name] = md_file.read_text(encoding='utf-8')
                    except Exception as e:
                        logger.warning(f"⚠️  无法读取资源文件 {md_file.name}: {e}")
            
            # 创建 Skill 对象
            skill = Skill(
                skill_id=skill_id,
                metadata=metadata,
                content=markdown_content,
                resources=resources,
                skill_dir=skill_dir
            )
            
            # 验证
            is_valid, errors = skill.validate()
            if not is_valid:
                logger.warning(f"⚠️  Skill {skill_id} 验证失败: {errors}")
            
            return skill
            
        except Exception as e:
            logger.error(f"❌ 加载 Skill {skill_id} 失败: {e}")
            return None


class SkillRegistry:
    """Skill 注册表 - 管理已加载的 Skills"""
    
    def __init__(self):
        """初始化注册表"""
        self._skills: Dict[str, Skill] = {}
    
    def register(self, skill: Skill) -> None:
        """注册 Skill"""
        self._skills[skill.skill_id] = skill
        logger.info(f"✅ 注册 Skill: {skill.metadata.name} (ID: {skill.skill_id})")
    
    def get(self, skill_id: str) -> Optional[Skill]:
        """获取 Skill"""
        return self._skills.get(skill_id)
    
    def get_by_name(self, name: str) -> Optional[Skill]:
        """按名称获取 Skill"""
        for skill in self._skills.values():
            if skill.metadata.name == name:
                return skill
        return None
    
    def list_all(self) -> List[Skill]:
        """列出所有 Skills"""
        return list(self._skills.values())
    
    def list_by_tag(self, tag: str) -> List[Skill]:
        """按标签列出 Skills"""
        return [
            skill for skill in self._skills.values()
            if tag in skill.metadata.tags
        ]
    
    def list_by_category(self, category: str) -> List[Skill]:
        """按分类列出 Skills"""
        return [
            skill for skill in self._skills.values()
            if skill.metadata.category == category
        ]
    
    def search(
        self,
        query: str = "",
        tags: Optional[List[str]] = None,
        category: Optional[str] = None
    ) -> List[Skill]:
        """
        搜索 Skills
        
        Args:
            query: 搜索关键词（匹配名称和描述）
            tags: 标签过滤
            category: 分类过滤
        
        Returns:
            匹配的 Skill 列表
        """
        results = []
        query_lower = query.lower()
        
        for skill in self._skills.values():
            # 检查关键词匹配
            if query and not (
                query_lower in skill.metadata.name.lower() or
                query_lower in skill.metadata.description.lower()
            ):
                continue
            
            # 检查标签过滤
            if tags and not any(tag in skill.metadata.tags for tag in tags):
                continue
            
            # 检查分类过滤
            if category and skill.metadata.category != category:
                continue
            
            results.append(skill)
        
        return results
    
    def unregister(self, skill_id: str) -> bool:
        """注销 Skill"""
        if skill_id in self._skills:
            del self._skills[skill_id]
            logger.info(f"✅ 注销 Skill: {skill_id}")
            return True
        return False
    
    def count(self) -> int:
        """获取已注册 Skill 数量"""
        return len(self._skills)
