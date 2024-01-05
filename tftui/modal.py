from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Grid
from textual.screen import ModalScreen
from textual.widgets import Button, RichLog, Input, Checkbox, Static


class YesNoModal(ModalScreen):
    contents = None

    def __init__(self, contents: str, *args, **kwargs):
        self.contents = contents
        super().__init__(*args, **kwargs)

    def compose(self) -> ComposeResult:
        question = RichLog(id="question", auto_scroll=False, wrap=True)
        question.write(self.contents)
        yield Grid(
            question,
            Button("Yes", variant="primary", id="yes"),
            Button("No", id="no"),
            id="yesno",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "yes":
            self.dismiss(True)
        else:
            self.dismiss(False)

    def on_key(self, event) -> None:
        if event.key == "y":
            self.dismiss(True)
        elif event.key == "n" or event.key == "escape":
            self.dismiss(False)


class PlanInputsModal(ModalScreen):
    input = None
    checkbox = None
    var_file = None

    def __init__(self, var_file, targets=False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.var_file = var_file
        self.input = Input(id="varfile", placeholder="Optional")
        self.checkbox = Checkbox(
            "Target only selected resources",
            id="plantarget",
            value=targets,
        )

    def compose(self) -> ComposeResult:
        question = Static(
            Text("Would you like to create a terraform plan?", "bold"), id="question"
        )
        if self.var_file:
            self.input.value = self.var_file
        yield Grid(
            question,
            Static("Var-file:", id="varfilelabel"),
            self.input,
            self.checkbox,
            Button("Yes", variant="primary", id="yes"),
            Button("No", id="no"),
            id="tfvars",
        )
        self.input.focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "yes":
            self.dismiss((self.input.value, self.checkbox.value))
        else:
            self.dismiss(None)

    def on_key(self, event) -> None:
        if event.key == "y":
            self.dismiss((self.input.value, self.checkbox.value))
        elif event.key == "n" or event.key == "escape":
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss((self.input.value, self.checkbox.value))
