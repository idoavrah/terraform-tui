from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Grid
from textual.screen import ModalScreen
from textual.widgets import Button, RichLog, Input


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def compose(self) -> ComposeResult:
        question = RichLog(id="question", auto_scroll=False, wrap=True)
        question.write(Text("Would you like to create a terraform plan?", "bold"))
        self.input = Input(id="varfile", placeholder="Enter a valid var-file name...")
        yield Grid(
            question,
            self.input,
            Button("Yes", variant="primary", id="yes"),
            Button("No", id="no"),
            id="tfvars",
        )
        self.input.focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "yes":
            self.dismiss(self.input.value)
        else:
            self.dismiss(None)

    def on_key(self, event) -> None:
        if event.key == "y":
            self.dismiss(self.input.value)
        elif event.key == "n" or event.key == "escape":
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(self.input.value)
