#!/usr/bin/env python3
"""
Code Skill 模块 - 实现类似 Claude Code Skill 的功能

Code Skill 是可复用的编程技能集合，包含：
1. 元数据 - 名称、描述、标签、版本
2. 实现代码 - 可执行的 Python 代码或工具调用
3. 参数定义 - 输入输出参数规范
4. 使用示例 - 展示如何使用该 Skill
5. 性能指标 - 使用次数、成功率、平均耗时
"""

import json
import uuid
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field, asdict
from utils.logger import logger


@dataclass
class Parameter:
    """参数定义"""
    name: str  # 参数名
    type: str  # 参数类型（str, int, bool, list, dict）
    description: str  # 参数描述
    required: bool = False  # 是否必需
    default: Any = None  # 默认值
    examples: List[Any] = field(default_factory=list)  # 示例值
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SkillMetadata:
    """Skill 元数据"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))  # 唯一ID
    name: str = ""  # Skill 名称
    description: str = ""  # 描述
    version: str = "1.0.0"  # 版本号
    author: str = "IntelliAgent"  # 作者
    tags: List[str] = field(default_factory=list)  # 标签
    category: str = "general"  # 分类
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # 文档
    usage_examples: List[str] = field(default_factory=list)  # 使用示例
    notes: str = ""  # 备注
    dependencies: List[str] = field(default_factory=list)  # 依赖的其他 Skill ID
    
    # 参数
    input_params: List[Parameter] = field(default_factory=list)
    output_params: List[Parameter] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['input_params'] = [p.to_dict() for p in self.input_params]
        data['output_params'] = [p.to_dict() for p in self.output_params]
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SkillMetadata':
        """从字典创建元数据"""
        # 处理参数
        if 'input_params' in data and data['input_params']:
            data['input_params'] = [
                Parameter(**p) if isinstance(p, dict) else p
                for p in data['input_params']
            ]
        else:
            data['input_params'] = []
        
        if 'output_params' in data and data['output_params']:
            data['output_params'] = [
                Parameter(**p) if isinstance(p, dict) else p
                for p in data['output_params']
            ]
        else:
            data['output_params'] = []
        
        return cls(**data)


@dataclass
class SkillImplementation:
    """Skill 实现"""
    code: str = ""  # Python 代码
    language: str = "python"  # 编程语言
    entry_point: str = "execute"  # 入口函数名
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SkillMetrics:
    """Skill 性能指标"""
    usage_count: int = 0  # 使用次数
    success_count: int = 0  # 成功次数
    failure_count: int = 0  # 失败次数
    total_time: float = 0.0  # 总耗时（秒）
    average_time: float = 0.0  # 平均耗时
    last_used: Optional[str] = None  # 最后使用时间
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.usage_count == 0:
            return 0.0
        return self.success_count / self.usage_count
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CodeSkill:
    """Code Skill - 可复用的编程技能"""
    
    def __init__(
        self,
        name: str,
        code: str,
        description: str = "",
        author: str = "IntelliAgent"
    ):
        """
        初始化 Skill
        
        Args:
            name: Skill 名称
            code: 实现代码
            description: 描述
            skill_type: Skill 类型
            author: 作者
        """
        self.metadata = SkillMetadata(
            name=name,
            description=description,
            author=author
        )
        self.implementation = SkillImplementation(code=code)
        self.metrics = SkillMetrics()
        self._sandbox = None  # 执行沙箱
    
    @property
    def id(self) -> str:
        """获取 Skill ID"""
        return self.metadata.id
    
    @property
    def name(self) -> str:
        """获取 Skill 名称"""
        return self.metadata.name
    
    def set_input_params(self, params: List[Parameter]) -> 'CodeSkill':
        """设置输入参数"""
        self.metadata.input_params = params
        return self
    
    def set_output_params(self, params: List[Parameter]) -> 'CodeSkill':
        """设置输出参数"""
        self.metadata.output_params = params
        return self
    
    def add_tag(self, tag: str) -> 'CodeSkill':
        """添加标签"""
        if tag not in self.metadata.tags:
            self.metadata.tags.append(tag)
        return self
    
    def add_example(self, example: str) -> 'CodeSkill':
        """添加使用示例"""
        self.metadata.usage_examples.append(example)
        return self
    
    def add_dependency(self, skill_id: str) -> 'CodeSkill':
        """添加依赖"""
        if skill_id not in self.metadata.dependencies:
            self.metadata.dependencies.append(skill_id)
        return self
    
    def set_category(self, category: str) -> 'CodeSkill':
        """设置分类"""
        self.metadata.category = category
        return self
    
    def execute(
        self,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行 Skill
        
        Args:
            **kwargs: 参数
        
        Returns:
            执行结果 {"success": bool, "result": Any, "error": str, "time": float}
        """
        import time
        start_time = time.time()
        
        try:
            # 创建执行上下文
            sandbox = self._create_sandbox(kwargs)
            
            # 执行代码
            exec(self.implementation.code, sandbox)
            
            # 获取结果
            entry_func = sandbox.get(self.implementation.entry_point)
            if not callable(entry_func):
                raise ValueError(f"入口点 '{self.implementation.entry_point}' 不是可调用的函数")
            
            # 调用入口函数
            result = entry_func(**kwargs)
            
            # 更新指标
            elapsed = time.time() - start_time
            self._update_metrics(True, elapsed)
            
            return {
                "success": True,
                "result": result,
                "time": elapsed
            }
        
        except Exception as e:
            elapsed = time.time() - start_time
            self._update_metrics(False, elapsed)
            
            logger.error(f"执行 Skill '{self.name}' 失败: {e}")
            return {
                "success": False,
                "result": None,
                "error": str(e),
                "time": elapsed
            }
    
    def _create_sandbox(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """创建执行沙箱"""
        sandbox = {
            "__builtins__": {
                # 允许基础函数
                "print": print,
                "len": len,
                "str": str,
                "int": int,
                "float": float,
                "list": list,
                "dict": dict,
                "set": set,
                "range": range,
                "enumerate": enumerate,
                "zip": zip,
                "sorted": sorted,
                "sum": sum,
                "min": min,
                "max": max,
                "any": any,
                "all": all,
                "isinstance": isinstance,
                "type": type,
                "Exception": Exception,
                "ValueError": ValueError,
                "TypeError": TypeError,
                "RuntimeError": RuntimeError,
                # JSON 支持
                "json": __import__('json'),
                # 时间支持
                "datetime": __import__('datetime'),
                "time": __import__('time'),
            }
        }
        
        # 添加参数到沙箱
        sandbox.update(params)
        
        return sandbox
    
    def _update_metrics(self, success: bool, elapsed: float):
        """更新性能指标"""
        self.metrics.usage_count += 1
        if success:
            self.metrics.success_count += 1
        else:
            self.metrics.failure_count += 1
        
        self.metrics.total_time += elapsed
        self.metrics.average_time = self.metrics.total_time / self.metrics.usage_count
        self.metrics.last_used = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "metadata": self.metadata.to_dict(),
            "implementation": self.implementation.to_dict(),
            "metrics": self.metrics.to_dict()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CodeSkill':
        """从字典创建 Skill"""
        metadata = SkillMetadata.from_dict(data['metadata'])
        
        skill = cls(
            name=metadata.name,
            code=data['implementation']['code'],
            description=metadata.description,
            author=metadata.author
        )
        
        # 恢复元数据
        skill.metadata = metadata
        
        # 恢复指标
        if 'metrics' in data:
            metrics_data = data['metrics']
            skill.metrics = SkillMetrics(**metrics_data)
        
        return skill
    
    def to_json(self) -> str:
        """转换为 JSON 字符串"""
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'CodeSkill':
        """从 JSON 字符串创建"""
        data = json.loads(json_str)
        return cls.from_dict(data)
    
    def __repr__(self) -> str:
        return f"<CodeSkill name={self.name} version={self.metadata.version} success_rate={self.metrics.success_rate:.1%}>"
