"""The keyboard reference."""

from __future__ import annotations

from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Grid
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable

#: (key, description, section). Sections group the table for scanning.
KEYS: tuple[tuple[str, str, str], ...] = (
    ("↑ ↓ / j k", "Move up and down", "Navigate"),
    ("← → / h l", "Collapse / expand, or step in and out", "Navigate"),
    ("Enter", "View the resource, or expand the module", "Navigate"),
    ("Esc", "Go back to the state tree", "Navigate"),
    ("/", "Filter the tree, or search within a plan", "Navigate"),
    ("n / N", "Next / previous match when searching a plan", "Navigate"),
    ("0-9", "Collapse the tree to a module depth; 0 expands everything", "Navigate"),
    ("Space", "Select the resource, or every resource in the module", "Select"),
    ("Ctrl+A", "Clear the current selection", "Select"),
    ("T", "Taint the selection, or the highlighted resource", "Act"),
    ("U", "Untaint the selection, or the highlighted resource", "Act"),
    ("D", "Remove from state the selection, or the highlighted resource", "Act"),
    ("P", "Create an execution plan", "Plan"),
    ("Ctrl+D", "Create a destruction plan", "Plan"),
    ("A", "Apply the current plan", "Plan"),
    ("X", "Reveal sensitive values in the resource view", "Inspect"),
    ("F", "Full screen; hold Shift or Option to select text with the mouse", "Inspect"),
    ("C", "Copy the resource name or definition to the clipboard", "Inspect"),
    ("R", "Refresh the state tree", "Session"),
    ("W", "Switch workspace", "Session"),
    ("M", "Toggle light and dark mode", "Session"),
    ("?", "Show this help", "Session"),
    ("Q", "Quit", "Session"),
)


class HelpScreen(ModalScreen[None]):
    """A grouped table of every binding."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", "Close", show=False),
        Binding("question_mark", "close", "Close", show=False),
        Binding("q", "close", "Close", show=False),
    ]

    def compose(self) -> ComposeResult:
        table: DataTable[Text] = DataTable(show_cursor=False, zebra_stripes=True, id="helptable")
        table.add_columns(
            Text("Key", "bold", justify="right"),
            Text("Action", "bold"),
        )

        section = ""
        for key, description, group in KEYS:
            if group != section:
                section = group
                table.add_row(Text(""), Text(group.upper(), "bold dim"))
            table.add_row(Text(key, "bold", justify="right"), Text(description))

        button = Button("Close", id="close", variant="primary")
        yield Grid(table, button, id="help")

    def on_mount(self) -> None:
        self.query_one("#close", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        del event
        self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)
