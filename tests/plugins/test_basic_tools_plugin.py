"""插件契约集成测试：内置基本工具包经 PluginHost 注册，Capability 查询可得 5 个 Tool。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.core.plugin_host import CapabilityKind, PluginHost
from src.plugins.basic_tools import BasicToolsPlugin, ToolSpec, tool_success
from src.plugins.basic_tools.file_tools import edit_tool
from src.utils.path_policy import PathPolicy


def envelope(result: str) -> dict[str, Any]:
    data = json.loads(result)
    assert isinstance(data, dict)
    return data


def loaded_tool_specs(path_policy: PathPolicy | None = None) -> dict[str, ToolSpec]:
    host = PluginHost()
    host.load(BasicToolsPlugin(path_policy=path_policy))
    specs = host.capabilities(CapabilityKind.TOOL)
    assert all(isinstance(spec, ToolSpec) for spec in specs.values())
    return dict(specs)  # type: ignore[arg-type]


class TestBasicToolsPluginContract:
    def test_plugin_registers_five_tool_capabilities(self) -> None:
        specs = loaded_tool_specs()

        assert set(specs) == {"read", "write", "bash", "edit", "grep"}
        for name, spec in specs.items():
            assert spec.name == name

    def test_manifest_matches_registered_capabilities(self) -> None:
        plugin = BasicToolsPlugin()

        declared = {(item.kind, item.name) for item in plugin.manifest.capabilities}

        assert declared == {(CapabilityKind.TOOL, name) for name in ("read", "write", "bash", "edit", "grep")}
        assert plugin.manifest.name == "basic-tools"
        assert plugin.manifest.api_version == 1

    async def test_tool_is_invocable_through_host(self, tmp_path: Path) -> None:
        specs = loaded_tool_specs(PathPolicy(workspace=tmp_path))
        target = tmp_path / "hello.txt"
        target.write_text("hello\n", encoding="utf-8")

        data = envelope(await specs["read"].run(path=str(target)))

        assert data["status"] == "ok"
        assert data["content"] == "hello"

    def test_parameters_are_native_json_schema(self) -> None:
        specs = loaded_tool_specs()

        read_params = specs["read"].parameters
        assert read_params["type"] == "object"
        assert set(read_params["properties"]) == {"path", "offset", "limit"}
        assert read_params["required"] == ["path"]

        assert specs["edit"].parameters["properties"]["replaceAll"]["type"] == "boolean"
        assert specs["bash"].parameters["required"] == ["command"]


class TestToolSpecRun:
    async def test_bad_arguments_converge_to_error_envelope(self) -> None:
        data = envelope(await edit_tool().run(bogus_argument=1))

        assert data["status"] == "error"
        assert data["code"] == "INVALID_ARGUMENT"

    async def test_unexpected_exception_converges_to_error_envelope(self) -> None:
        async def explode(value: str) -> str:
            raise ValueError("boom")

        spec = ToolSpec(name="fake", description="test", parameters={"type": "object"}, handler=explode)

        data = envelope(await spec.run(value="x"))

        assert data["status"] == "error"
        assert data["code"] == "EXECUTION_ERROR"
        assert "boom" in data["error"]

    async def test_success_envelope_keeps_status_ok(self) -> None:
        async def fine(value: str) -> str:
            return tool_success(value=value)

        spec = ToolSpec(name="fake", description="test", parameters={"type": "object"}, handler=fine)

        data = envelope(await spec.run(value="x"))
        assert data == {"status": "ok", "value": "x"}
