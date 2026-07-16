"""Discord 风格深色主题 QSS 样式表。

结构:
  1. 设计令牌  — 颜色 / 字号 / 间距 / 圆角 / 尺度
  2. 通用样式  — 全局字体 / 选中色
  3. 组件样式  — 按功能域分组
"""

from __future__ import annotations

# ============================================================================
# 1. Discord 深色主题令牌
# ============================================================================

# 背景层次（从深到浅）
_BG = {
    "sidebar": "#2b2d31",  # 侧边栏 — 最深
    "chat": "#313338",  # 聊天区
    "chat_hover": "#2e3035",  # 消息 hover
    "input_area": "#313338",  # 输入区（与聊天区一致）
    "card": "#2b2d31",  # 卡片/代码块
    "input_field": "#383a40",  # 输入框填充
    "dialog": "#313338",  # 对话框
    "surface": "#2b2d31",  # 通用面板
    "surface_hover": "#35373c",  # hover 面板
}

# 文字层次
_TX = {
    "primary": "#f2f3f5",  # 正文
    "secondary": "#b5bac1",  # 次要文字
    "muted": "#949ba4",  # 辅助文字
    "inverse": "#ffffff",  # 反色（深底上的白字）
}

# 边框
_BD = {
    "strong": "#3f4147",  # 明显边框
    "subtle": "#2e3035",  # 弱边框
    "input": "#1e1f22",  # 输入框边框
}

# 品牌色
_ACCENT = "#5865f2"  # Discord blurple
_ACCENT_HOVER = "#4752c4"

# 状态色
_GREEN = "#23a55a"
_RED = "#f23f43"
_YELLOW = "#f0b232"

# 排版
_TEXT = {
    "caption": "12px",
    "body_sm": "13px",
    "body": "14px",
    "body_lg": "15px",
    "heading": "16px",
}

# 间距
_SPACE = {
    "xs": "4px",
    "sm": "8px",
    "md": "12px",
    "lg": "16px",
    "xl": "20px",
    "2xl": "24px",
}

# 圆角
_RADIUS = {
    "sm": "4px",
    "md": "6px",
    "lg": "8px",
    "xl": "12px",
    "pill": "999px",
}

# 尺度
_SIZE = {
    "btn": "36px",
    "input": "44px",
    "scrollbar": "6px",
    "sidebar": "240px",
    "status": "28px",
}

_FONT = '"gg sans", "Noto Sans", "Helvetica Neue", "Helvetica", "Arial", sans-serif'
_MONO = '"JetBrains Mono", "SF Mono", "Menlo", "Consolas", monospace'


def _qss(*rules: str) -> str:
    return "\n\n".join(rules)


# ============================================================================
# 2. 全局
# ============================================================================


def _global_styles() -> str:
    return f"""
    /* ── 字体 ── */
    QMainWindow, QDialog, QFrame, QLabel, QPushButton,
    QLineEdit, QTextEdit, QListWidget, QMenu, QCheckBox {{
        font-family: {_FONT};
        color: {_TX["primary"]};
    }}

    /* ── 全局背景 ── */
    QMainWindow {{
        background-color: {_BG["chat"]};
    }}

    /* ── 选中色 ── */
    QTextEdit, QLineEdit {{
        selection-background-color: {_ACCENT};
        selection-color: {_TX["inverse"]};
    }}
    """


# ============================================================================
# 3. 组件
# ============================================================================


