"""IntelliAgent GUI 入口。

使用 qasync 桥接 asyncio 与 Qt 事件循环。
"""

import sys

from qasync import QApplication
from qasync import run as qasync_run

from src.config.unified_config import UnifiedConfig
from src.db.repositories.conversation import ConversationRepository
from src.db.repositories.message import MessageRepository
from src.gui.main_window import MainWindow
from src.gui.services.event_bridge import EventBridge
from src.gui.styles.theme import ThemeManager
from src.runtime.agent_runtime import AgentRuntime


async def main() -> None:
    """启动 GUI 应用。"""
    # 1. Create QApplication with qasync event loop integration
    app = QApplication(sys.argv)
    app.setApplicationName("IntelliAgent")

    # 2. Load configuration
    config = UnifiedConfig.load()

    # 3. Create AgentRuntime and initialize (DB + MCP)
    runtime = AgentRuntime(config)
    await runtime.initialize()

    # 4. Create repositories (share a session from the runtime's factory)
    session_factory = runtime.session_factory
    session = session_factory()
    conv_repo = ConversationRepository(session)
    msg_repo = MessageRepository(session)

    # 5. Create EventBridge
    bridge = EventBridge(runtime)

    # 6. Create and show MainWindow
    window = MainWindow(bridge, conv_repo, msg_repo)
    window.show()

    # 7. Apply initial theme (light)
    ThemeManager.apply_light(app)

    # 8. Enter Qt event loop (qasync-integrated)
    app.exec()

    # 9. Cleanup
    await session.close()
    await runtime.shutdown()


if __name__ == "__main__":
    qasync_run(main())
