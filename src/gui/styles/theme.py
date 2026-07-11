"""ThemeManager — 基于 MiniMax 设计系统的主题管理。"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication
from qfluentwidgets import Theme, setTheme

from src.gui.styles.minimax_qss import generate_stylesheet


class ThemeManager:
    """封装 MiniMax 设计系统的主题切换。

    Usage::

        app = QApplication(sys.argv)
        ThemeManager.setup(app)
        ThemeManager.apply_light(app)
    """

    _applied = False

    @staticmethod
    def setup(app: QApplication) -> None:
        """Initialize application-level styling."""
        app.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings)

    @staticmethod
    def apply_light(app: QApplication) -> None:
        """Apply light theme with MiniMax design system."""
        setTheme(Theme.LIGHT)
        qss = generate_stylesheet()
        app.setStyleSheet(qss)

    @staticmethod
    def apply_dark(app: QApplication) -> None:
        """Apply dark theme (placeholder — MiniMax design only specifies light)."""
        setTheme(Theme.DARK)
        qss = generate_stylesheet()
        app.setStyleSheet(qss)
