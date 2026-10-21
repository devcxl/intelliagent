"""Capability 注册表契约测试：注册、查询、能力名冲突拒绝。"""

from __future__ import annotations

import pytest

from src.core.plugin_host import CapabilityConflictError, CapabilityKind, CapabilityRegistry


class TestCapabilityRegistry:
    def test_registered_capability_can_be_queried(self) -> None:
        registry = CapabilityRegistry()
        provider = object()

        registry.register("core-tools", CapabilityKind.TOOL, "read", provider)

        assert registry.get(CapabilityKind.TOOL, "read") is provider

    def test_querying_missing_capability_returns_none(self) -> None:
        registry = CapabilityRegistry()
        assert registry.get(CapabilityKind.TOOL, "missing") is None

    def test_get_all_returns_capabilities_of_requested_kind_only(self) -> None:
        registry = CapabilityRegistry()
        tool_provider = object()
        hook_provider = object()

        registry.register("core-tools", CapabilityKind.TOOL, "read", tool_provider)
        registry.register("memory", CapabilityKind.HOOK, "inject", hook_provider)

        assert registry.get_all(CapabilityKind.TOOL) == {"read": tool_provider}
        assert registry.get_all(CapabilityKind.HOOK) == {"inject": hook_provider}

    def test_same_capability_name_under_different_kind_is_not_a_conflict(self) -> None:
        registry = CapabilityRegistry()
        tool_provider = object()
        hook_provider = object()

        registry.register("core-tools", CapabilityKind.TOOL, "shared", tool_provider)
        registry.register("memory", CapabilityKind.HOOK, "shared", hook_provider)

        assert registry.get(CapabilityKind.TOOL, "shared") is tool_provider
        assert registry.get(CapabilityKind.HOOK, "shared") is hook_provider

    def test_conflicting_capability_name_is_rejected_and_names_both_plugins(self) -> None:
        registry = CapabilityRegistry()
        registry.register("core-tools", CapabilityKind.TOOL, "read", object())

        with pytest.raises(CapabilityConflictError) as exc_info:
            registry.register("other-tools", CapabilityKind.TOOL, "read", object())

        message = str(exc_info.value)
        assert "core-tools" in message
        assert "other-tools" in message
        assert "read" in message

    def test_conflict_keeps_original_provider(self) -> None:
        registry = CapabilityRegistry()
        original = object()
        registry.register("core-tools", CapabilityKind.TOOL, "read", original)

        with pytest.raises(CapabilityConflictError):
            registry.register("other-tools", CapabilityKind.TOOL, "read", object())

        assert registry.get(CapabilityKind.TOOL, "read") is original
