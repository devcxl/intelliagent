#!/usr/bin/env python3
"""{env:NAME} / {env:NAME:default} 环境变量插值引擎。"""

from __future__ import annotations

import os
import re
from typing import Any

_ENV_PATTERN = re.compile(r"\{env:([^:}]+)(?::([^}]*))?\}")


def interpolate(value: str) -> str:
    """将字符串中的 {env:NAME} / {env:NAME:default} 替换为环境变量值。

    环境变量不存在且无默认值时抛出 ValueError。
    """

    def _replace(m: re.Match) -> str:
        var = m.group(1)
        default = m.group(2)
        val = os.environ.get(var)
        if val is not None:
            return val
        if default is not None:
            return default
        raise ValueError(f"环境变量 {var} 未设置，且没有提供默认值")

    return _ENV_PATTERN.sub(_replace, value)


def deep_interpolate(obj: Any) -> Any:
    """递归遍历 JSON 结构，对所有字符串值执行 interpolate()。"""
    if isinstance(obj, str):
        return interpolate(obj)
    if isinstance(obj, dict):
        return {k: deep_interpolate(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [deep_interpolate(v) for v in obj]
    return obj
