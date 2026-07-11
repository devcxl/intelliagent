"""ThemeManager — QFluentWidgets 浅色/深色主题切换。"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication
from qfluentwidgets import Theme, setTheme


class ThemeManager:
    """封装 QFluentWidgets 主题切换。

    Usage::

        app = QApplication(sys.argv)
        ThemeManager.setup(app)
        ThemeManager.apply_light(app)
    """

    @staticmethod
    def setup(app: QApplication) -> None:
        """Initialize QFluentWidgets styling on the application."""
        # Enable high DPI scaling (required by QFluentWidgets)
        app.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings)

    @staticmethod
    def apply_light(app: QApplication) -> None:
        setTheme(Theme.LIGHT)

    @staticmethod
    def apply_dark(app: QApplication) -> None:
        setTheme(Theme.DARK)
