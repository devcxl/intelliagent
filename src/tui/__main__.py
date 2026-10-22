"""python -m src.tui 免安装入口（README「TUI（交互式）」）。"""

from __future__ import annotations

import sys

from src.config.yaml_config import ConfigError
from src.core.plugin_host import PluginError
from src.runtime.plugin_assembly import redact_secrets
from src.tui.assembly import build_app

EXIT_STARTUP_FAILURE = 2


def main() -> int:
    """组装并运行 TUI；同步/异步启动错误由入口或应用脱敏后以 2 退出。"""
    try:
        app = build_app()
    except (ConfigError, PluginError, ValueError) as exc:
        sys.stderr.write(f"error: {redact_secrets(str(exc))}\n")
        return EXIT_STARTUP_FAILURE
    app.run()
    return getattr(app, "return_code", 0)


if __name__ == "__main__":
    raise SystemExit(main())
