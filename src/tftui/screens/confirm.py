"""A yes/no confirmation dialog."""

from __future__ import annotations

from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Grid, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ConfirmScreen(ModalScreen[bool]):
    """Asks the user to confirm a destructive action.

    Defaults to *No*: the focused button when the dialog opens is the safe one,
    so a stray Enter cannot destroy anything.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("y", "confirm(True)", "Yes", show=False),
        Binding("n", "confirm(False)", "No", show=False),
        Binding("escape", "confirm(False)", "Cancel", show=False),
    ]

    def __init__(self, question: Text | str) -> None:
        super().__init__()
        self.question = question

    def compose(self) -> ComposeResult:
        self._no = Button("No", id="no", variant="primary")
        yield Grid(
            VerticalScroll(Static(self.question, id="question"), id="questionbox"),
            Button("Yes", id="yes", variant="error"),
            self._no,
            id="yesno",
        )

    def on_mount(self) -> None:
        self._no.focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

    def action_confirm(self, answer: bool) -> None:
        self.dismiss(answer)
