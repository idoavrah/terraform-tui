"""The dialog that collects options before creating a plan."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Grid, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Static


@dataclass(frozen=True, slots=True)
class PlanRequest:
    """What the user asked for when creating a plan."""

    var_file: str
    targeted: bool


class PlanInputsScreen(ModalScreen[PlanRequest | None]):
    """Asks for an optional var-file and whether to target the selection."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(self, *, var_file: str | None, targets_available: bool, destroy: bool) -> None:
        super().__init__()
        self._var_file = var_file or ""
        self._targets_available = targets_available
        self._destroy = destroy

    def compose(self) -> ComposeResult:
        verb = "destruction plan" if self._destroy else "plan"
        question = Static(
            Text(f"Create a Terraform {verb}?", "bold"),
            id="question",
        )
        self.input = Input(
            id="varfile",
            placeholder="Optional",
            value=self._var_file,
        )
        self.checkbox = Checkbox(
            "Target only selected resources",
            id="plantarget",
            value=self._targets_available,
            disabled=not self._targets_available,
        )
        yield Grid(
            question,
            Horizontal(Static("Var-file:", id="varfilelabel"), self.input),
            self.checkbox,
            Button("Create", id="yes", variant="primary"),
            Button("Cancel", id="no"),
            id="tfvars",
        )

    def on_mount(self) -> None:
        self.input.focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "yes":
            self._submit()
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        del event
        self._submit()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _submit(self) -> None:
        self.dismiss(
            PlanRequest(
                var_file=self.input.value.strip(),
                targeted=self.checkbox.value,
            )
        )
