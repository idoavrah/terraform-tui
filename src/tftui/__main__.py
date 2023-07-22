from typing import List
from textual import work
from textual.app import App, ComposeResult, Binding
from textual.widgets import Header, Footer, Tree, TextLog, LoadingIndicator, ContentSwitcher, Static
from shutil import which
import subprocess
import asyncio


async def execute_async(*command: str) -> tuple[str, str]:
    proc = await asyncio.create_subprocess_exec(*command,
                                                stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.STDOUT)

    stdout, strerr = await proc.communicate()
    response = stdout.decode('utf-8')

    return (proc.returncode, response)


class TerraformTUI(App):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.state = {}
        self.currentNode = None

    TITLE = "Terraform TUI"
    SUB_TITLE = "The textual UI for Terraform"
    CSS_PATH = "ui.css"

    BINDINGS = [
        ("Enter", "", "View state"),
        Binding("escape", "back", "Back"),
        # ("d", "destroy", "Destroy"),
        # ("t", "taint", "Taint"),
        # ("u", "untaint", "Untaint"),
        # ("r", "refresh", "Refresh"),
        ("m", "toggle_dark", "Toggle dark mode"),
        ("q", "quit", "Quit")
    ]

    def compose(self) -> ComposeResult:
        yield Header(classes="header")
        with ContentSwitcher(id="switcher", initial="loading"):
            yield LoadingIndicator(id="loading")
            yield Tree("State", id="tree", classes="tree")
            yield TextLog(id="pretty", highlight=True, markup=True, wrap=True, classes="pretty", auto_scroll=False)
        yield Static(id="status", classes="status")
        yield Footer()

    def on_mount(self) -> None:
        tree = self.get_widget_by_id("tree")
        tree.guide_depth = 3
        status = self.get_widget_by_id("status")
        status.update("Loading state...")

    async def on_ready(self) -> None:
        self.load_state()

    @work(exclusive=True)
    async def load_state(self) -> None:
        tree = self.get_widget_by_id("tree")
        status = self.get_widget_by_id("status")
        data = ""

        status.update("Terraform init...")

        returncode, stdout = await execute_async("terraform", "init", "-no-color")

        if returncode != 0:
            self.exit(message=stdout)
            return

        status.update("Terraform show...")

        returncode, stdout = await execute_async("terraform", "show", "-no-color")

        if returncode != 0:
            self.exit(message=stdout)
            return
        elif not stdout.startswith('#'):
            self.exit(message=stdout)
            return

        status.update("")

        for line in stdout.splitlines():

            # regular resource
            if line.startswith('#') and not line.startswith('# module'):
                leaf = tree.root.add_leaf(line[2:-1])

            # module
            elif line.startswith('# module'):
                node = tree.root
                items = []
                leaf = ""
                parts = line[2:-1].split('.')
                for part in parts:
                    if part == "module":
                        isModule = True
                        continue
                    elif isModule:
                        isModule = False
                        items.append(f"module.{part}")
                        continue
                    leaf = f"{leaf}.{part}"
                items.append(leaf[1:])

                key = ""
                for item in items:
                    isModule = False
                    key = f"{key}.{item}"
                    if item.startswith("module"):
                        isModule = True
                    if self.state.get(key) is None:
                        if isModule:
                            node = node.add(item)
                        else:
                            leaf = node.add_leaf(item)
                        self.state[key] = node
                    else:
                        node = self.state[key]

            # data portion of resource
            else:
                data += line + "\n"

            if len(line) == 1:
                leaf.data = data.strip()
                data = ""

        tree.root.expand_all()
        self.get_widget_by_id("switcher").current = "tree"

    def on_tree_node_highlighted(self, node) -> None:
        self.currentNode = node.node
        pretty = self.get_widget_by_id("pretty")
        if self.currentNode.data is not None:
            pretty = self.get_widget_by_id("pretty")
            pretty.clear()
            pretty.write(self.currentNode.data)
        else:
            self.currentNode = None

    def on_tree_node_selected(self) -> None:
        if (self.currentNode is None):
            return
        self.get_widget_by_id("switcher").current = "pretty"

    def action_back(self) -> None:
        switcher = self.get_widget_by_id("switcher")
        if not switcher.current == "pretty":
            return
        switcher.current = "tree"

    def action_destroy(self) -> None:
        if not self.get_widget_by_id("switcher").current == "tree":
            return

    def action_taint(self) -> None:
        if not self.get_widget_by_id("switcher").current == "tree":
            return

    def action_untaint(self) -> None:
        if not self.get_widget_by_id("switcher").current == "tree":
            return

    def action_refresh(self) -> None:
        if not self.get_widget_by_id("switcher").current == "tree":
            return

    def action_toggle_dark(self) -> None:
        self.dark = not self.dark


def main() -> None:

    if which("terraform") is None:
        print("Terraform not found. Please install Terraform and try again.")
        return

    app = TerraformTUI()
    result = app.run()
    if result is not None:
        print(result)


if __name__ == "__main__":
    main()
