"""MiniMax 设计系统 → QSS 样式表。

从 DESIGN.md 提取设计令牌并编译为 Qt QSS。
"""

# ── Design Tokens ──────────────────────────────────────────────────

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
    "slate": "#45515e",
    "steel": "#5f5f5f",
    "stone": "#8e8e93",
    "muted": "#a8aab2",
    "brand_coral": "#ff5530",
    "brand_blue": "#1456f0",
    "brand_blue_deep": "#1d4ed8",
    "success_bg": "#e8ffea",
    "success_text": "#1ba673",
    "error_border": "#d45656",
}

RADIUS = {
    "xs": "4px",
    "sm": "6px",
    "md": "8px",
    "lg": "12px",
    "xl": "16px",
    "xxl": "20px",
    "xxxl": "24px",
    "hero": "32px",
    "full": "9999px",
}


def _qss(*rules: str) -> str:
    """Join QSS rule blocks."""
    return "\n\n".join(rules)


def generate_stylesheet() -> str:
    """Generate complete MiniMax-themed QSS stylesheet."""
    C = COLORS
    R = RADIUS

    return _qss(
        # ── Global ──────────────────────────────────────────
        f"""
        * {{
            font-family: "DM Sans", "Inter", "Helvetica Neue", "Helvetica", "Arial", sans-serif;
        }}

        QWidget {{
            background-color: {C["canvas"]};
            color: {C["charcoal"]};
        }}
        """,
        # ── SessionList ──────────────────────────────────────
        f"""
        /* [+] New Session Button */
        QPushButton {{
            background-color: {C["primary"]};
            color: {C["on_primary"]};
            font-size: 14px;
            font-weight: 600;
            border: none;
            border-radius: {R["full"]};
            padding: 8px 20px;
            min-height: 36px;
        }}
        QPushButton:hover {{
            background-color: {C["charcoal"]};
        }}
        QPushButton:disabled {{
            background-color: {C["hairline"]};
            color: {C["muted"]};
        }}

        /* Session List Items */
        QListWidget {{
            background-color: {C["canvas"]};
            border: none;
            outline: none;
            padding: 4px;
        }}
        QListWidget::item {{
            background-color: transparent;
            color: {C["charcoal"]};
            font-size: 14px;
            font-weight: 400;
            padding: 6px 12px;
            border-radius: {R["sm"]};
            border: none;
        }}
        QListWidget::item:selected {{
            background-color: {C["surface"]};
            color: {C["ink"]};
            font-weight: 500;
        }}
        QListWidget::item:hover {{
            background-color: {C["surface_soft"]};
        }}
        """,
        # ── ChatView ─────────────────────────────────────────
        f"""
        QScrollArea {{
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
        /* Text Input */
        QLineEdit {{
            background-color: {C["canvas"]};
            color: {C["ink"]};
            font-size: 16px;
            font-weight: 400;
            border: 1px solid {C["hairline"]};
            border-radius: {R["md"]};
            padding: 8px 14px;
            min-height: 36px;
            selection-background-color: {C["brand_blue"]};
            selection-color: {C["on_primary"]};
        }}
        QLineEdit:focus {{
            border: 2px solid {C["brand_blue_deep"]};
        }}
        QLineEdit:disabled {{
            background-color: {C["surface"]};
            color: {C["muted"]};
        }}

        /* Send Button */
        QPushButton#sendBtn {{
            background-color: {C["primary"]};
            color: {C["on_primary"]};
            font-size: 14px;
            font-weight: 600;
            border: none;
            border-radius: {R["full"]};
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
        /* User bubble (right-aligned) */
        QLabel#userBubble {{
            background-color: {C["primary"]};
            color: {C["on_primary"]};
            font-size: 14px;
            font-weight: 400;
            border-radius: {R["lg"]};
            padding: 10px 16px;
            max-width: 600px;
        }}

        /* Thought bubble (gray italic) */
        QLabel#thoughtBubble {{
            color: {C["steel"]};
            font-size: 13px;
            font-weight: 400;
            font-style: italic;
            padding: 4px 0;
        }}

        /* Tool call card */
        QFrame#toolCard {{
            background-color: {C["surface"]};
            border: 1px solid {C["hairline"]};
            border-radius: {R["md"]};
            padding: 8px;
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
            font-family: "Courier New", monospace;
        }}

        /* Observation block */
        QTextEdit#observationBlock {{
            background-color: {C["surface"]};
            color: {C["charcoal"]};
            font-size: 13px;
            font-weight: 400;
            font-family: "Courier New", monospace;
            border: 1px solid {C["hairline"]};
            border-radius: {R["md"]};
            padding: 8px 12px;
        }}

        /* Answer bubble (Markdown) */
        QTextEdit#answerBubble {{
            background-color: transparent;
            color: {C["charcoal"]};
            font-size: 15px;
            font-weight: 400;
            border: none;
            padding: 4px 0;
            line-height: 1.5;
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
            border-radius: {R["full"]};
            padding: 8px 24px;
            min-height: 36px;
        }}
        QPushButton#permDeny {{
            background-color: transparent;
            color: {C["ink"]};
            font-size: 14px;
            font-weight: 600;
            border: 1px solid {C["ink"]};
            border-radius: {R["full"]};
            padding: 8px 24px;
            min-height: 36px;
        }}
        QPushButton#permAllow:hover {{
            background-color: {C["charcoal"]};
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


__all__ = ["generate_stylesheet"]
