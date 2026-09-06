"""The workspace picker."""

from __future__ import annotations

from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, OptionList, Static


class WorkspaceScreen(ModalScreen[str | None]):
    """Lets the user switch Terraform workspace."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(self, workspaces: tuple[str, ...], current: str) -> None:
        super().__init__()
        self.workspaces = workspaces
        self.current = current

    def compose(self) -> ComposeResult:
        self.options = OptionList(*self.workspaces, id="workspacelist")
        yield Vertical(
            Static(Text("Select a workspace:\n", "bold"), id="question"),
            self.options,
            Button("Switch", id="ok", variant="primary"),
            id="workspaces",
        )

    def on_mount(self) -> None:
        if self.current in self.workspaces:
            self.options.highlighted = self.workspaces.index(self.current)
        self.options.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(self.workspaces[event.option_index])

    def on_button_pressed(self, event: Button.Pressed) -> None:
        del event
        self._submit()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _submit(self) -> None:
        index = self.options.highlighted
        self.dismiss(None if index is None else self.workspaces[index])
