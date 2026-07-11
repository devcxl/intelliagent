"""IntelliAgent GUI 入口。

使用 qasync 桥接 asyncio 与 Qt 事件循环。
"""

from __future__ import annotations

import asyncio
import sys

from PyQt5.QtWidgets import QApplication
from qasync import QEventLoop

from src.config.unified_config import UnifiedConfig
from src.db.repositories.conversation import ConversationRepository
from src.db.repositories.message import MessageRepository
from src.gui.main_window import MainWindow
from src.gui.services.event_bridge import EventBridge
from src.gui.styles.theme import ThemeManager
from src.runtime.agent_runtime import AgentRuntime


async def _async_main(app: QApplication) -> None:
    """启动 GUI 应用（异步初始化 + 事件循环桥接）。"""
    # 1. Load configuration
    config = UnifiedConfig.load()

    # 2. Create AgentRuntime and initialize (DB + MCP)
    runtime = AgentRuntime(config)
    await runtime.initialize()

    # 3. Create repositories (share a session from the runtime's factory)
    session_factory = runtime.session_factory
    session = session_factory()
    conv_repo = ConversationRepository(session)
    msg_repo = MessageRepository(session)

    # 4. Create EventBridge
    bridge = EventBridge(runtime)

    # 5. Create and show MainWindow
    window = MainWindow(bridge, conv_repo, msg_repo)
    window.show()

    # 6. Apply initial theme (light)
    ThemeManager.apply_light(app)

    # 7. Wait for the Qt main window to close
    close_event = asyncio.Event()
    app.aboutToQuit.connect(close_event.set)
    await close_event.wait()

    # 8. Cleanup
    await session.close()
    await runtime.shutdown()


def main() -> None:
    """同步入口 — 创建 QApplication + qasync 事件循环。"""
    app = QApplication(sys.argv)
    app.setApplicationName("IntelliAgent")

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(_async_main(app))
    finally:
        loop.close()


if __name__ == "__main__":
    main()
