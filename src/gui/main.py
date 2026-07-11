"""IntelliAgent GUI 入口。

独立入口，不依赖 CLI 模块。使用 qasync 桥接 asyncio 与 Qt 事件循环。
"""

import sys

from qasync import QApplication


def main() -> None:
    """启动 GUI 应用。"""
    app = QApplication(sys.argv)
    app.setApplicationName("IntelliAgent")
    app.setApplicationDisplayName("IntelliAgent")

    # 占位 — MainWindow 将在后续任务中实现
    from PyQt5.QtWidgets import QLabel
    label = QLabel("IntelliAgent GUI")
    label.show()

    app.exec()


if __name__ == "__main__":
    main()
