#!/usr/bin/env python3
"""
测试 MCP Prompts 功能
"""
from core.tool_registry import ToolRegistry


def test_list_prompts():
    """测试列出所有 prompts"""
    print("=" * 60)
    print("测试列出所有 Prompts")
    print("=" * 60)
    
    registry = ToolRegistry()
    registry.initialize()
    
    prompts = registry.list_prompts()
    print(f"\n✅ 发现 {len(prompts)} 个 prompts:")
    for prompt_name in prompts:
        print(f"  - {prompt_name}")
    
    return prompts


def test_describe_prompts():
    """测试描述所有 prompts"""
    print("\n" + "=" * 60)
    print("测试描述 Prompts")
    print("=" * 60)
    
    registry = ToolRegistry()
    registry.initialize()
    
    description = registry.describe_prompts()
    if description:
        print(f"\n{description}")
    else:
        print("\n没有可用的 prompts")


def test_get_prompt():
    """测试获取特定 prompt"""
    print("\n" + "=" * 60)
    print("测试获取特定 Prompt")
    print("=" * 60)
    
    registry = ToolRegistry()
    registry.initialize()
    
    prompts = registry.list_prompts()
    
    if not prompts:
        print("\n⚠️ 没有可用的 prompts 进行测试")
        return None
    
    # 测试第一个 prompt
    prompt_name = prompts[0]
    print(f"\n获取 prompt: {prompt_name}")
    
    try:
        result = registry.get_prompt(prompt_name)
        
        if result.get('status') == 'ok':
            print("✅ 获取成功！")
            if result.get('description'):
                print(f"\n描述: {result['description']}")
            
            print(f"\n消息数量: {len(result.get('messages', []))}")
            for i, msg in enumerate(result.get('messages', []), 1):
                print(f"\n消息 {i}:")
                print(f"  角色: {msg['role']}")
                content_str = str(msg['content'])
                print(f"  内容预览: {content_str[:200]}...")
        else:
            print(f"❌ 获取失败: {result}")
            
        return result
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == '__main__':
    try:
        # 测试列出 prompts
        test_list_prompts()
        
        # 测试描述 prompts
        test_describe_prompts()
        
        # 测试获取 prompt
        test_get_prompt()
        
        print("\n" + "=" * 60)
        print("✅ Prompts 测试完成！")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
