#!/usr/bin/env python3
"""
工具系统验证 - 语法和结构检查

检查 mcp_server.py 中的工具是否正确定义，不需要 mcp 依赖
"""
import sys
import os
import ast
import json
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logger import logger


class ToolValidation:
    """工具验证类"""
    
    def __init__(self):
        self.mcp_server_path = Path(__file__).parent.parent / "mcp_server.py"
        self.issues = []
        self.passed_checks = 0
        self.failed_checks = 0
    
    def check_mcp_server_exists(self):
        """检查 mcp_server.py 文件是否存在"""
        logger.info("\n🧪 检查 mcp_server.py 文件...")
        if self.mcp_server_path.exists():
            logger.info(f"✅ 文件存在: {self.mcp_server_path}")
            self.passed_checks += 1
            return True
        else:
            logger.error(f"❌ 文件不存在: {self.mcp_server_path}")
            self.failed_checks += 1
            return False
    
    def check_syntax(self):
        """检查 Python 语法"""
        logger.info("\n🧪 检查 Python 语法...")
        try:
            with open(self.mcp_server_path, 'r', encoding='utf-8') as f:
                code = f.read()
            
            ast.parse(code)
            logger.info("✅ 语法检查通过")
            self.passed_checks += 1
            return True
        except SyntaxError as e:
            logger.error(f"❌ 语法错误: {e}")
            self.failed_checks += 1
            return False
    
    def extract_tool_definitions(self):
        """提取工具定义"""
        logger.info("\n🧪 提取工具定义...")
        try:
            with open(self.mcp_server_path, 'r', encoding='utf-8') as f:
                code = f.read()
            
            tree = ast.parse(code)
            
            tools = {}
            for node in ast.walk(tree):
                if isinstance(node, ast.AsyncFunctionDef):
                    # 检查是否有装饰器
                    for decorator in node.decorator_list:
                        if (isinstance(decorator, ast.Attribute) and
                            decorator.attr == "tool"):
                            tools[node.name] = {
                                "type": "async",
                                "args": [arg.arg for arg in node.args.args],
                                "docstring": ast.get_docstring(node)
                            }
            
            return tools
        except Exception as e:
            logger.error(f"❌ 提取失败: {e}")
            self.failed_checks += 1
            return {}
    
    def validate_tools(self, tools: dict):
        """验证工具定义"""
        logger.info(f"\n🧪 验证工具定义 ({len(tools)} 个)...")
        
        expected_tools = ["run_shell", "read_file", "write_file", "list_dir", "delete_file", "file_exists"]
        
        # 检查所有预期的工具是否存在
        found_tools = set(tools.keys())
        expected_set = set(expected_tools)
        
        missing = expected_set - found_tools
        if missing:
            logger.warning(f"⚠️ 缺失工具: {missing}")
        
        extra = found_tools - expected_set
        if extra:
            logger.info(f"ℹ️ 额外工具: {extra}")
        
        # 验证每个工具
        for tool_name, tool_info in tools.items():
            logger.info(f"\n  📝 工具: {tool_name}")
            
            # 检查文档字符串
            if tool_info.get("docstring"):
                logger.info(f"     ✅ 有文档字符串")
                self.passed_checks += 1
            else:
                logger.warning(f"     ⚠️ 缺少文档字符串")
                self.failed_checks += 1
            
            # 检查参数
            args = tool_info.get("args", [])
            if args:
                logger.info(f"     ✅ 参数: {', '.join(args)}")
                self.passed_checks += 1
            else:
                logger.warning(f"     ⚠️ 没有参数")
            
            # 基本验证
            if tool_info.get("type") == "async":
                logger.info(f"     ✅ 异步函数")
                self.passed_checks += 1
            else:
                logger.warning(f"     ⚠️ 非异步函数")
                self.failed_checks += 1
    
    def validate_response_format(self):
        """验证响应格式函数"""
        logger.info("\n🧪 检查响应格式函数...")
        try:
            with open(self.mcp_server_path, 'r', encoding='utf-8') as f:
                code = f.read()
            
            # 检查关键函数是否存在
            required_functions = ["success_response", "error_response"]
            
            for func_name in required_functions:
                if f"def {func_name}" in code:
                    logger.info(f"✅ 函数存在: {func_name}")
                    self.passed_checks += 1
                else:
                    logger.warning(f"⚠️ 函数缺失: {func_name}")
                    self.failed_checks += 1
        except Exception as e:
            logger.error(f"❌ 检查失败: {e}")
            self.failed_checks += 1
    
    def validate_constants(self):
        """验证配置常量"""
        logger.info("\n🧪 检查配置常量...")
        try:
            with open(self.mcp_server_path, 'r', encoding='utf-8') as f:
                code = f.read()
            
            tree = ast.parse(code)
            
            constants = {}
            for node in tree.body:
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            constants[target.id] = True
            
            # 检查必要的常量
            required_constants = [
                "SHELL_COMMAND_TIMEOUT",
                "FILE_READ_MAX_SIZE",
                "FILE_WRITE_MAX_SIZE",
                "DIR_LIST_MAX_ITEMS"
            ]
            
            for const_name in required_constants:
                if const_name in constants:
                    logger.info(f"✅ 常量存在: {const_name}")
                    self.passed_checks += 1
                else:
                    logger.warning(f"⚠️ 常量缺失: {const_name}")
                    self.failed_checks += 1
        except Exception as e:
            logger.error(f"❌ 检查失败: {e}")
            self.failed_checks += 1
    
    def check_documentation(self):
        """检查文档文件"""
        logger.info("\n🧪 检查文档文件...")
        
        docs_to_check = [
            ("docs/TOOLS.md", "工具文档"),
            ("docs/TOOL_INTEGRATION.md", "集成指南"),
        ]
        
        for doc_path, doc_name in docs_to_check:
            full_path = Path(__file__).parent.parent / doc_path
            if full_path.exists():
                size = full_path.stat().st_size
                logger.info(f"✅ {doc_name}存在 ({size} 字节)")
                self.passed_checks += 1
            else:
                logger.warning(f"⚠️ {doc_name}缺失")
                self.failed_checks += 1
    
    def check_readme_updated(self):
        """检查 README 是否更新"""
        logger.info("\n🧪 检查 README 更新...")
        
        readme_path = Path(__file__).parent.parent / "README.md"
        if readme_path.exists():
            content = readme_path.read_text()
            
            # 检查关键内容
            checks = [
                ("Tools - 工具系统" in content or "工具系统" in content, "Tools 章节"),
                ("list_dir" in content, "list_dir 工具"),
                ("delete_file" in content, "delete_file 工具"),
                ("file_exists" in content, "file_exists 工具"),
                ("docs/TOOLS.md" in content, "工具文档链接"),
                ("docs/TOOL_INTEGRATION.md" in content or "MCP 集成" in content, "集成指南链接"),
            ]
            
            for check, name in checks:
                if check:
                    logger.info(f"✅ {name}")
                    self.passed_checks += 1
                else:
                    logger.warning(f"⚠️ {name}")
                    self.failed_checks += 1
        else:
            logger.error("❌ README.md 不存在")
            self.failed_checks += 1
    
    def run_validation(self):
        """运行所有验证"""
        logger.info("=" * 70)
        logger.info("🔍 开始工具系统验证")
        logger.info("=" * 70)
        
        # 基础检查
        if not self.check_mcp_server_exists():
            logger.error("文件不存在，无法继续")
            return False
        
        if not self.check_syntax():
            logger.error("语法错误，无法继续")
            return False
        
        # 工具验证
        tools = self.extract_tool_definitions()
        if tools:
            logger.info(f"\n✅ 找到 {len(tools)} 个工具: {', '.join(tools.keys())}")
            self.validate_tools(tools)
        else:
            logger.warning("⚠️ 没有找到任何工具定义")
        
        # 响应格式验证
        self.validate_response_format()
        
        # 常量验证
        self.validate_constants()
        
        # 文档验证
        self.check_documentation()
        self.check_readme_updated()
        
        # 输出总结
        logger.info("\n" + "=" * 70)
        logger.info("📊 验证总结")
        logger.info("=" * 70)
        logger.info(f"✅ 通过: {self.passed_checks}")
        logger.info(f"❌ 失败: {self.failed_checks}")
        
        if self.failed_checks == 0:
            logger.info("🎉 所有检查通过！")
            logger.info("=" * 70)
            return True
        else:
            logger.warning(f"⚠️ 有 {self.failed_checks} 个检查未通过")
            logger.info("=" * 70)
            return False


def main():
    """主函数"""
    validator = ToolValidation()
    success = validator.run_validation()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
