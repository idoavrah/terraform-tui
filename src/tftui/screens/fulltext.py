"""A borderless full-screen view, for reading and for mouse-selecting text."""

from __future__ import annotations

from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.screen import ModalScreen
from textual.widgets import RichLog

from tftui.widgets.resource_view import highlight_lines


class FullTextScreen(ModalScreen[None]):
    """Shows content edge to edge so it can be selected with the mouse."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("f", "close", "Close", show=False),
        Binding("escape", "close", "Close", show=False),
        Binding("q", "close", "Close", show=False),
    ]

    def __init__(self, content: Text | str, *, syntax: bool = False) -> None:
        super().__init__()
        self.content = content
        self.syntax = syntax

    def compose(self) -> ComposeResult:
        log = RichLog(auto_scroll=False, wrap=True, markup=False, id="fulltext")
        if self.syntax and isinstance(self.content, str):
            for line in highlight_lines(self.content, dark=bool(self.app.current_theme.dark)):
                log.write(line)
        else:
            log.write(self.content)
        yield log

    def action_close(self) -> None:
        self.dismiss(None)
