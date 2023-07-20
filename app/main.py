from pathlib import Path
from rich.text import Text
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Tree, TextLog, LoadingIndicator
from textual.widgets.tree import TreeNode


class TerraformTUI(App):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.state = {}

    BINDINGS = [
        ("t", "taint", "Taint"),
        ("d", "toggle_dark", "Toggle dark mode"),
        ("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Tree("State")
        yield TextLog(highlight=True, markup=True, wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        log = self.query_one(TextLog)
        tree = self.query_one(Tree)
        tree.root.expand()

        log.write('Starting TFTUI')

        with open("state.txt") as data_file:
            for line in data_file:
                line = line.rstrip()
                if line.startswith('#'):
                  parts = line[2:-1].split('.')
                  qualifier = ".".join(parts[:-1])
                  node = tree.root
                  for part in parts:
                    if self.state.get(qualifier) is None:
                       node = node.add(part)
                       self.state[qualifier] = node
                    else:
                      node = self.state[qualifier]
                    node = node.add(part)
                    node.expand()
                                      
                # log.write(line.rstrip())

    def action_toggle_dark(self) -> None:
        self.dark = not self.dark

if __name__ == "__main__":
    app = TerraformTUI()
    app.run()
