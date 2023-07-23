from textual import work
from textual.app import App, ComposeResult, Binding
from textual.widgets import Header, Footer, Tree, TextLog, LoadingIndicator, ContentSwitcher, Static, Button
from textual.containers import Vertical, Horizontal
from shutil import which
import asyncio


class StateTree(Tree):

    current_node = None
    selected_nodes = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.guide_depth = 3
        self.root.data = ""

    def on_tree_node_highlighted(self, node) -> None:
        self.current_node = node.node

    def on_tree_node_selected(self) -> None:
        if self.current_node is None:
            return
        if self.current_node.data.startswith('module') or self.current_node.is_root:
            return
        self.app.resource.clear()
        self.app.resource.write(self.current_node.data)
        self.app.switcher.current = "resource"

    def select_current_node(self) -> None:
        if self.current_node is None:
            return
        if self.current_node.data.startswith('module') or self.current_node.data.startswith('data') or self.current_node.is_root:
            return
        if self.current_node in self.selected_nodes:
            self.selected_nodes.remove(self.current_node)
            label = self.current_node.label
            label.right_crop(4)
            self.current_node.set_label(label)
        else:
            self.selected_nodes.append(self.current_node)
            self.current_node.set_label(self.current_node.label.append(" [X]"))

    @work(exclusive=True)
    async def refresh_state(self) -> None:

        self.app.switcher.current = "loading"
        self.selected_nodes = []
        self.current_node = None
        self.clear()
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

        # build module tree
        modules = set()
        module_nodes = {}
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
                parts = line[2:].split('.')
                i = 0
                qualifier = ""
                while parts[i] == 'module':
                    qualifier = f"{parts[i]}.{parts[i+1]}."
                    i += 2
                name = '.'.join(parts[i:]).replace(':', '')
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
        self.app.status.update("")
        self.app.switcher.current = "tree"
        self.app.tree.focus()


class TerraformTUI(App):

    status = None
    switcher = None
    tree = None
    resource = None
    question = None
    action = None
    selected_action = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    TITLE = "Terraform TUI"
    SUB_TITLE = "The textual UI for Terraform"
    CSS_PATH = "ui.css"

    BINDINGS = [
        ("Enter", "", "View state"),
        Binding("escape", "back", "Back"),
        ("s", "select", "Select"),
        ("t", "taint", "Taint"),
        ("u", "untaint", "Untaint"),
        ("r", "refresh", "Refresh state"),
        ("m", "toggle_dark", "Toggle dark mode"),
        Binding("y", "yes", "Yes", show=False),
        Binding("n", "no", "No", show=False),
        ("q", "quit", "Quit")
    ]

    def compose(self) -> ComposeResult:
        yield Header(classes="header")
        with ContentSwitcher(id="switcher", initial="loading"):
            yield LoadingIndicator(id="loading")
            yield StateTree("State", id="tree")
            yield TextLog(id="resource", highlight=True, markup=True, wrap=True, classes="resource", auto_scroll=False)
            with Vertical(id="action"):
                yield TextLog(id="question", auto_scroll=False)
                with Horizontal():
                    yield Button("Yes", id="yes", variant="primary")
                    yield Button("No", id="no", variant="error")
        yield Static(id="status", classes="status")
        yield Footer()

    def on_mount(self) -> None:
        self.status = self.get_widget_by_id("status")
        self.resource = self.get_widget_by_id("resource")
        self.tree = self.get_widget_by_id("tree")
        self.switcher = self.get_widget_by_id("switcher")
        self.question = self.get_widget_by_id("question")
        self.action = self.get_widget_by_id("action")

    async def on_ready(self) -> None:
        self.tree.refresh_state()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "yes":
            await self.perform_action()
        elif event.button.id == "no":
            self.action_no()

    async def perform_taint_untaint(self, what_to_do: str) -> None:
        resources = [
            f"{node.parent.data}.{node.label.plain[:-4]}".lstrip(".").replace(' (tainted)', '') for node in self.tree.selected_nodes]
        for resource in resources:
            await execute_async("terraform", what_to_do, resource)

    async def perform_action(self) -> None:
        if self.switcher.current != "action":
            return
        if self.selected_action == "taint" or self.selected_action == "untaint":
            self.status.update(f"Executing Terraform {self.selected_action}")
            self.switcher.current = "loading"
            await self.perform_taint_untaint(self.selected_action)
        self.tree.refresh_state()

    async def action_yes(self) -> None:
        await self.perform_action()

    def action_no(self) -> None:
        self.action_back()

    def action_back(self) -> None:
        if not self.switcher.current == "resource" and not self.switcher.current == "action":
            return
        self.switcher.current = "tree"
        self.tree.focus()

    def action_select(self) -> None:
        if not self.switcher.current == "tree":
            return
        self.tree.select_current_node()

    def action_destroy(self) -> None:
        if not self.switcher.current == "tree":
            return

    def action_taint_untaint(self, what_to_do: str) -> None:
        if not self.switcher.current == "tree":
            return
        if not self.tree.selected_nodes:
            return
        self.selected_action = what_to_do
        self.question.clear()
        resources = [f"{node.parent.data}.{node.label.plain[:-4]}".lstrip('.') for node in self.tree.selected_nodes]
        self.question.write(f"Are you sure you wish to {what_to_do} the selected resources?\n\n - " +
                            "\n - ".join(resources))
        self.switcher.current = "action"

    def action_taint(self) -> None:
        self.action_taint_untaint("taint")

    def action_untaint(self) -> None:
        self.action_taint_untaint("untaint")

    def action_refresh(self) -> None:
        if not self.switcher.current == "tree":
            return
        self.tree.refresh_state()

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
