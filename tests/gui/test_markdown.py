"""MarkdownRenderer 单元测试 — Markdown → HTML 渲染。"""

from __future__ import annotations

from src.gui.styles.markdown import MarkdownRenderer


def test_render_plain_text():
    md = MarkdownRenderer()
    html = md.render("Hello World")
    assert "Hello World" in html


def test_render_bold():
    md = MarkdownRenderer()
    html = md.render("**bold**")
    assert "<strong>" in html or "<b>" in html


def test_render_code_block():
    md = MarkdownRenderer()
    html = md.render("```python\nprint('hello')\n```")
    assert "<code" in html


def test_render_list():
    md = MarkdownRenderer()
    html = md.render("- item1\n- item2")
    assert "<li>" in html
    assert "<ul>" in html or "<ol>" in html


def test_render_empty_string():
    md = MarkdownRenderer()
    html = md.render("")
    assert isinstance(html, str)