def _session_list_styles() -> str:
    return f"""
    /* ── 侧边栏 ── */
    QWidget#sidebarPanel {{
        background-color: {_BG["sidebar"]};
        border-right: 1px solid {_BD["subtle"]};
    }}

    QListWidget#sessionList {{
        background-color: transparent;
        border: none;
        outline: none;
        padding: {_SPACE["sm"]} {_SPACE["sm"]} {_SPACE["xs"]} {_SPACE["sm"]};
    }}
    QListWidget#sessionList::item {{
        background-color: transparent;
        color: {_TX["secondary"]};
        font-size: {_TEXT["body"]};
        font-weight: 400;
        padding: {_SPACE["sm"]} {_SPACE["md"]};
        margin: 1px {_SPACE["xs"]};
        border-radius: {_RADIUS["sm"]};
        border-left: 3px solid transparent;
    }}
    QListWidget#sessionList::item:selected {{
        background-color: {_BG["surface_hover"]};
        color: {_TX["primary"]};
        font-weight: 500;
        border-left: 3px solid {_ACCENT};
    }}
    QListWidget#sessionList::item:hover:!selected {{
        background-color: {_BG["chat_hover"]};
        color: {_TX["primary"]};
    }}

    /* 新建会话按钮 */
    QPushButton#newSessionBtn {{
        background-color: {_ACCENT};
        color: {_TX["inverse"]};
        font-size: {_TEXT["body"]};
        font-weight: 600;
        border: none;
        border-radius: {_RADIUS["sm"]};
        padding: {_SPACE["sm"]} {_SPACE["lg"]};
        min-height: {_SIZE["btn"]};
        margin: 0 {_SPACE["sm"]} {_SPACE["sm"]} {_SPACE["sm"]};
    }}
    QPushButton#newSessionBtn:hover {{
        background-color: {_ACCENT_HOVER};
    }}
    QPushButton#newSessionBtn:disabled {{
        background-color: {_BD["strong"]};
        color: {_TX["muted"]};
    }}

    /* 设置按钮 */
    QPushButton#settingsBtn {{
        background-color: transparent;
        color: {_TX["muted"]};
        font-size: {_TEXT["body_sm"]};
        font-weight: 400;
        border: none;
        border-top: 1px solid {_BD["subtle"]};
        border-radius: 0;
        padding: {_SPACE["sm"]} {_SPACE["md"]};
        text-align: left;
    }}
    QPushButton#settingsBtn:hover {{
        background-color: {_BG["surface_hover"]};
        color: {_TX["primary"]};
    }}
    """


def _chat_view_styles() -> str:
    return f"""
    /* ── 聊天区 ── */
    QScrollArea#chatView {{
        background-color: {_BG["chat"]};
        border: none;
    }}
    QScrollArea#chatView QScrollBar:vertical {{
        background: transparent;
        width: {_SIZE["scrollbar"]};
        margin: {_SPACE["xs"]};
    }}
    QScrollArea#chatView QScrollBar::handle:vertical {{
        background: {_BG["surface_hover"]};
        border-radius: {_RADIUS["sm"]};
        min-height: 32px;
    }}
    QScrollArea#chatView QScrollBar::handle:vertical:hover {{
        background: {_BD["strong"]};
    }}
    QScrollArea#chatView QScrollBar::add-line:vertical,
    QScrollArea#chatView QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    """


def _input_bar_styles() -> str:
    return f"""
    /* ── 输入区 ── */
    QWidget#inputPanel {{
        background-color: {_BG["input_area"]};
        border-top: 1px solid {_BD["subtle"]};
    }}

    QLineEdit#msgInput {{
        background-color: {_BG["input_field"]};
        color: {_TX["primary"]};
        font-size: {_TEXT["body_lg"]};
        font-weight: 400;
        border: 1px solid {_BD["input"]};
        border-radius: {_RADIUS["md"]};
        padding: {_SPACE["sm"]} {_SPACE["lg"]};
        min-height: {_SIZE["input"]};
    }}
    QLineEdit#msgInput:focus {{
        border-color: {_ACCENT};
    }}
    QLineEdit#msgInput:disabled {{
        background-color: {_BG["card"]};
        color: {_TX["muted"]};
    }}

    QPushButton#sendBtn {{
        background-color: {_ACCENT};
        color: {_TX["inverse"]};
        font-size: {_TEXT["body"]};
        font-weight: 600;
        border: none;
        border-radius: {_RADIUS["sm"]};
        padding: {_SPACE["sm"]} {_SPACE["xl"]};
        min-height: {_SIZE["input"]};
    }}
    QPushButton#sendBtn:hover {{
        background-color: {_ACCENT_HOVER};
    }}
    QPushButton#sendBtn:disabled {{
        background-color: {_BG["surface_hover"]};
        color: {_TX["muted"]};
    }}
    """


