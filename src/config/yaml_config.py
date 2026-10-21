#!/usr/bin/env python3
"""intelliagent.yaml 配置读取 — YAML 解析、{env:NAME} 插值、pydantic 校验（ADR 0009）。

旧 intelliagent.json 不再被读取（删除胜过兼容，不做迁移）。
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

DEFAULT_CONFIG_FILENAME = "intelliagent.yaml"

_ENV_PATTERN = re.compile(r"\{env:([^:}]+)(?::([^}]*))?\}")


class ConfigError(Exception):
    """非法配置 — 错误信息指明配置路径（含插件名与字段名）。"""


class WorkspaceConfig(BaseModel):
    """工作区配置。"""

    model_config = ConfigDict(extra="forbid")

    dir: str = "."


class PluginConfig(BaseModel):
    """单个插件条目：启用开关 + 自定义配置。

    config 的 schema 由插件 Manifest 声明，校验属插件宿主（后续票）。
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class IntelliAgentConfig(BaseModel):
    """intelliagent.yaml 顶层配置。"""

    model_config = ConfigDict(extra="forbid")

    model: str | None = None
    max_steps: int | None = Field(default=None, ge=1)  # 预留：运行参数将由引擎消费
    workspace: WorkspaceConfig = Field(default_factory=WorkspaceConfig)
    plugins: dict[str, PluginConfig] = Field(default_factory=dict)


def interpolate_env(value: str) -> str:
    """将字符串中的 {env:NAME} / {env:NAME:default} 替换为环境变量值。

    环境变量不存在且无默认值时抛出 ConfigError。
    """

    def _resolve(match: re.Match[str]) -> str:
        name, default = match.group(1), match.group(2)
        resolved = os.environ.get(name)
        if resolved is not None:
            return resolved
        if default is not None:
            return default
        raise ConfigError(f"环境变量 {name} 未设置，且没有提供默认值")

    return _ENV_PATTERN.sub(_resolve, value)


def deep_interpolate_env(obj: Any, path: str = "") -> Any:
    """递归遍历配置结构，对所有字符串值执行 interpolate_env()。

    path 为当前配置路径（如 plugins.mcp.config.token），用于错误定位。
    """
    if isinstance(obj, str):
        try:
            return interpolate_env(obj)
        except ConfigError as exc:
            raise ConfigError(f"{path or '<root>'}: {exc}") from exc
    if isinstance(obj, dict):
        return {key: deep_interpolate_env(val, f"{path}.{key}" if path else str(key)) for key, val in obj.items()}
    if isinstance(obj, list):
        return [deep_interpolate_env(item, f"{path}[{index}]") for index, item in enumerate(obj)]
    return obj


def load_config(path: str | Path | None = None) -> IntelliAgentConfig:
    """加载并校验 intelliagent.yaml。

    path 为 YAML 文件路径；缺省时读取当前目录的 intelliagent.yaml。
    旧 intelliagent.json 不参与加载，也不作为缺省回落。
    """
    config_path = Path(path) if path is not None else Path(DEFAULT_CONFIG_FILENAME)
    data = deep_interpolate_env(_read_yaml_file(config_path))
    return _validate_config(data, config_path)


def _read_yaml_file(config_path: Path) -> dict[str, Any]:
    """读取 YAML 文件为映射；文件缺失、语法错误或根非映射时抛出 ConfigError。"""
    if not config_path.is_file():
        raise ConfigError(f"配置文件不存在: {config_path}")
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{config_path}: YAML 解析失败: {exc}") from exc
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{config_path}: 顶层必须是映射（mapping）")
    return raw


def _validate_config(data: Any, config_path: Path) -> IntelliAgentConfig:
    """pydantic 校验；每条错误格式化为「配置路径: 原因」以便定位插件与字段。"""
    try:
        return IntelliAgentConfig.model_validate(data)
    except ValidationError as exc:
        details = "; ".join(f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" for error in exc.errors())
        raise ConfigError(f"{config_path}: {details}") from exc
