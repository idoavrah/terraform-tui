from rich.style import Style
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult, Binding
from textual.widgets import Header, Footer, Tree, TextLog, LoadingIndicator, ContentSwitcher, Static
from textual.widgets._tree import TreeNode
from shutil import which
import asyncio


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
        if self.currentNode is None or self.currentNode.data is None:
            return
        if self.currentNode.data.startswith('module'):
            return
        self.app.resource.clear()
        self.app.resource.write(self.currentNode.data)
        self.app.switcher.current = "resource"

    def select_current_node(self) -> None:
        if self.currentNode.data.startswith('module'):
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
        self.app.status.update("Executing Terraform init")

        returncode, stdout = await execute_async("terraform", "init", "-no-color")

        if returncode != 0:
            self.app.exit(message=stdout)
            return

        self.app.status.update("Executing Terraform show")

        returncode, stdout = await execute_async("terraform", "show", "-no-color")

        if returncode != 0 or not stdout.startswith('#'):
            self.app.exit(message=stdout)
            return

        self.app.status.update("Building state tree")

        lines = stdout.splitlines()
        line_index = 0
        node = self.root

        # build module tree
        modules = set()
        for line in lines:
            if not line.startswith('# module'):
                continue
            parts = line[2:-1].split('.')
            i = 0
            module = ""
            while parts[i] == 'module':
                module += f"{parts[i]}.{parts[i+1]}."
                modules.add(module[:-1])
                i += 2

        module_nodes = {}
        for module_fullname in sorted(modules):
            parts = module_fullname.split('.')
            qualifier = ""
            i = 0
            while i < len(parts):
                qualifier = f"{parts[i]}.{parts[i+1]}."
                if qualifier[:-1] not in module_nodes:
                    node = self.root.add(qualifier[:-1], data=module_fullname)
                    module_nodes[qualifier[:-1]] = node
                i += 2

        # parse objects
        name = ""
        for line in lines:
            if line.startswith('#'):
                parts = line[2:-1].split('.')
                i = 0
                qualifier = ""
                while parts[i] == 'module':
                    qualifier = f"{parts[i]}.{parts[i+1]}."
                    i += 2
                name = '.'.join(parts[i:])
                data = ""
                if qualifier[:-1] in module_nodes:
                    module_node = module_nodes[qualifier[:-1]]
                else:
                    module_node = self.root
            elif line == "}":
                data += line + "\n"
                module_node.add_leaf(name, data=data.strip())
            else:
                data += line + "\n"

        self.root.expand_all()
        self.app.switcher.current = "tree"
        self.app.status.update("")

        return


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
