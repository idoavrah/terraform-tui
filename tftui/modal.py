from textual.app import ComposeResult
from textual.containers import Grid
from textual.screen import ModalScreen
from textual.widgets import Button, RichLog


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
            Button("Yes", variant="error", id="yes"),
            Button("No", variant="primary", id="no"),
            id="dialog",
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
