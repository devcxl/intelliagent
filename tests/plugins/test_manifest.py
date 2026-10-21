"""Manifest 契约测试：字段校验、能力清单唯一性、配置 schema 类型。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.plugins import CapabilityDeclaration, CapabilityKind, Manifest


def build_capability(kind: CapabilityKind, name: str) -> CapabilityDeclaration:
    return CapabilityDeclaration(kind=kind, name=name)


class TestManifestValidation:
    def test_valid_manifest_holds_declared_fields(self) -> None:
        manifest = Manifest(
            name="memory",
            version="1.0.0",
            api_version=1,
            capabilities=(build_capability(CapabilityKind.TOOL, "memory.recall"),),
        )
        assert manifest.name == "memory"
        assert manifest.version == "1.0.0"
        assert manifest.api_version == 1
        assert manifest.capabilities == (build_capability(CapabilityKind.TOOL, "memory.recall"),)
        assert manifest.config_schema is None

    def test_empty_name_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Manifest(
                name="", version="1.0.0", api_version=1, capabilities=(build_capability(CapabilityKind.HOOK, "h"),)
            )

    @pytest.mark.parametrize("bad_name", ["Memory", "mem ory", "-memory", "记忆"])
    def test_invalid_name_pattern_is_rejected(self, bad_name: str) -> None:
        with pytest.raises(ValidationError):
            Manifest(
                name=bad_name,
                version="1.0.0",
                api_version=1,
                capabilities=(build_capability(CapabilityKind.HOOK, "h"),),
            )

    def test_empty_version_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Manifest(
                name="memory", version="", api_version=1, capabilities=(build_capability(CapabilityKind.HOOK, "h"),)
            )

    @pytest.mark.parametrize("bad_api_version", [0, -1])
    def test_non_positive_api_version_is_rejected(self, bad_api_version: int) -> None:
        with pytest.raises(ValidationError):
            Manifest(
                name="memory",
                version="1.0.0",
                api_version=bad_api_version,
                capabilities=(build_capability(CapabilityKind.HOOK, "h"),),
            )

    def test_empty_capability_list_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Manifest(name="memory", version="1.0.0", api_version=1, capabilities=())

    def test_invalid_capability_name_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Manifest(
                name="memory",
                version="1.0.0",
                api_version=1,
                capabilities=(build_capability(CapabilityKind.TOOL, "Bad Name"),),
            )

    def test_duplicate_capability_declaration_is_rejected_with_name(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            Manifest(
                name="memory",
                version="1.0.0",
                api_version=1,
                capabilities=(
                    build_capability(CapabilityKind.TOOL, "memory.recall"),
                    build_capability(CapabilityKind.HOOK, "memory.inject"),
                    build_capability(CapabilityKind.TOOL, "memory.recall"),
                ),
            )
        assert "memory.recall" in str(exc_info.value)

    def test_same_name_under_different_kinds_is_allowed(self) -> None:
        manifest = Manifest(
            name="memory",
            version="1.0.0",
            api_version=1,
            capabilities=(
                build_capability(CapabilityKind.TOOL, "memory.shared"),
                build_capability(CapabilityKind.HOOK, "memory.shared"),
            ),
        )
        assert len(manifest.capabilities) == 2

    def test_config_schema_must_be_pydantic_model(self) -> None:
        with pytest.raises(ValidationError):
            Manifest(
                name="memory",
                version="1.0.0",
                api_version=1,
                capabilities=(build_capability(CapabilityKind.HOOK, "h"),),
                config_schema=int,
            )


class TestCapabilityKind:
    def test_capability_kinds_cover_plugin_vocabulary(self) -> None:
        assert {kind.value for kind in CapabilityKind} == {"tool", "hook", "permission", "storage"}
