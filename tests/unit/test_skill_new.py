#!/usr/bin/env python3
"""
Claude Code 风格 Skill 系统测试

测试新的基于 Markdown 的 Skill 实现

运行: pytest test/test_skill_new.py -v
"""

import pytest
import tempfile
from pathlib import Path

from src.skills.skill_system import (
    Skill, SkillMetadata, SkillParser, SkillRegistry, Workflow
)
from src.skills.skill_loader import SkillLoader
from src.skills.skill_integration import SkillIntegration, SkillExecutionHistory


class TestSkillMetadata:
    """Skill 元数据测试"""
    
    def test_create_metadata(self):
        """测试创建元数据"""
        metadata = SkillMetadata(
            id="test-skill",
            name="Test Skill",
            description="A test skill"
        )
        
        assert metadata.id == "test-skill"
        assert metadata.name == "Test Skill"
        assert metadata.description == "A test skill"
        assert metadata.version == "1.0.0"
    
    def test_metadata_to_dict(self):
        """测试元数据转字典"""
        metadata = SkillMetadata(
            id="test",
            name="Test",
            description="Test Skill",
            tags=["test", "demo"]
        )
        
        data = metadata.to_dict()
        assert data['id'] == 'test'
        assert data['tags'] == ['test', 'demo']
        assert isinstance(data, dict)


class TestSkillParser:
    """Skill 解析器测试"""
    
    def test_parse_skill_md_with_yaml(self):
        """测试解析带 YAML 前置的 Markdown"""
        content = """---
name: Test Skill
description: A test skill
version: 1.0.0
tags:
  - test
  - demo
---

# Content

This is the markdown content.
"""
        metadata, markdown = SkillParser.parse_skill_md(content)
        
        assert metadata['name'] == 'Test Skill'
        assert metadata['description'] == 'A test skill'
        assert metadata['tags'] == ['test', 'demo']
        assert 'This is the markdown content.' in markdown
    
    def test_parse_skill_md_without_yaml(self):
        """测试解析无 YAML 前置的 Markdown"""
        content = "# Just Markdown\n\nNo YAML here."
        metadata, markdown = SkillParser.parse_skill_md(content)
        
        assert metadata == {} or metadata is None or isinstance(metadata, dict)
        assert '# Just Markdown' in markdown


class TestSkill:
    """Skill 类测试"""
    
    def test_create_skill(self):
        """测试创建 Skill"""
        metadata = SkillMetadata(
            id="test",
            name="Test Skill",
            description="Test"
        )
        
        skill = Skill(
            skill_id="test",
            metadata=metadata,
            content="# Content"
        )
        
        assert skill.skill_id == "test"
        assert skill.metadata.name == "Test Skill"
    
    def test_skill_workflow_parsing(self):
        """测试工作流解析"""
        content = """
## Workflows

### Workflow 1
这是工作流 1

- 步骤 1
- 步骤 2

### Workflow 2
这是工作流 2

- 步骤 A
- 步骤 B
"""
        metadata = SkillMetadata(
            id="test",
            name="Test",
            description="Test"
        )
        
        skill = Skill(
            skill_id="test",
            metadata=metadata,
            content=content
        )
        
        assert len(skill.workflows) == 2
        assert skill.workflows[0].name == "Workflow 1"
        assert len(skill.workflows[0].steps) == 2
    
    def test_skill_resources(self):
        """测试 Skill 资源管理"""
        resources = {
            'SKILL.md': 'Content of SKILL.md',
            'README.md': 'Content of README.md'
        }
        
        metadata = SkillMetadata(
            id="test",
            name="Test",
            description="Test"
        )
        
        skill = Skill(
            skill_id="test",
            metadata=metadata,
            resources=resources
        )
        
        assert skill.get_resource('README.md') == 'Content of README.md'
        assert 'README.md' in skill.list_resources()
    
    def test_skill_validation(self):
        """测试 Skill 验证"""
        # 有效的 Skill
        metadata = SkillMetadata(
            id="test",
            name="Test",
            description="Test"
        )
        
        skill = Skill(
            skill_id="test",
            metadata=metadata,
            content="# Content"
        )
        
        is_valid, errors = skill.validate()
        assert is_valid
        assert len(errors) == 0
        
        # 无效的 Skill（无内容和资源）
        skill2 = Skill(
            skill_id="",
            metadata=SkillMetadata(id="", name="", description=""),
            content=""
        )
        
        is_valid, errors = skill2.validate()
        assert not is_valid
        assert len(errors) > 0


