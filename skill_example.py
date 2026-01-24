#!/usr/bin/env python3
"""
Code Skill 系统演示
展示如何创建、管理和使用 Code Skill
"""

from core.skill import CodeSkill, Parameter
from core.skill_manager import SkillManager
from core.skill_integration import SkillIntegration
from utils.logger import logger


def example_1_create_basic_skill():
    """例子 1: 创建基础 Skill"""
    logger.info("\n" + "="*60)
    logger.info("例子 1: 创建基础 Skill")
    logger.info("="*60)
    
    # 创建一个简单的数据处理 Skill
    code = """
def execute(data, operation):
    '''执行数据操作'''
    if operation == 'sum':
        return {'result': sum(data)}
    elif operation == 'avg':
        return {'result': sum(data) / len(data)}
    elif operation == 'max':
        return {'result': max(data)}
    elif operation == 'min':
        return {'result': min(data)}
    else:
        raise ValueError(f"未支持的操作: {operation}")
"""
    
    skill = CodeSkill(
        name="数据统计",
        code=code,
        description="对数列进行基本统计操作"
    )
    
    # 设置参数
    skill.set_input_params([
        Parameter("data", "list", "要统计的数列", required=True, 
                 examples=[[1, 2, 3, 4, 5]]),
        Parameter("operation", "str", "操作类型 (sum/avg/max/min)", required=True,
                 examples=["sum", "avg"])
    ])
    
    skill.set_output_params([
        Parameter("result", "number", "统计结果", required=True)
    ])
    
    # 添加元数据
    skill.add_tag("数据处理").add_tag("统计").set_category("data-processing")
    skill.add_example("数据统计('求和', [1,2,3,4,5]) -> {'result': 15}")
    skill.add_example("数据统计('平均', [1,2,3,4,5]) -> {'result': 3.0}")
    
    # 测试执行
    logger.info(f"\n创建 Skill: {skill.name}")
    logger.info(f"描述: {skill.metadata.description}")
    logger.info(f"标签: {skill.metadata.tags}")
    
    # 执行 Skill
    logger.info("\n执行测试...")
    result1 = skill.execute(data=[1, 2, 3, 4, 5], operation="sum")
    logger.info(f"  sum([1,2,3,4,5]) = {result1}")
    
    result2 = skill.execute(data=[10, 20, 30], operation="avg")
    logger.info(f"  avg([10,20,30]) = {result2}")
    
    logger.info(f"\nSkill 指标: {skill}")
    
    return skill


def example_2_skill_management():
    """例子 2: Skill 管理"""
    logger.info("\n" + "="*60)
    logger.info("例子 2: Skill 管理（创建、保存、加载）")
    logger.info("="*60)
    
    # 初始化管理器
    manager = SkillManager(skills_dir="skills")
    logger.info(f"初始化 Skill 管理器，目录: skills")
    
    # 创建多个 Skill
    skills = []
    
    # Skill 1: JSON 处理
    json_code = """
import json

def execute(json_str, action):
    '''JSON 处理操作'''
    data = json.loads(json_str)
    if action == 'pretty':
        return {'result': json.dumps(data, indent=2, ensure_ascii=False)}
    elif action == 'minify':
        return {'result': json.dumps(data, separators=(',', ':'))}
    elif action == 'keys':
        if isinstance(data, dict):
            return {'result': list(data.keys())}
        else:
            raise ValueError("期望字典类型")
    else:
        raise ValueError(f"未支持的操作: {action}")
"""
    
    json_skill = CodeSkill(
        name="JSON处理",
        code=json_code,
        description="处理 JSON 字符串的格式化、压缩和键提取操作"
    )
    json_skill.add_tag("JSON").add_tag("文本处理").set_category("text")
    
    # Skill 2: 字符串处理
    str_code = """
def execute(text, action, pattern=None):
    '''字符串处理'''
    if action == 'upper':
        return {'result': text.upper()}
    elif action == 'lower':
        return {'result': text.lower()}
    elif action == 'reverse':
        return {'result': text[::-1]}
    elif action == 'count':
        if pattern:
            return {'result': text.count(pattern)}
        return {'result': len(text)}
    else:
        raise ValueError(f"未支持的操作: {action}")
"""
    
    str_skill = CodeSkill(
        name="字符串处理",
        code=str_code,
        description="字符串的转换、反转、计数等操作"
    )
    str_skill.add_tag("字符串").add_tag("文本处理").set_category("text")
    
    # 注册 Skill
    for skill in [json_skill, str_skill]:
        manager.register(skill)
        manager.save(skill)
    
    logger.info(f"\n已注册 {len(manager.skills)} 个 Skill")
    
    # 列出所有 Skill
    logger.info("\n所有已注册的 Skill:")
    for skill in manager.list_all():
        logger.info(f"  - {skill.name} ({skill.id})")
        logger.info(f"    描述: {skill.metadata.description}")
        logger.info(f"    标签: {skill.metadata.tags}")
    
    # 搜索 Skill
    logger.info("\n搜索 'JSON' 相关 Skill:")
    results = manager.search(query="JSON")
    for skill in results:
        logger.info(f"  - {skill.name}")
    
    # 获取统计信息
    stats = manager.get_stats()
    logger.info(f"\n统计信息:")
    logger.info(f"  总数: {stats['total_skills']}")
    logger.info(f"  分类: {stats['categories']}")
    logger.info(f"  标签: {stats['tags']}")
    
    return manager