def _message_bubble_styles() -> str:
    return f"""
    /* ── 气泡 ── */

    /* 用户 */
    QFrame#userBubble {{
        background-color: {_ACCENT};
        border-radius: {_RADIUS["xl"]};
        padding: {_SPACE["sm"]} {_SPACE["md"]};
    }}
    QFrame#userBubble QTextEdit {{
        color: {_TX["inverse"]};
        font-size: {_TEXT["body_lg"]};
        font-weight: 400;
        background: transparent;
        border: none;
    }}

    /* AI 助手 */
    QFrame#answerBubble {{
        background-color: {_BG["card"]};
        border-radius: {_RADIUS["xl"]};
        padding: {_SPACE["sm"]} {_SPACE["md"]};
        margin: 2px 0;
    }}
    QFrame#answerBubble QTextEdit {{
        color: {_TX["primary"]};
        font-size: {_TEXT["body_lg"]};
        font-weight: 400;
        background-color: transparent;
        border: none;
    }}

    /* 思考中 */
    QLabel#thoughtBubble {{
        color: {_TX["muted"]};
        font-size: {_TEXT["body_sm"]};
        font-weight: 400;
        font-style: italic;
        padding: {_SPACE["xs"]} 0;
    }}

    /* 工具卡片 */
    QFrame#toolCard {{
        background-color: {_BG["card"]};
        border: 1px solid {_BD["subtle"]};
        border-radius: {_RADIUS["sm"]};
        padding: {_SPACE["sm"]} {_SPACE["md"]};
        margin: 2px {_SPACE["lg"]};
    }}
    QFrame#toolCard QPushButton {{
        color: {_TX["secondary"]};
        font-size: {_TEXT["body_sm"]};
        font-weight: 600;
        border: none;
        background: transparent;
        text-align: left;
    }}
    QFrame#toolCard QPushButton:hover {{
        color: {_TX["primary"]};
    }}
    QFrame#toolCard QLabel {{
        color: {_TX["muted"]};
        font-size: {_TEXT["caption"]};
        font-weight: 600;
        background: transparent;
        border: none;
        padding: 2px 0;
    }}
    QFrame#toolCard QTextEdit {{
        color: {_TX["secondary"]};
        font-size: {_TEXT["caption"]};
        font-family: {_MONO};
        border: none;
        background: transparent;
    }}

    /* 观察结果 */
    QFrame#observationBlock {{
        background-color: {_BG["card"]};
        border: 1px solid {_BD["subtle"]};
        border-radius: {_RADIUS["sm"]};
        padding: {_SPACE["sm"]} {_SPACE["md"]};
        margin: 2px {_SPACE["lg"]} 2px {_SPACE["2xl"]};
    }}
    QFrame#observationBlock QPushButton {{
        color: {_TX["muted"]};
        font-size: {_TEXT["body_sm"]};
        font-weight: 600;
        border: none;
        background: transparent;
        text-align: left;
    }}
    QFrame#observationBlock QPushButton:hover {{
        color: {_TX["primary"]};
    }}
    QFrame#observationBlock QTextEdit {{
        color: {_TX["secondary"]};
        font-size: {_TEXT["caption"]};
        font-family: {_MONO};
        border: none;
        background: transparent;
    }}
    """


def _permission_dialog_styles() -> str:
    return f"""
    /* ── 权限对话框 ── */
    QDialog#permDialog {{
        background-color: {_BG["dialog"]};
    }}
    QLabel#permHeader {{
        color: {_TX["primary"]};
        font-size: {_TEXT["heading"]};
        font-weight: 600;
        padding: {_SPACE["xs"]} 0;
    }}
    QLabel#permTitle {{
        color: {_TX["primary"]};
        font-size: {_TEXT["body"]};
        font-weight: 600;
    }}
    QLabel#permReason {{
        color: {_TX["secondary"]};
        font-size: {_TEXT["body"]};
        font-weight: 400;
    }}
    QLabel#permArgsLabel {{
        color: {_TX["muted"]};
        font-size: {_TEXT["body_sm"]};
        font-weight: 600;
    }}
    QTextEdit#permArgs {{
        color: {_TX["secondary"]};
        font-size: {_TEXT["body_sm"]};
        font-family: {_MONO};
        background-color: {_BG["card"]};
        border: 1px solid {_BD["subtle"]};
        border-radius: {_RADIUS["sm"]};
        padding: {_SPACE["sm"]} {_SPACE["md"]};
    }}
    QPushButton#permAllow {{
        background-color: {_ACCENT};
        color: {_TX["inverse"]};
        font-size: {_TEXT["body"]};
        font-weight: 600;
        border: none;
        border-radius: {_RADIUS["sm"]};
        padding: {_SPACE["sm"]} {_SPACE["2xl"]};
        min-height: {_SIZE["btn"]};
    }}
    QPushButton#permAllow:hover {{
        background-color: {_ACCENT_HOVER};
    }}
    QPushButton#permDeny {{
        background-color: transparent;
        color: {_TX["secondary"]};
        font-size: {_TEXT["body"]};
        font-weight: 500;
        border: 1px solid {_BD["strong"]};
        border-radius: {_RADIUS["sm"]};
        padding: {_SPACE["sm"]} {_SPACE["2xl"]};
        min-height: {_SIZE["btn"]};
    }}
    QPushButton#permDeny:hover {{
        background-color: {_BG["surface_hover"]};
        color: {_TX["primary"]};
    }}
    """


