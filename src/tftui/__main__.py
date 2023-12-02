import argparse
from apis import OutboundAPIs
from state import State, Block, execute_async
from shutil import which
from textual import work
from textual.app import App, Binding
from textual.containers import Vertical, Horizontal
from textual.widgets import (
    Header,
    Footer,
    Tree,
    Input,
    RichLog as TextLog,
    LoadingIndicator,
    ContentSwitcher,
    Static,
    Button,
)

global_no_init = False
global_executable = "terraform"
global_successful_termination = True


class StateTree(Tree):
    current_node = None
    selected_nodes = []
    current_state = State(executable=global_executable, no_init=global_no_init)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.guide_depth = 3
        self.root.data = ""

    def build_tree(self, search_string="") -> None:
        self.clear()
        self.selected_nodes = []
        self.current_node = None
        module_nodes = {}

        filtered_blocks = dict(
            filter(
                lambda block: search_string in block[1].contents,
                self.current_state.state_tree.items(),
            )
        )
        modules = {
            block.submodule
            for block in filtered_blocks.values()
            if block.submodule != ""
        }

        for module_fullname in sorted(modules):
            parts = module_fullname.split(".")
            submodule = ""
            i = 0
            while i < len(parts):
                parent = submodule
                short_name = f"{parts[i]}.{parts[i+1]}"
                submodule = (
                    ".".join([submodule, short_name]) if submodule else short_name
                )
                if submodule not in module_nodes:
                    if module_nodes.get(parent) is None:
                        parent_node = self.root
                    else:
                        parent_node = module_nodes[parent]
                    node = parent_node.add(short_name, data=submodule)
                    module_nodes[submodule] = node
                i += 2

        # build resource tree
        for block in filtered_blocks.values():
            if block.submodule == "":
                module_node = self.root
            else:
                module_node = module_nodes[block.submodule]
            leaf = module_node.add_leaf(block.name, data=block)
            if block.is_tainted:
                leaf.label.stylize("strike")

        self.root.expand_all()
        self.app.switcher.current = "tree"

    @work(exclusive=True)
    async def refresh_state(self) -> None:
        global global_successful_termination

        self.app.switcher.current = "loading"
        self.app.update_status(f"Running {global_executable.capitalize()} show")
        self.app.search.value = ""
        try:
            await self.current_state.refresh_state()
        except Exception as e:
            self.app.exit(e)
            global_successful_termination = False
            return

        self.build_tree()
        self.app.tree.focus()
        self.app.update_status("")
        OutboundAPIs.post_usage("refreshed state")

    def on_tree_node_highlighted(self, node) -> None:
        self.current_node = node.node

    def on_tree_node_selected(self) -> None:
        if not self.current_node.allow_expand:
            self.app.resource.clear()
            self.app.resource.write(self.current_node.data.contents)
            self.app.switcher.current = "resource"

    def select_current_node(self) -> None:
        if self.current_node is None:
            return
        if (
            self.current_node.allow_expand
            or self.current_node.data.type == Block.TYPE_DATASOURCE
        ):
            return
        if self.current_node in self.selected_nodes:
            self.selected_nodes.remove(self.current_node)
            self.current_node.label = self.current_node.label.plain
            if self.current_node.data.is_tainted:
                self.current_node.label.stylize("strike")
        else:
            self.selected_nodes.append(self.current_node)
            self.current_node.label.stylize("red bold italic reverse")


