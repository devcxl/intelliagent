#!/usr/bin/env python3
"""兼容入口。

长期 CLI 入口已迁移到 `src.cli.main`。
"""

from src.cli.main import IntelliAgent, main


if __name__ == "__main__":
    raise SystemExit(main())