class TestSkillRegistry:
    """Skill 注册表测试"""
    
    def test_register_skill(self):
        """测试注册 Skill"""
        registry = SkillRegistry()
        
        metadata = SkillMetadata(
            id="test",
            name="Test",
            description="Test"
        )
        
        skill = Skill(
            skill_id="test",
            metadata=metadata
        )
        
        registry.register(skill)
        assert registry.get("test") == skill
    
    def test_search_skills(self):
        """测试搜索 Skills"""
        registry = SkillRegistry()
        
        # 创建多个 Skills
        for i in range(3):
            metadata = SkillMetadata(
                id=f"skill-{i}",
                name=f"Test Skill {i}",
                description=f"Test skill {i}",
                tags=["test"]
            )
            skill = Skill(
                skill_id=f"skill-{i}",
                metadata=metadata
            )
            registry.register(skill)
        
        # 搜索
        results = registry.search(query="Test Skill", tags=["test"])
        assert len(results) >= 2
    
    def test_list_by_tag(self):
        """测试按标签列出"""
        registry = SkillRegistry()
        
        metadata1 = SkillMetadata(
            id="skill1",
            name="Skill 1",
            description="Test",
            tags=["coding"]
        )
        metadata2 = SkillMetadata(
            id="skill2",
            name="Skill 2",
            description="Test",
            tags=["documentation"]
        )
        
        registry.register(Skill("skill1", metadata1))
        registry.register(Skill("skill2", metadata2))
        
        coding_skills = registry.list_by_tag("coding")
        assert len(coding_skills) == 1
        assert coding_skills[0].skill_id == "skill1"


class TestSkillLoader:
    """Skill 加载器测试"""
    
    def test_loader_load_all(self):
        """测试加载所有 Skills"""
        loader = SkillLoader()
        skills = loader.load_all()
        
        assert isinstance(skills, list)
        # 应该加载示例 Skills
        assert len(skills) > 0
    
    def test_loader_get_skill(self):
        """测试获取单个 Skill"""
        loader = SkillLoader()
        loader.load_all()
        
        # 尝试获取已知的 Skill
        skill = loader.get("code-review")
        if skill:
            assert skill.skill_id == "code-review"
    
    def test_loader_search(self):
        """测试搜索"""
        loader = SkillLoader()
        loader.load_all()
        
        results = loader.search(query="code")
        assert isinstance(results, list)
    
    def test_loader_reload(self):
        """测试重新加载"""
        loader = SkillLoader()
        loader.load_all()
        count1 = loader.registry.count()
        
        loader.reload()
        count2 = loader.registry.count()
        
        assert count1 == count2


class TestSkillIntegration:
    """Skill 集成测试"""
    
    def test_skill_integration_init(self):
        """测试初始化"""
        integration = SkillIntegration()
        integration.initialize()
        
        count = integration.get_skill_count()
        assert count > 0
    
    def test_available_skills_for_llm(self):
        """测试获取 LLM 可用的 Skills"""
        integration = SkillIntegration()
        integration.initialize()
        
        description = integration.get_available_skills_for_llm()
        assert isinstance(description, str)
        assert len(description) > 0
    
    def test_suggest_skills(self):
        """测试推荐 Skills"""
        integration = SkillIntegration()
        integration.initialize()
        
        recommendations = integration.suggest_skills_for_task(
            "write documentation"
        )
        
        assert isinstance(recommendations, list)
    
    def test_invoke_skill(self):
        """测试调用 Skill"""
        integration = SkillIntegration()
        integration.initialize()
        
        # 尝试调用不存在的 Skill
        result = integration.invoke_skill("nonexistent")
        
        assert isinstance(result, dict)
        assert 'success' in result
        assert result['success'] is False
    
    def test_skill_execution_history(self):
        """测试执行历史"""
        history = SkillExecutionHistory()
        
        history.record("skill1", "Test Skill", {}, {
            'success': True,
            'result': 'test'
        })
        
        records = history.get_history()
        assert len(records) == 1
        assert records[0]['skill_id'] == 'skill1'
    
    def test_execution_stats(self):
        """测试执行统计"""
        history = SkillExecutionHistory()
        
        history.record("skill1", "Test", {}, {'success': True})
        history.record("skill1", "Test", {}, {'success': False})
        
        stats = history.get_stats()
        assert stats['total_executions'] == 2
        assert stats['successful'] == 1
        assert stats['failed'] == 1


class TestSkillIntegrationWithLoader:
    """Skill 集成与加载器集成测试"""
    
    def test_integration_uses_loader(self):
        """测试集成正确使用加载器"""
        integration = SkillIntegration()
        integration.initialize()
        
        registry = integration.get_skill_registry()
        assert registry is not None
        assert registry.count() > 0
    
    def test_describe_skill_for_llm(self):
        """测试为 LLM 生成 Skill 描述"""
        integration = SkillIntegration()
        integration.initialize()
        
        # 获取第一个 Skill
        skills = integration.loader.list_all()
        if skills:
            skill_id = skills[0].skill_id
            desc = integration.describe_skill_for_llm(skill_id)
            
            assert isinstance(desc, str)
            assert len(desc) > 0
            assert "Skill:" in desc or "skill" in desc.lower()


# 集成测试
class TestSkillSystemIntegration:
    """完整 Skill 系统集成测试"""
    
    def test_full_workflow(self):
        """测试完整工作流"""
        # 1. 初始化加载器
        loader = SkillLoader()
        skills = loader.load_all()
        
        assert len(skills) > 0
        
        # 2. 使用集成接口
        integration = SkillIntegration()
        integration.initialize()
        
        # 3. 获取可用 Skills
        available = integration.get_available_skills_for_llm()
        assert len(available) > 0
        
        # 4. 推荐 Skills
        recommendations = integration.suggest_skills_for_task(
            "code analysis"
        )
        assert isinstance(recommendations, list)
        
        # 5. 执行 Skill（即使失败也应该被正确处理）
        result = integration.invoke_skill("code-review")
        assert 'success' in result


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
