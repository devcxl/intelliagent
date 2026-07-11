"""Markdown 渲染模块 — 基于 mistune 解析为 HTML，适配 QTextEdit。"""

import mistune


class MarkdownRenderer:
    """将 Markdown 文本渲染为适用于 QTextEdit 的 HTML。"""

    def __init__(self) -> None:
        self._markdown = mistune.create_markdown()

    def render(self, text: str) -> str:
        """Convert markdown text to HTML string."""
        return self._markdown(text)

    def apply_to_text_edit(self, text_edit, markdown_text: str) -> None:
        """Render markdown into a QTextEdit with basic styling."""
        html = self.render(markdown_text)
        styled_html = f'<html><body style="font-family: sans-serif; line-height: 1.5;">{html}</body></html>'
        text_edit.setHtml(styled_html)
