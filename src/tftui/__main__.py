from rich.style import Style
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult, Binding
from textual.widgets import Header, Footer, Tree, TextLog, LoadingIndicator, ContentSwitcher, Static
from textual.widgets._tree import TreeNode
from shutil import which
import asyncio


class NodeType:
    type = None
    name = None
    data = None

    def __init__(self, type: str, name: str, data: str):
        self.type = type
        self.name = name
        self.data = data


class StateTree(Tree):

    state = {}
    currentNode = None
    selectedNodes = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.guide_depth = 3

    def on_tree_node_highlighted(self, node) -> None:
        self.currentNode = node.node

    def on_tree_node_selected(self) -> None:
        if (self.currentNode is None): 
            return
        if (self.currentNode.data is None):
            return
        self.app.resource.clear()
        self.app.resource.write(self.currentNode.data)
        self.app.switcher.current = "resource"

    def select_current_node(self) -> None:
        if self.currentNode.data is None:
            return
        if self.currentNode in self.selectedNodes:
            self.selectedNodes.remove(self.currentNode)
        else:
            self.selectedNodes.append(self.currentNode)

    def render_label(self, node: TreeNode, base_style: Style, style: Style) -> Text:
        label = super().render_label(node, base_style, style)
        return label

    @work(exclusive=True)
    async def refresh_state(self) -> None:
        data = ""
        self.app.status.update("Terraform init...")

        returncode, stdout = await execute_async("terraform", "init", "-no-color")

        if returncode != 0:
            self.exit(message=stdout)
            return

        self.app.status.update("Terraform show...")

        returncode, stdout = await execute_async("terraform", "show", "-no-color")

        if returncode != 0:
            self.exit(message=stdout)
            return
        elif not stdout.startswith('#'):
            self.exit(message=stdout)
            return

        self.app.status.update("")

        for line in stdout.splitlines():

            # regular resource
            if line.startswith('#') and not line.startswith('# module'):
                leaf = self.root.add_leaf(line[2:-1])

            # module
            elif line.startswith('# module'):
                node = self.root
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

        self.root.expand_all()
        self.app.switcher.current = "tree"


class TerraformTUI(App):

    status = None
    switcher = None
    tree = None
    resource = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    TITLE = "Terraform TUI"
    SUB_TITLE = "The textual UI for Terraform"
    CSS_PATH = "ui.css"

    BINDINGS = [
        ("Enter", "", "View state"),
        Binding("escape", "back", "Back"),
        ("s", "select", "Select"),
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
            yield StateTree("State", id="tree", classes="tree")
            yield TextLog(id="resource", highlight=True, markup=True, wrap=True, classes="resource", auto_scroll=False)
        yield Static(id="status", classes="status")
        yield Footer()

    def on_mount(self) -> None:
        self.status = self.get_widget_by_id("status")
        self.resource = self.get_widget_by_id("resource")
        self.tree = self.get_widget_by_id("tree")
        self.switcher = self.get_widget_by_id("switcher")

    async def on_ready(self) -> None:
        self.tree.refresh_state()

    def action_back(self) -> None:
        if not self.switcher.current == "resource":
            return
        self.switcher.current = "tree"

    def action_select(self) -> None:
        if not self.switcher.current == "tree":
            return
        self.tree.select_current_node()

    def action_destroy(self) -> None:
        if not self.switcher.current == "tree":
            return

    def action_taint(self) -> None:
        if not self.switcher.current == "tree":
            return

    def action_untaint(self) -> None:
        if not self.switcher.current == "tree":
            return

    def action_refresh(self) -> None:
        if not self.switcher.current == "tree":
            return

    def action_toggle_dark(self) -> None:
        self.dark = not self.dark


async def execute_async(*command: str) -> tuple[str, str]:
    proc = await asyncio.create_subprocess_exec(*command,
                                                stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.STDOUT)

    stdout, strerr = await proc.communicate()
    response = stdout.decode('utf-8')

    return (proc.returncode, response)


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
