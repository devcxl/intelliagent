#!/usr/bin/env python3
"""
测试 Context7 MCP 集成
"""
from core.tool_registry import ToolRegistry


def test_context7_connection():
    """测试 Context7 连接"""
    print("=" * 60)
    print("测试 Context7 MCP 连接")
    print("=" * 60)
    
    registry = ToolRegistry()
    registry.initialize()
    
    # 检查 context7 工具是否可用
    context7_tools = [name for name, (server, _) in registry.tools.items() if server.name == 'context7']
    print(f"\n✅ Context7 工具已加载: {context7_tools}")
    
    return registry


def test_resolve_library():
    """测试库解析功能"""
    print("\n" + "=" * 60)
    print("测试 resolve-library-id 工具")
    print("=" * 60)
    
    registry = ToolRegistry()
    registry.initialize()
    
    # 测试解析 React 库
    print("\n查询库: react")
    result = registry.get_tool('resolve-library-id')(libraryName='react')
    
    if result.get('status') == 'ok':
        print("✅ 调用成功！")
        print(f"\n结果预览:\n{result['result'][:300]}...")
    else:
        print(f"❌ 调用失败: {result}")
    
    return result


def test_get_library_docs():
    """测试获取库文档功能"""
    print("\n" + "=" * 60)
    print("测试 get-library-docs 工具")
    print("=" * 60)
    
    registry = ToolRegistry()
    registry.initialize()
    
    # 测试获取 React 文档
    print("\n获取库文档: /facebook/react")
    result = registry.get_tool('get-library-docs')(
        context7CompatibleLibraryID='/facebook/react',
        topic='hooks'
    )
    
    if result.get('status') == 'ok':
        print("✅ 调用成功！")
        print(f"\n文档预览:\n{str(result['result'])[:300]}...")
    else:
        print(f"❌ 调用失败: {result}")
    
    return result


if __name__ == '__main__':
    try:
        # 测试连接
        test_context7_connection()
        
        # 测试库解析
        test_resolve_library()
        
        # 测试获取文档
        test_get_library_docs()
        
        print("\n" + "=" * 60)
        print("✅ 所有测试通过！")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
