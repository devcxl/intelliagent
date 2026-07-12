"""IntelliAgent GUI 入口。

使用 qasync 桥接 asyncio 与 Qt 事件循环。
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

from PyQt5.QtWidgets import QApplication
from qasync import QEventLoop

from src.config.unified_config import UnifiedConfig
from src.db.repositories.conversation import ConversationRepository
from src.db.repositories.message import MessageRepository
from src.gui.main_window import MainWindow
from src.gui.services.event_bridge import EventBridge
from src.gui.styles.theme import ThemeManager
from src.gui.widgets.permission_dialog import PermissionDialog
from src.runtime.agent_runtime import AgentRuntime


class _GuiPermissionCallback:
    """GUI 权限回调 — 桥接 PermissionEngine → PermissionDialog。"""

    async def on_prompt(self, tool_name: str, args: dict[str, Any], reason: str) -> bool:
        return await PermissionDialog.on_prompt(tool_name, args, reason)


async def _async_main(app: QApplication) -> None:
    """启动 GUI 应用（异步初始化 + 事件循环桥接）。"""
    # 1. Load configuration
    config = UnifiedConfig.load()

    # 2. Initialize QFluentWidgets styling
    ThemeManager.setup(app)

    # 3. Create AgentRuntime with GUI permission callback
    runtime = AgentRuntime(
        config,
        permission_callback_factory=lambda: _GuiPermissionCallback(),
    )
    await runtime.initialize()

    # 4. Create repositories (share a session from the runtime's factory)
    session_factory = runtime.session_factory
    session = session_factory()
    conv_repo = ConversationRepository(session)
    msg_repo = MessageRepository(session)

    # 5. Create EventBridge
    bridge = EventBridge(runtime)

    # 6. Apply theme BEFORE showing window
    ThemeManager.apply_light(app)

    # 7. Create and show MainWindow
    window = MainWindow(bridge, conv_repo, msg_repo)
    window.show()

    # 8. 后台清理任务 — 窗口关闭时由 aboutToQuit 触发
    async def _shutdown() -> None:
        await session.close()
        await runtime.shutdown()

    app.aboutToQuit.connect(lambda: asyncio.ensure_future(_shutdown()))


def _fix_input_method() -> None:
    """修复 Linux 下 fcitx5/ibus 输入法在 PyQt5 虚拟环境中不工作的问题。

    虚拟环境 PyQt5 自带的 platforminputcontexts 目录不含 fcitx5 插件。
    把系统插件软链接过去，一次执行，永久生效。
    """
    if sys.platform != "linux":
        return

    import PyQt5

    source = "/usr/lib/qt/plugins/platforminputcontexts/libfcitx5platforminputcontextplugin.so"
    if not os.path.exists(source):
        return

    qt5_dir = os.path.join(os.path.dirname(PyQt5.__file__), "Qt5", "plugins", "platforminputcontexts")
    dest = os.path.join(qt5_dir, "libfcitx5platforminputcontextplugin.so")
    if os.path.exists(dest):
        return

    try:
        os.symlink(source, dest)
        print(f"[IME] Symlinked {source} → {dest}")  # noqa: T201 — startup diagnostic
    except OSError:
        print(  # noqa: T201
            f"[IME] 请手动执行:\n  ln -s {source} {dest}"
        )


def main() -> None:
    """同步入口 — 创建 QApplication + qasync 事件循环。"""
    _fix_input_method()

    app = QApplication(sys.argv)
    app.setApplicationName("IntelliAgent")

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    asyncio.ensure_future(_async_main(app))
    loop.run_forever()
    loop.close()


if __name__ == "__main__":
    main()
