"""MiniMax 设计系统 → QSS 样式表。从 DESIGN.md 设计令牌编译为 Qt QSS。"""

COLORS = {
    "primary": "#0a0a0a",
    "on_primary": "#ffffff",
    "surface": "#f7f8fa",
    "surface_soft": "#f2f3f5",
    "canvas": "#ffffff",
    "hairline": "#e5e7eb",
    "hairline_soft": "#eaecf0",
    "ink": "#0a0a0a",
    "ink_strong": "#000000",
    "charcoal": "#222222",
    "steel": "#5f5f5f",
    "stone": "#8e8e93",
    "muted": "#a8aab2",
    "brand_blue": "#1456f0",
    "brand_blue_deep": "#1d4ed8",
}


def _qss(*rules: str) -> str:
    return "\n\n".join(rules)


def generate_stylesheet() -> str:
    C = COLORS

    return _qss(
        # ── Global fonts only (NO widget-level background/color override) ──
        """
        * {
            font-family: "DM Sans", "Inter", "Helvetica Neue", "Helvetica", "Arial", sans-serif;
        }
        """,
        # ── SessionList ──────────────────────────────────────
        f"""
        QListWidget#sessionList {{
            background-color: {C["canvas"]};
            border: none;
            outline: none;
            padding: 4px;
        }}
        QListWidget#sessionList::item {{
            background-color: transparent;
            color: {C["charcoal"]};
            font-size: 14px;
            font-weight: 400;
            padding: 6px 12px;
            border-radius: 6px;
        }}
        QListWidget#sessionList::item:selected {{
            background-color: {C["surface"]};
            color: {C["ink"]};
            font-weight: 500;
        }}
        QListWidget#sessionList::item:hover {{
            background-color: {C["surface_soft"]};
        }}

        QPushButton#newSessionBtn {{
            background-color: {C["primary"]};
            color: {C["on_primary"]};
            font-size: 14px;
            font-weight: 600;
            border: none;
            border-radius: 9999px;
            padding: 8px 20px;
            min-height: 36px;
        }}
        QPushButton#newSessionBtn:hover {{
            background-color: {C["charcoal"]};
        }}
        QPushButton#newSessionBtn:disabled {{
            background-color: {C["hairline"]};
            color: {C["muted"]};
        }}
        """,
        # ── ChatView ─────────────────────────────────────────
        f"""
        QScrollArea#chatView {{
            background-color: {C["canvas"]};
            border: none;
        }}
        QScrollBar:vertical {{
            background-color: {C["canvas"]};
            width: 8px;
            margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background-color: {C["hairline"]};
            border-radius: 4px;
            min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{
            background-color: {C["stone"]};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
        }}
        """,
        # ── InputBar ─────────────────────────────────────────
        f"""
        QLineEdit#msgInput {{
            background-color: {C["canvas"]};
            color: {C["ink"]};
            font-size: 16px;
            font-weight: 400;
            border: 1px solid {C["hairline"]};
            border-radius: 8px;
            padding: 8px 14px;
            min-height: 36px;
            selection-background-color: {C["brand_blue"]};
            selection-color: {C["on_primary"]};
        }}
        QLineEdit#msgInput:focus {{
            border: 2px solid {C["brand_blue_deep"]};
        }}
        QLineEdit#msgInput:disabled {{
            background-color: {C["surface"]};
            color: {C["muted"]};
        }}

        QPushButton#sendBtn {{
            background-color: {C["primary"]};
            color: {C["on_primary"]};
            font-size: 14px;
            font-weight: 600;
            border: none;
            border-radius: 9999px;
            padding: 8px 20px;
            min-height: 36px;
        }}
        QPushButton#sendBtn:hover {{
            background-color: {C["charcoal"]};
        }}
        QPushButton#sendBtn:disabled {{
            background-color: {C["hairline"]};
            color: {C["muted"]};
        }}
        """,
        # ── MessageBubble ────────────────────────────────────
        f"""
        QFrame#userBubble {{
            background-color: {C["primary"]};
            border-radius: 12px;
            padding: 10px 16px;
            margin: 4px 0;
        }}
        QFrame#userBubble QLabel {{
            color: {C["on_primary"]};
            font-size: 14px;
            font-weight: 400;
        }}

        QLabel#thoughtBubble {{
            color: {C["steel"]};
            font-size: 13px;
            font-weight: 400;
            font-style: italic;
            padding: 4px 0;
        }}

        QFrame#toolCard {{
            background-color: {C["surface"]};
            border: 1px solid {C["hairline"]};
            border-radius: 8px;
            padding: 8px;
            margin: 4px 0;
        }}
        QLabel#toolCardTitle {{
            color: {C["ink"]};
            font-size: 14px;
            font-weight: 600;
        }}
        QLabel#toolCardArg {{
            color: {C["steel"]};
            font-size: 13px;
            font-weight: 400;
        }}

        QFrame#observationBlock {{
            background-color: {C["surface"]};
            border: 1px solid {C["hairline"]};
            border-radius: 8px;
            padding: 8px 12px;
            margin: 4px 0;
        }}
        QFrame#observationBlock QTextEdit {{
            color: {C["charcoal"]};
            font-size: 13px;
            font-weight: 400;
            background-color: transparent;
            border: none;
        }}

        QFrame#answerBubble {{
            border: none;
            margin: 4px 0;
            padding: 4px 0;
        }}
        QFrame#answerBubble QTextEdit {{
            color: {C["charcoal"]};
            font-size: 15px;
            font-weight: 400;
            background-color: transparent;
            border: none;
        }}
        """,
        # ── PermissionDialog ─────────────────────────────────
        f"""
        QDialog {{
            background-color: {C["canvas"]};
        }}
        QLabel#permTitle {{
            color: {C["ink"]};
            font-size: 16px;
            font-weight: 600;
        }}
        QPushButton#permAllow {{
            background-color: {C["primary"]};
            color: {C["on_primary"]};
            font-size: 14px;
            font-weight: 600;
            border: none;
            border-radius: 9999px;
            padding: 8px 24px;
            min-height: 36px;
        }}
        QPushButton#permAllow:hover {{
            background-color: {C["charcoal"]};
        }}
        QPushButton#permDeny {{
            background-color: transparent;
            color: {C["ink"]};
            font-size: 14px;
            font-weight: 600;
            border: 1px solid {C["ink"]};
            border-radius: 9999px;
            padding: 8px 24px;
            min-height: 36px;
        }}
        QPushButton#permDeny:hover {{
            background-color: {C["surface"]};
        }}
        """,
        # ── StatusBar ────────────────────────────────────────
        f"""
        QLabel#statusLabel {{
            color: {C["steel"]};
            font-size: 12px;
            font-weight: 400;
            padding: 2px 8px;
            background-color: {C["canvas"]};
            border-top: 1px solid {C["hairline"]};
        }}
        """,
    )
