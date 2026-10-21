"""内置基本工具插件（Built-in Plugin）：read / write / bash / edit / grep 五个 Tool Capability。"""

from src.plugins.basic_tools.bash_tool import bash_tool
from src.plugins.basic_tools.file_tools import edit_tool, read_tool, write_tool
from src.plugins.basic_tools.grep_tool import grep_tool
from src.plugins.basic_tools.plugin import BasicToolsPlugin
from src.plugins.basic_tools.result import tool_error, tool_success
from src.plugins.basic_tools.tool import ToolSpec

__all__ = [
    "BasicToolsPlugin",
    "ToolSpec",
    "bash_tool",
    "edit_tool",
    "grep_tool",
    "read_tool",
    "tool_error",
    "tool_success",
    "write_tool",
]
