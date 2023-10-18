import asyncio
import argparse
import uuid
import importlib.metadata
import requests
from textual import work
from textual.app import App, ComposeResult, Binding
from textual.containers import Vertical, Horizontal
from shutil import which
from posthog import Posthog
from textual.widgets import (
    Header,
    Footer,
    Tree,
    RichLog as TextLog,
    LoadingIndicator,
    ContentSwitcher,
    Static,
    Button,
)

version = importlib.metadata.version("tftui")
global_no_init = False
global_executable = "terraform"
global_successful_termination = True


class OutboundAPIs:
    is_new_version_available = False
    is_usage_tracking_enabled = True
    session_id = uuid.uuid4()
    posthog = Posthog(
        project_api_key="phc_tjGzx7V6Y85JdNfOFWxQLXo5wtUs6MeVLvoVfybqz09",
        host="https://app.posthog.com",
        disable_geoip=False,
    )

    response = requests.get("https://pypi.org/pypi/tftui/json")
    if response.status_code == 200:
        ver = response.json()["info"]["version"]
        if ver != version:
            is_new_version_available = True

    @staticmethod
    def post_usage(message: str) -> None:
        if OutboundAPIs.is_usage_tracking_enabled:
            OutboundAPIs.posthog.capture(
                OutboundAPIs.session_id, message, {"tftui_version": version}
            )

    @staticmethod
    def disable_usage_tracking() -> None:
        OutboundAPIs.is_usage_tracking_enabled = False


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
        if self.current_node.data.startswith("module") or self.current_node.is_root:
            return
        self.app.resource.clear()
        self.app.resource.write(self.current_node.data)
        self.app.switcher.current = "resource"

    def select_current_node(self) -> None:
        if self.current_node is None:
            return
        if (
            self.current_node.data.startswith("module")
            or self.current_node.data.startswith("data")
            or self.current_node.is_root
        ):
            return
        if self.current_node in self.selected_nodes:
            self.selected_nodes.remove(self.current_node)
            self.current_node.label = self.current_node.label.plain
        else:
            self.selected_nodes.append(self.current_node)
            self.current_node.label.stylize("red bold italic reverse")

    @work(exclusive=True)
    async def refresh_state(self) -> None:
        global global_successful_termination

        self.app.switcher.current = "loading"
        self.selected_nodes = []
        self.current_node = None
        self.clear()

        if not global_no_init:
            self.app.status.update(f"Executing {global_executable.capitalize()} init")
            returncode, stdout = await execute_async(
                global_executable, "init", "-no-color"
            )
            if returncode != 0:
                self.app.exit(message=stdout)
                global_successful_termination = False
                return

        self.app.status.update(f"Executing {global_executable.capitalize()} show")

        returncode, stdout = await execute_async(global_executable, "show", "-no-color")
        if returncode != 0 or not stdout.startswith("#"):
            self.app.exit(message=stdout)
            global_successful_termination = False
            return

        self.app.status.update("Building state tree")
        lines = stdout.splitlines()

        # build module tree
        modules = set()
        module_nodes = {}
        for line in lines:
            if not line.startswith("# module"):
                continue
            parts = line[2:-1].split(".")
            i = 0
            module = ""
            while parts[i] == "module":
                module += f"{parts[i]}.{parts[i+1]}."
                modules.add(module[:-1])
                i += 2

        for module_fullname in sorted(modules):
            parts = module_fullname.split(".")
            sub_module = ""
            i = 0
            while i < len(parts):
                parent = sub_module
                short_name = f"{parts[i]}.{parts[i+1]}."
                sub_module += short_name
                if sub_module[:-1] not in module_nodes:
                    if module_nodes.get(parent[:-1]) is None:
                        parent_node = self.root
                    else:
                        parent_node = module_nodes[parent[:-1]]
                    node = parent_node.add(short_name[:-1], data=sub_module[:-1])
                    module_nodes[sub_module[:-1]] = node
                i += 2

        # parse objects
        name = ""
        for line in lines:
            if line.startswith("#"):
                parts = line[2:].split(".")
                i = 0
                qualifier = ""
                while parts[i] == "module":
                    qualifier += f"{parts[i]}.{parts[i+1]}."
                    i += 2
                name = ".".join(parts[i:]).replace(":", "")
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
        OutboundAPIs.post_usage("refreshed state")


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

    TITLE = f"Terraform TUI v{version}"
    SUB_TITLE = f"The textual UI for Terraform{' (new version available)' if OutboundAPIs.is_new_version_available else ''}"
    CSS_PATH = "ui.css"

    BINDINGS = [
        ("Enter", "", "View state"),
        Binding("escape", "back", "Back"),
        ("s", "select", "Select"),
        ("t", "taint", "Taint"),
        ("u", "untaint", "Untaint"),
        ("r", "refresh", "Refresh state"),
        ("1-9", "collapse", "Collapse level"),
        ("m", "toggle_dark", "Toggle dark mode"),
        Binding("y", "yes", "Yes", show=False),
        Binding("n", "no", "No", show=False),
        ("q", "quit", "Quit"),
    ] + [Binding(f"{i}", f"collapse({i})", show=False) for i in range(10)]

    def compose(self) -> ComposeResult:
        yield Header(classes="header")
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

    async def on_ready(self) -> None:
        self.tree.refresh_state()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "yes":
            await self.perform_action()
        elif event.button.id == "no":
            self.action_no()

    async def perform_taint_untaint(self, what_to_do: str) -> None:
        resources = [
            f"{node.parent.data}.{node.label.plain}".lstrip(".").replace(
                " (tainted)", ""
            )
            for node in self.tree.selected_nodes
        ]
        for resource in resources:
            await execute_async(global_executable, what_to_do, resource)

    async def perform_action(self) -> None:
        if self.switcher.current != "action":
            return
        if self.selected_action == "taint" or self.selected_action == "untaint":
            self.status.update(
                f"Executing {global_executable.capitalize()} {self.selected_action}"
            )
            self.switcher.current = "loading"
            await self.perform_taint_untaint(self.selected_action)
        self.tree.refresh_state()

    async def action_yes(self) -> None:
        await self.perform_action()

    def action_no(self) -> None:
        self.action_back()

    def action_back(self) -> None:
        if (
            not self.switcher.current == "resource"
            and not self.switcher.current == "action"
        ):
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
        resources = [
            f"{node.parent.data}.{node.label.plain}".lstrip(".")
            for node in self.tree.selected_nodes
        ]
        self.question.write(
            f"Are you sure you wish to {what_to_do} the selected resources?\n\n - "
            + "\n - ".join(resources)
        )
        self.switcher.current = "action"

    def action_taint(self) -> None:
        self.action_taint_untaint("taint")
        OutboundAPIs.post_usage("applied taint")

    def action_untaint(self) -> None:
        self.action_taint_untaint("untaint")
        OutboundAPIs.post_usage("applied untaint")

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


async def execute_async(*command: str) -> tuple[str, str]:
    proc = await asyncio.create_subprocess_exec(
        *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )

    stdout, strerr = await proc.communicate()
    response = stdout.decode("utf-8")

    return (proc.returncode, response)


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
            f"\ntftui v{version}{' (new version available)' if OutboundAPIs.is_new_version_available else ''}\n"
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