class TerraformTUI(App):
    status = None
    switcher = None
    tree = None
    resource = None
    question = None
    action = None
    search = None
    selected_action = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    TITLE = f"Terraform TUI v{OutboundAPIs.version}"
    SUB_TITLE = f"The textual UI for Terraform{' (new version available)' if OutboundAPIs.is_new_version_available else ''}"
    CSS_PATH = "ui.css"

    BINDINGS = [
        ("Enter", "", "View"),
        Binding("escape", "back", "Back"),
        ("s", "select", "Select"),
        ("d", "delete", "Delete"),
        ("t", "taint", "Taint"),
        ("u", "untaint", "Untaint"),
        ("r", "refresh", "Refresh"),
        ("/", "search", "Search"),
        ("1-9", "collapse", "Collapse"),
        ("m", "toggle_dark", "Dark mode"),
        Binding("y", "yes", "Yes", show=False),
        Binding("n", "no", "No", show=False),
        ("q", "quit", "Quit"),
    ] + [Binding(f"{i}", f"collapse({i})", show=False) for i in range(10)]

    def compose(self):
        yield Header(classes="header")
        yield Input(id="search", placeholder="Search text...")
        with ContentSwitcher(id="switcher", initial="loading"):
            yield LoadingIndicator(id="loading")
            yield StateTree("State", id="tree")
            yield TextLog(
                id="resource",
                highlight=True,
                markup=True,
                wrap=True,
                classes="resource",
                auto_scroll=False,
            )
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
        self.search = self.get_widget_by_id("search")

    async def on_ready(self) -> None:
        self.tree.refresh_state()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "yes":
            await self.perform_action()
        elif event.button.id == "no":
            self.action_no()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search":
            search_string = event.value.strip()
            self.perform_search(search_string)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.tree.focus()

    async def manipulate_resources(self, what_to_do: str) -> None:
        for node in self.tree.selected_nodes:
            await execute_async(
                global_executable,
                (what_to_do if what_to_do != "delete" else "state rm"),
                ".".join([node.data.submodule, node.data.name])
                if node.data.submodule
                else node.data.name,
            )

    async def perform_action(self) -> None:
        if self.switcher.current != "action":
            return
        if self.selected_action in ["taint", "untaint", "delete"]:
            self.update_status(
                f"Executing {global_executable.capitalize()} {self.selected_action}"
            )
            self.switcher.current = "loading"
            await self.manipulate_resources(self.selected_action)
            OutboundAPIs.post_usage(f"applied {self.selected_action}")
        self.tree.refresh_state()

    def update_status(self, message: str) -> None:
        self.status.update(f"\n{message}")

    def perform_search(self, search_string: str) -> None:
        self.tree.root.collapse_all()
        self.tree.build_tree(search_string)
        self.tree.root.expand()

    async def action_yes(self) -> None:
        await self.perform_action()

    def action_no(self) -> None:
        self.action_back()

    def action_back(self) -> None:
        if (
            not self.switcher.current == "resource"
            and not self.switcher.current == "action"
            and not self.focused.id == "search"
        ):
            return
        self.switcher.current = "tree"
        self.tree.focus()

    def action_select(self) -> None:
        if not self.switcher.current == "tree":
            return
        self.tree.select_current_node()

    def action_manipulate_resources(self, what_to_do: str) -> None:
        if not self.switcher.current == "tree":
            return
        if not self.tree.selected_nodes:
            return
        self.selected_action = what_to_do
        self.question.clear()
        resources = [
            f"{node.parent.data}.{node.label.plain}".lstrip(".")
            for node in self.tree.selected_nodes
        ]
        self.question.write(
            f"Are you sure you wish to {what_to_do} the selected resources?\n\n - "
            + "\n - ".join(resources)
        )
        self.switcher.current = "action"

    def action_delete(self) -> None:
        self.action_manipulate_resources("delete")

    def action_taint(self) -> None:
        self.action_manipulate_resources("taint")

    def action_untaint(self) -> None:
        self.action_manipulate_resources("untaint")

    def action_refresh(self) -> None:
        if not self.switcher.current == "tree":
            return
        self.tree.refresh_state()
        OutboundAPIs.post_usage("refreshed state")

    def action_toggle_dark(self) -> None:
        self.dark = not self.dark

    def expand_node(self, level, node) -> None:
        if not node.allow_expand:
            return
        cnt = node.data.count(".module.") + 1
        if level <= cnt:
            return
        for child in node.children:
            self.expand_node(level, child)
        node.expand()

    def action_collapse(self, level=0) -> None:
        if not self.switcher.current == "tree":
            return
        if level == 0:
            self.tree.root.expand_all()
            return
        self.tree.root.collapse_all()
        for node in self.tree.root.children:
            self.expand_node(level, node)
        self.tree.root.expand()

    def action_search(self) -> None:
        self.switcher.current = "tree"
        self.search.focus()


def parse_command_line() -> None:
    global global_no_init
    global global_executable

    parser = argparse.ArgumentParser(
        prog="tftui", description="TFTUI - the Terraform terminal UI", epilog="Enjoy!"
    )
    parser.add_argument(
        "-e", "--executable", help="set executable command (default 'terraform')"
    )
    parser.add_argument(
        "-n",
        "--no-init",
        help="do not run terraform init on startup (default run)",
        action="store_true",
    )
    parser.add_argument(
        "-d",
        "--disable-usage-tracking",
        help="disable usage tracking (default enabled)",
        action="store_true",
    )
    parser.add_argument(
        "-v", "--version", help="show version information", action="store_true"
    )

    args = parser.parse_args()

    if args.version:
        print(
            f"\ntftui v{OutboundAPIs.version}{' (new version available)' if OutboundAPIs.is_new_version_available else ''}\n"
        )
        exit(0)
    if args.no_init:
        global_no_init = True
    if args.disable_usage_tracking:
        OutboundAPIs.disable_usage_tracking()
    if args.executable:
        global_executable = args.executable

    if which(global_executable) is None and which(f"{global_executable}.exe") is None:
        print(
            f"Executable '{global_executable}' not found. Please install and try again."
        )
        exit(1)


def main() -> None:
    global global_successful_termination

    parse_command_line()
    OutboundAPIs.post_usage("started application")

    app = TerraformTUI()
    result = app.run()
    if result is not None:
        print(result)
    if global_successful_termination:
        OutboundAPIs.post_usage("exited successfully")
    else:
        OutboundAPIs.post_usage("exited unsuccessfully")

    print(
        f"\nBye!{' Also, new version available.' if OutboundAPIs.is_new_version_available else ''}\n"
    )


if __name__ == "__main__":
    main()