def _settings_dialog_styles() -> str:
    return f"""
    /* ── 设置对话框 ── */
    QDialog#settingsDialog {{
        background-color: {_BG["dialog"]};
    }}
    QDialog#settingsDialog QTabWidget::pane {{
        border: none;
        background-color: {_BG["dialog"]};
    }}
    QDialog#settingsDialog QTabBar::tab {{
        background-color: transparent;
        color: {_TX["muted"]};
        font-size: {_TEXT["body"]};
        font-weight: 400;
        padding: {_SPACE["sm"]} {_SPACE["xl"]};
        border: none;
        border-bottom: 2px solid transparent;
    }}
    QDialog#settingsDialog QTabBar::tab:selected {{
        color: {_TX["primary"]};
        font-weight: 600;
        border-bottom: 2px solid {_ACCENT};
    }}
    QDialog#settingsDialog QTabBar::tab:hover:!selected {{
        color: {_TX["primary"]};
    }}

    QPushButton#settingsSaveBtn {{
        background-color: {_ACCENT};
        color: {_TX["inverse"]};
        font-size: {_TEXT["body"]};
        font-weight: 600;
        border: none;
        border-radius: {_RADIUS["sm"]};
        padding: {_SPACE["sm"]} {_SPACE["2xl"]};
        min-height: {_SIZE["btn"]};
    }}
    QPushButton#settingsSaveBtn:hover {{
        background-color: {_ACCENT_HOVER};
    }}

    QPushButton#settingsCloseBtn {{
        background-color: {_BG["surface"]};
        color: {_TX["primary"]};
        font-size: {_TEXT["body"]};
        font-weight: 500;
        border: 1px solid {_BD["strong"]};
        border-radius: {_RADIUS["sm"]};
        padding: {_SPACE["sm"]} {_SPACE["2xl"]};
        min-height: {_SIZE["btn"]};
        margin: {_SPACE["md"]} {_SPACE["xl"]};
    }}
    QPushButton#settingsCloseBtn:hover {{
        background-color: {_BG["surface_hover"]};
    }}

    QPushButton#settingsBrowseBtn {{
        background-color: {_BG["surface"]};
        color: {_TX["primary"]};
        font-size: {_TEXT["body"]};
        font-weight: 400;
        border: 1px solid {_BD["strong"]};
        border-radius: {_RADIUS["sm"]};
        padding: {_SPACE["xs"]} {_SPACE["md"]};
        min-height: {_SIZE["btn"]};
    }}
    QPushButton#settingsBrowseBtn:hover {{
        background-color: {_BG["surface_hover"]};
    }}

    QLineEdit#settingsInput {{
        background-color: {_BG["input_field"]};
        color: {_TX["primary"]};
        font-size: {_TEXT["body"]};
        border: 1px solid {_BD["input"]};
        border-radius: {_RADIUS["sm"]};
        padding: {_SPACE["xs"]} {_SPACE["md"]};
        min-height: {_SIZE["btn"]};
    }}
    QLineEdit#settingsInput:focus {{
        border-color: {_ACCENT};
    }}

    QCheckBox {{
        color: {_TX["primary"]};
        font-size: {_TEXT["body"]};
    }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border: 2px solid {_BD["strong"]};
        border-radius: {_RADIUS["sm"]};
        background-color: {_BG["card"]};
    }}
    QCheckBox::indicator:checked {{
        background-color: {_ACCENT};
        border-color: {_ACCENT};
    }}
    """


def _status_bar_styles() -> str:
    return f"""
    /* ── 状态栏 ── */
    QLabel#statusLabel {{
        color: {_TX["muted"]};
        font-size: {_TEXT["caption"]};
        font-weight: 400;
        padding: {_SPACE["xs"]} {_SPACE["md"]};
        background-color: {_BG["chat"]};
        border-top: 1px solid {_BD["subtle"]};
    }}
    """


# ============================================================================
# 4. 入口
# ============================================================================


def generate_stylesheet() -> str:
    return _qss(
        _global_styles(),
        _session_list_styles(),
        _chat_view_styles(),
        _input_bar_styles(),
        _message_bubble_styles(),
        _permission_dialog_styles(),
        _settings_dialog_styles(),
        _status_bar_styles(),
    )
