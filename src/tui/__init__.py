"""Textual TUI（CONTEXT 术语：TUI）：唯一交互式前端，仅消费引擎事件流（ADR 0009、issue #61）。

模块分工：event_sink 事件翻译、editor 输入、message_stream/message_view 消息流、status_bar 与
tool_panel 展示组件、app 应用与执行入口、assembly 最小组装。
"""