def example_3_skill_recommendation():
    """例子 3: Skill 推荐"""
    logger.info("\n" + "="*60)
    logger.info("例子 3: Skill 推荐")
    logger.info("="*60)
    
    manager = SkillManager(skills_dir="skills")
    manager.load_all()
    
    if not manager.skills:
        logger.warning("没有已加载的 Skill，跳过推荐演示")
        return
    
    # 创建集成
    integration = SkillIntegration(manager)
    
    # 推荐任务相关 Skill
    task = "我需要处理一些 JSON 数据并格式化"
    logger.info(f"\n任务: {task}")
    logger.info("\n推荐的 Skill:")
    
    recommendations = integration.suggest_skills_for_task(task, top_k=3)
    for i, rec in enumerate(recommendations, 1):
        logger.info(f"  {i}. {rec['name']} (得分: {rec['score']:.2f})")
        logger.info(f"     描述: {rec['description']}")
        logger.info(f"     成功率: {rec['success_rate']:.1%}")
    
    return integration


def example_4_skill_execution_workflow():
    """例子 4: Skill 执行工作流"""
    logger.info("\n" + "="*60)
    logger.info("例子 4: Skill 执行和工作流")
    logger.info("="*60)
    
    manager = SkillManager(skills_dir="skills")
    manager.load_all()
    
    if not manager.skills:
        logger.warning("没有已加载的 Skill，跳过工作流演示")
        return
    
    integration = SkillIntegration(manager)
    
    # 执行单个 Skill
    logger.info("\n执行单个 Skill:")
    
    str_skill = manager.get_by_name("字符串处理")
    if str_skill:
        result = integration.executor.execute(str_skill.id, text="Hello World", action="upper")
        logger.info(f"  字符串处理执行结果: {result}")
        
        # 查看指标
        logger.info(f"  Skill 指标: {str_skill}")
    
    # 查看执行历史
    logger.info(f"\n执行历史: {len(integration.executor.execution_history)} 条")
    for history in integration.executor.get_execution_history(limit=3):
        logger.info(f"  - {history['skill_name']}: {history['result']['success']}")
    
    # 执行统计
    stats = integration.executor.get_execution_stats()
    logger.info(f"\n执行统计:")
    logger.info(f"  总执行: {stats['total_executions']}")
    logger.info(f"  成功: {stats['successful']}")
    logger.info(f"  失败: {stats['failed']}")
    logger.info(f"  成功率: {stats['success_rate']:.1%}")


def main():
    """运行所有演示"""
    logger.info("\n🚀 Code Skill 系统演示\n")
    
    # 例子 1: 创建 Skill
    skill = example_1_create_basic_skill()
    
    # 例子 2: Skill 管理
    manager = example_2_skill_management()
    
    # 例子 3: Skill 推荐
    integration = example_3_skill_recommendation()
    
    # 例子 4: Skill 执行
    example_4_skill_execution_workflow()
    
    logger.info("\n" + "="*60)
    logger.info("✅ 所有演示完成！")
    logger.info("="*60)
    logger.info("\n🎯 核心特性总结：")
    logger.info("  1. ✅ Skill 定义与实现")
    logger.info("  2. ✅ Skill 管理和持久化")
    logger.info("  3. ✅ 自动推荐引擎")
    logger.info("  4. ✅ 执行和性能跟踪")
    logger.info("  5. ✅ 工作流支持")
    logger.info("\n下一步: 集成到 ReAct 引擎中，让 AI 自动使用 Skill！\n")


if __name__ == "__main__":
    main()
