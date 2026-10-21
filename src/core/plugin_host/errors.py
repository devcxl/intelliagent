"""插件宿主错误层次：所有错误携带插件名与能力名，可直接诊断。"""

from __future__ import annotations


class PluginError(Exception):
    """插件相关错误的基类。"""


class ApiVersionError(PluginError):
    """插件声明的 api_version 不在宿主支持区间内，宿主拒绝加载。"""


class PluginConfigError(PluginError):
    """插件配置未通过其 Manifest config_schema 校验。"""


class CapabilityConflictError(PluginError):
    """能力名冲突：同一 (kind, name) 只能由一个插件注册。"""


class PluginLoadError(PluginError):
    """插件加载失败：Manifest 缺失、Entry Point 解析失败或注册与 Manifest 不一致。"""
