#!/usr/bin/env python3
"""
Skill 管理器 - 负责 Skill 的存储、检索、版本管理

功能：
1. Skill 的创建、编辑、删除
2. 持久化存储和加载
3. 搜索和分类
4. 版本管理
5. 依赖关系解析
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from .skill import CodeSkill, SkillMetadata, Parameter
from utils.logger import logger


class SkillManager:
    """Skill 管理器"""
    
    def __init__(self, skills_dir: str = "skills"):
        """
        初始化 Skill 管理器
        
        Args:
            skills_dir: Skill 存储目录
        """
        self.skills_dir = Path(skills_dir)
        self.skills: Dict[str, CodeSkill] = {}  # id -> skill
        self.index: Dict[str, Dict[str, List[str]]] = {  # 索引：tag/category -> [skill_id]
            "by_tag": {},
            "by_category": {},
        }
        
        # 创建目录
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"✅ Skill 管理器已初始化 | 目录: {self.skills_dir}")
        
        # 加载已有 Skill
        self.load_all()
    
    def register(self, skill: CodeSkill) -> str:
        """
        注册新 Skill
        
        Args:
            skill: CodeSkill 实例
        
        Returns:
            Skill ID
        """
        skill_id = skill.id
        self.skills[skill_id] = skill
        
        # 更新索引
        self._update_index(skill)
        
        logger.info(f"✅ 注册 Skill: {skill.name} (ID: {skill_id})")
        
        return skill_id
    
    def save(self, skill: CodeSkill) -> Path:
        """
        保存 Skill 到文件
        
        Args:
            skill: CodeSkill 实例
        
        Returns:
            保存的文件路径
        """
        # 创建 Skill 目录
        skill_dir = self.skills_dir / skill.id
        skill_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存 Skill 文件
        skill_file = skill_dir / f"{skill.metadata.name}.json"
        
        with open(skill_file, 'w', encoding='utf-8') as f:
            json.dump(skill.to_dict(), f, indent=2, ensure_ascii=False)
        
        logger.info(f"✅ 已保存 Skill: {skill_file}")
        
        return skill_file
    
    def save_all(self) -> List[Path]:
        """保存所有 Skill"""
        saved_files = []
        for skill in self.skills.values():
            saved_files.append(self.save(skill))
        return saved_files
    
    def load(self, skill_id: str) -> Optional[CodeSkill]:
        """
        加载单个 Skill
        
        Args:
            skill_id: Skill ID
        
        Returns:
            CodeSkill 实例或 None
        """
        if skill_id in self.skills:
            return self.skills[skill_id]
        
        skill_dir = self.skills_dir / skill_id
        if not skill_dir.exists():
            logger.warning(f"⚠️ Skill 目录不存在: {skill_dir}")
            return None
        
        # 查找 JSON 文件
        json_files = list(skill_dir.glob("*.json"))
        if not json_files:
            logger.warning(f"⚠️ Skill 目录中没有 JSON 文件: {skill_dir}")
            return None
        
        skill_file = json_files[0]
        
        try:
            with open(skill_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            skill = CodeSkill.from_dict(data)
            self.skills[skill_id] = skill
            self._update_index(skill)
            
            logger.info(f"✅ 已加载 Skill: {skill.name} (ID: {skill_id})")
            
            return skill
        
        except Exception as e:
            logger.error(f"❌ 加载 Skill 失败 ({skill_file}): {e}")
            return None
    
    def load_all(self) -> int:
        """
        加载所有 Skill
        
        Returns:
            加载的 Skill 数量
        """
        if not self.skills_dir.exists():
            return 0
        
        loaded_count = 0
        for skill_dir in self.skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            
            skill = self.load(skill_dir.name)
            if skill:
                loaded_count += 1
        
        logger.info(f"✅ 已加载 {loaded_count} 个 Skill")
        
        return loaded_count
    
    def unregister(self, skill_id: str) -> bool:
        """
        注销 Skill
        
        Args:
            skill_id: Skill ID
        
        Returns:
            是否成功
        """
        if skill_id not in self.skills:
            logger.warning(f"⚠️ Skill 不存在: {skill_id}")
            return False
        
        skill = self.skills[skill_id]
        
        # 删除文件
        skill_dir = self.skills_dir / skill_id
        if skill_dir.exists():
            import shutil
            shutil.rmtree(skill_dir)
        
        # 从内存移除
        del self.skills[skill_id]
        
        # 更新索引
        self._remove_from_index(skill)
        
        logger.info(f"✅ 已注销 Skill: {skill.name} (ID: {skill_id})")
        
        return True
    
    def get(self, skill_id: str) -> Optional[CodeSkill]:
        """获取 Skill"""
        if skill_id in self.skills:
            return self.skills[skill_id]
        return self.load(skill_id)
    
    def get_by_name(self, name: str) -> Optional[CodeSkill]:
        """根据名称获取 Skill"""
        for skill in self.skills.values():
            if skill.name == name:
                return skill
        return None
    
    def list_all(self) -> List[CodeSkill]:
        """列出所有 Skill"""
        return list(self.skills.values())
    
    def search(
        self,
        query: str = "",
        tags: Optional[List[str]] = None,
        category: Optional[str] = None,
    ) -> List[CodeSkill]:
        """
        搜索 Skill
        
        Args:
            query: 查询关键字（搜索名称和描述）
            tags: 标签列表（OR 关系）
            category: 分类
        
        Returns:
            匹配的 Skill 列表
        """
        results = []
        query_lower = query.lower()
        
        for skill in self.skills.values():
            if query and query_lower not in skill.name.lower() and \
               query_lower not in skill.metadata.description.lower():
                continue
            if category and skill.metadata.category != category:
                continue
            if tags and not any(tag in skill.metadata.tags for tag in tags):
                continue
            results.append(skill)
        
        return results
    
    def get_by_category(self, category: str) -> List[CodeSkill]:
        """获取指定分类的 Skill"""
        return self.search(category=category)
    
    def get_by_tag(self, tag: str) -> List[CodeSkill]:
        """获取指定标签的 Skill"""
        return self.search(tags=[tag])
    
    def _update_index(self, skill: CodeSkill):
        """更新索引"""
        # 按标签索引
        for tag in skill.metadata.tags:
            if tag not in self.index["by_tag"]:
                self.index["by_tag"][tag] = []
            if skill.id not in self.index["by_tag"][tag]:
                self.index["by_tag"][tag].append(skill.id)
        
        # 按分类索引
        category = skill.metadata.category
        if category not in self.index["by_category"]:
            self.index["by_category"][category] = []
        if skill.id not in self.index["by_category"][category]:
            self.index["by_category"][category].append(skill.id)
        
    
    def _remove_from_index(self, skill: CodeSkill):
        """从索引移除"""
        for tag in skill.metadata.tags:
            if tag in self.index["by_tag"]:
                self.index["by_tag"][tag] = [
                    sid for sid in self.index["by_tag"][tag] if sid != skill.id
                ]
        
        category = skill.metadata.category
        if category in self.index["by_category"]:
            self.index["by_category"][category] = [
                sid for sid in self.index["by_category"][category] if sid != skill.id
            ]
        
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        total_skills = len(self.skills)
        total_usages = sum(s.metrics.usage_count for s in self.skills.values())
        total_success = sum(s.metrics.success_count for s in self.skills.values())
        
        return {
            "total_skills": total_skills,
            "total_usages": total_usages,
            "total_success": total_success,
            "success_rate": total_success / total_usages if total_usages > 0 else 0.0,
            "categories": list(self.index["by_category"].keys()),
            "tags": list(self.index["by_tag"].keys()),
            "types": list(self.index["by_type"].keys())
        }
    
    def export(self, output_file: str) -> bool:
        """
        导出所有 Skill
        
        Args:
            output_file: 输出文件路径
        
        Returns:
            是否成功
        """
        try:
            data = {
                "skills": [skill.to_dict() for skill in self.skills.values()],
                "exported_at": datetime.now().isoformat(),
                "total": len(self.skills)
            }
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"✅ 已导出 Skill 到: {output_file}")
            return True
        
        except Exception as e:
            logger.error(f"❌ 导出 Skill 失败: {e}")
            return False
    
    def import_skills(self, input_file: str) -> int:
        """
        导入 Skill
        
        Args:
            input_file: 输入文件路径
        
        Returns:
            导入的 Skill 数量
        """
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            imported_count = 0
            for skill_data in data.get('skills', []):
                try:
                    skill = CodeSkill.from_dict(skill_data)
                    self.register(skill)
                    self.save(skill)
                    imported_count += 1
                except Exception as e:
                    logger.error(f"❌ 导入 Skill 失败: {e}")
                    continue
            
            logger.info(f"✅ 已导入 {imported_count} 个 Skill")
            return imported_count
        
        except Exception as e:
            logger.error(f"❌ 读取导入文件失败: {e}")
            return 0
