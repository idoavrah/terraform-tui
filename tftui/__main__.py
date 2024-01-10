import argparse
import pyperclip
import os
import platform
import json
import traceback
import re
from rich.text import Text
from shutil import which
from tftui.apis import OutboundAPIs
from tftui.state import State, Block, execute_async, split_resource_name
from tftui.plan import PlanScreen
from tftui.debug_log import setup_logging
from tftui.modal import HelpModal, YesNoModal, PlanInputsModal
from textual import work
from textual.app import App, Binding
from textual.containers import Horizontal
from textual.screen import ModalScreen
from textual.widgets import (
    Footer,
    Tree,
    Input,
    Static,
    RichLog as TextLog,
    ContentSwitcher,
)

logger = setup_logging()


class ApplicationGlobals:
    executable = "terraform"
    successful_termination = True
    no_init = False
    darkmode = True
    var_file = None


class AppHeader(Horizontal):
    LOGO = r""" ______   ______   ______   __  __    __
/\__  _\ /\  ___\ /\__  _\ /\ \/\ \  /\ \
\/_/\ \/ \ \  __\ \/_/\ \/ \ \ \_\ \ \ \ \
   \ \_\  \ \_\      \ \_\  \ \_____\ \ \_\
    \/_/   \/_/       \/_/   \/_____/  \/_/
"""

    TITLES = """
TFTUI Version:\n
Working folder:\n
"""

    INFO = f"""
{OutboundAPIs.version}{' (new version available)' if OutboundAPIs.is_new_version_available else ''}\n
{os.getcwd()}\n
"""

    BORDER_TITLE = "TFTUI - the Terraform terminal user interface"

    def compose(self):
        yield Static(AppHeader.TITLES, classes="header-box")
        yield Static(AppHeader.INFO, classes="header-box")
        yield Static(AppHeader.LOGO, classes="header-box")


class StateTree(Tree):
    current_node = None
    highlighted_resource_node = []
    selected_nodes = []
    current_state = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_state = State(
            executable=ApplicationGlobals.executable, no_init=ApplicationGlobals.no_init
        )
        self.guide_depth = 3
        self.root.data = ""

    def build_tree(self, search_string="") -> None:
        self.clear()
        self.selected_nodes = []
        self.current_node = None
        module_nodes = {}

        filtered_blocks = dict(
            filter(
                lambda block: search_string in block[1].contents
                or search_string in block[1].name
                or search_string in block[1].submodule,
                self.current_state.state_tree.items(),
            )
        )
        modules = {
            block.submodule
            for block in filtered_blocks.values()
            if block.submodule != ""
        }

        logger.debug(
            "Filter tree: %s",
            json.dumps(
                {
                    "search string": search_string,
                    "filtered blocks": len(filtered_blocks),
                    "filtered modules": len(modules),
                },
                indent=2,
            ),
        )

        for module_fullname in sorted(modules):
            parts = split_resource_name(module_fullname)
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
                leaf.label.stylize("gold3 strike")

        self.root.expand_all()

    @work(exclusive=True)
    async def refresh_state(self, focus=True) -> None:
        self.loading = True
        self.app.notify("Refreshing state tree")
        self.app.search.value = ""
        try:
            await self.current_state.refresh_state()
        except Exception as e:
            ApplicationGlobals.successful_termination = False
            self.app.exit(e)
            return

        self.build_tree()
        self.current_node = self.get_node_at_line(min(self.cursor_line, self.last_line))
        self.update_highlighted_resource_node(self.current_node)
        self.loading = False
        OutboundAPIs.post_usage("refreshed state")
        if focus:
            self.focus()

    def update_highlighted_resource_node(self, node) -> None:
        self.current_node = node
        if type(self.current_node.data) == Block:
            self.highlighted_resource_node = (
                [node] if self.current_node.data.type == Block.TYPE_RESOURCE else []
            )
        else:
            self.highlighted_resource_node = []

    def on_tree_node_highlighted(self, node) -> None:
        self.update_highlighted_resource_node(node.node)

    def on_tree_node_selected(self) -> None:
        if not self.current_node:
            return
        if not self.current_node.allow_expand:
            self.app.resource.clear()
            self.app.resource.write(self.current_node.data.contents)
            self.app.switcher.border_title = (
                f"{self.current_node.data.submodule}.{self.current_node.data.name}"
                if self.current_node.data.submodule
                else self.current_node.data.name
            )
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
                self.current_node.label.stylize("gold3 strike")
        else:
            self.selected_nodes.append(self.current_node)
            self.current_node.label.stylize("red bold italic reverse")


class TerraformTUI(App):
    switcher = None
    tree = None
    resource = None
    search = None
    plan = None
    selected_action = None
    error_message = ""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dark = ApplicationGlobals.darkmode

    TITLE = f"Terraform TUI v{OutboundAPIs.version}"
    SUB_TITLE = f"The textual UI for Terraform{' (new version available)' if OutboundAPIs.is_new_version_available else ''}"
    CSS_PATH = "ui.tcss"

    BINDINGS = [
        ("Enter", "", "View"),
        Binding("escape", "back", "Back"),
        ("s", "select", "Select"),
        Binding("spacebar", "select", "Select"),
        ("d", "delete", "Delete"),
        ("t", "taint", "Taint"),
        ("u", "untaint", "Untaint"),
        ("c", "copy", "Copy"),
        ("r", "refresh", "Refresh"),
        ("p", "plan", "Plan"),
        ("a", "apply", "Apply"),
        ("ctrl+d", "destroy", "Destroy"),
        ("/", "search", "Search"),
        ("0-9", "collapse", "Collapse"),
        ("m", "toggle_dark", "Dark mode"),
        ("h", "help", "Help"),
        ("q", "quit", "Quit"),
    ] + [Binding(f"{i}", f"collapse({i})", show=False) for i in range(10)]

    def compose(self):
        yield AppHeader(id="header")
        yield Input(id="search", placeholder="Search text...")
        with ContentSwitcher(id="switcher", initial="tree"):
            yield StateTree("State", id="tree")
            yield TextLog(
                id="resource",
                highlight=True,
                markup=True,
                wrap=True,
                classes="resource",
                auto_scroll=False,
            )
            yield PlanScreen(id="plan", executable=ApplicationGlobals.executable)
        yield Footer()

    def on_mount(self) -> None:
        self.resource = self.get_widget_by_id("resource")
        self.tree = self.get_widget_by_id("tree")
        self.switcher = self.get_widget_by_id("switcher")
        self.search = self.get_widget_by_id("search")
        self.plan = self.get_widget_by_id("plan")

    def on_ready(self) -> None:
        self.tree.refresh_state()

    def on_input_changed(self, event: Input.Changed) -> None:
        if self.app.search.value == "":
            return
        elif self.app.tree.loading:
            self.app.search.value = ""
            self.app.notify(
                "Please wait until state refresh is complete", severity="warning"
            )
        elif event.input.id == "search":
            search_string = event.value.strip()
            self.perform_search(search_string)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if self.switcher.current == "tree":
            self.tree.focus()

    def on_key(self, event) -> None:
        if not self.tree.has_focus or isinstance(self.screen, ModalScreen):
            return
        if event.key == "space":
            self.action_select()
        elif event.key == "left" and self.switcher.current == "tree":
            if self.tree.current_node is not None:
                if (
                    self.tree.current_node.allow_expand
                    and self.tree.current_node.is_expanded
                ):
                    self.tree.current_node.collapse()
                elif self.tree.current_node.parent is not None:
                    self.tree.current_node = self.tree.current_node.parent
                    self.tree.select_node(self.tree.current_node)
                    self.tree.scroll_to_node(self.tree.current_node)

        elif event.key == "right" and self.switcher.current == "tree":
            if self.tree.current_node is not None:
                if (
                    self.tree.current_node.allow_expand
                    and not self.tree.current_node.is_expanded
                ):
                    self.tree.current_node.expand()
                else:
                    if (
                        self.tree.get_node_at_line(self.tree.cursor_line + 1)
                        is not None
                    ):
                        self.tree.current_node = self.tree.get_node_at_line(
                            self.tree.cursor_line + 1
                        )
                        self.tree.select_node(self.tree.current_node)
                        self.tree.scroll_to_node(self.tree.current_node)

    async def manipulate_resources(self, what_to_do: str) -> None:
        nodes = (
            self.tree.selected_nodes
            if self.tree.selected_nodes
            else self.tree.highlighted_resource_node
        )
        for node in nodes:
            await execute_async(
                ApplicationGlobals.executable,
                (what_to_do if what_to_do != "delete" else "state rm"),
                ".".join([node.data.submodule, node.data.name])
                if node.data.submodule
                else node.data.name,
            )

    async def perform_action(self) -> None:
        if self.selected_action in ["taint", "untaint", "delete"]:
            self.switcher.loading = True
            self.notify(
                f"Executing {ApplicationGlobals.executable.capitalize()} {self.selected_action}"
            )
            await self.manipulate_resources(self.selected_action)
            OutboundAPIs.post_usage(f"applied {self.selected_action}")
            self.tree.refresh_state()
            self.tree.focus()
            self.switcher.loading = False

    def perform_search(self, search_string: str) -> None:
        self.tree.root.collapse_all()
        self.tree.build_tree(search_string)
        self.tree.root.expand()

    def action_back(self) -> None:
        if (
            not self.switcher.current == "resource"
            and not self.switcher.current == "plan"
            and not self.focused.id == "search"
        ):
            return
        self.switcher.current = "tree"
        self.app.switcher.border_title = ""
        self.tree.focus()

    async def create_plan(self, destroy="") -> None:
        self.switcher.current = "plan"

        async def execute(response):
            if response is not None:
                self.notify(f"Creating {destroy} plan")
                targets = []
                if response[1]:
                    if self.tree.selected_nodes:
                        targets = [
                            f"{node.parent.data}.{node.label.plain}".lstrip(".")
                            for node in self.tree.selected_nodes
                        ]
                    else:
                        targets = [
                            f"{node.parent.data}.{node.label.plain}".lstrip(".")
                            for node in self.tree.highlighted_resource_node
                        ]
                self.plan.create_plan(response[0], targets, destroy)
                OutboundAPIs.post_usage(
                    f"create {'targeted' if targets else ''} {destroy} plan"
                )
            else:
                self.switcher.current = "tree"

        self.push_screen(
            PlanInputsModal(
                ApplicationGlobals.var_file,
                len(self.tree.selected_nodes) > 0,
            ),
            execute,
        )
        self.plan.focus()

    async def action_plan(self) -> None:
        await self.create_plan()

    async def action_destroy(self) -> None:
        await self.create_plan("destruction")

    async def action_apply(self) -> None:
        if not self.plan.active_plan:
            self.app.notify("No active plan to apply", severity="warning")
            return

        question = Text.assemble(
            ("Are you sure you wish to apply the current plan?\n\n", "bold"),
            self.plan.active_plan,
        )

        async def execute_if_yes(flag):
            if flag:
                self.switcher.loading = True
                self.notify("Applying plan")
                OutboundAPIs.post_usage("apply plan")
                logger.debug("Applying plan %s", self.plan.active_plan)
                self.plan.execute_apply()

        self.push_screen(YesNoModal(question), execute_if_yes)
        self.plan.focus()

    def action_select(self) -> None:
        if not self.switcher.current == "tree":
            return
        self.tree.select_current_node()

    async def action_manipulate_resources(self, what_to_do: str) -> None:
        if not self.switcher.current == "tree":
            return
        nodes = (
            self.tree.selected_nodes
            if self.tree.selected_nodes
            else self.tree.highlighted_resource_node
        )

        if nodes:
            self.selected_action = what_to_do
            resources = [
                f"{node.parent.data}.{node.label.plain}".lstrip(".") for node in nodes
            ]

            question = Text.assemble(
                ("Are you sure you wish to ", "bold"),
                (what_to_do, "bold red"),
                (" the selected resources?\n\n - ", "bold"),
                ("\n - ".join(resources)),
            )

            async def execute_if_yes(flag):
                if flag:
                    await self.perform_action()

            self.push_screen(YesNoModal(question), execute_if_yes)

    async def action_delete(self) -> None:
        await self.action_manipulate_resources("delete")

    async def action_taint(self) -> None:
        await self.action_manipulate_resources("taint")

    async def action_untaint(self) -> None:
        await self.action_manipulate_resources("untaint")

    def action_copy(self) -> None:
        if self.switcher.current == "resource":
            pyperclip.copy(self.app.tree.current_node.data.contents)
            self.notify("Copied resource definition to clipboard")
        elif self.switcher.current == "tree":
            pyperclip.copy(self.app.tree.current_node.label.plain)
            self.notify("Copied resource name to clipboard")

    def action_refresh(self) -> None:
        self.switcher.current = "tree"
        self.tree.refresh_state()

    def action_help(self) -> None:
        self.push_screen(HelpModal())

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
        else:
            self.tree.root.collapse_all()
            for node in self.tree.root.children:
                self.expand_node(level, node)
            self.tree.root.expand()

    def action_search(self) -> None:
        self.switcher.border_title = ""
        self.switcher.current = "tree"
        self.search.focus()

    def _handle_exception(self, exception: Exception) -> None:
        self.error_message = "".join(
            traceback.format_exception(
                type(exception), exception, exception.__traceback__
            )
        )
        super()._handle_exception(exception)

    def _on_resize(self, event):
        main_height = max(event.size.height - 11, 5)
        self.switcher.styles.height = main_height
        logger.debug("Main height: %s", main_height)
        OutboundAPIs.post_usage(
            "app resize", size=f"{event.size.width}x{event.size.height}"
        )
        super()._on_resize(event)


def parse_command_line() -> None:
    parser = argparse.ArgumentParser(
        prog="tftui",
        description="TFTUI - the Terraform terminal UI",
        epilog="Enjoy!",
    )
    parser.add_argument(
        "-e",
        "--executable",
        help="set executable command (default 'terraform')",
    )
    parser.add_argument(
        "-n",
        "--no-init",
        help="do not run terraform init on startup (default run)",
        action="store_true",
    )
    parser.add_argument(
        "-f",
        "--var-file",
        help="tfvars filename to be used in planning",
    )
    parser.add_argument(
        "-d",
        "--disable-usage-tracking",
        help="disable usage tracking (default enabled)",
        action="store_true",
    )
    parser.add_argument(
        "-l",
        "--light-mode",
        help="enable light mode (default dark)",
        action="store_true",
    )
    parser.add_argument(
        "-g",
        "--generate-debug-log",
        action="store_true",
        help="generate debug log file (default disabled)",
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
    if args.disable_usage_tracking:
        OutboundAPIs.disable_usage_tracking()
    if args.executable:
        ApplicationGlobals.executable = args.executable
    if args.var_file:
        ApplicationGlobals.var_file = args.var_file
    if args.generate_debug_log:
        logger = setup_logging("debug")
        logger.debug("*" * 50)
        logger.debug(f"Debug log enabled (tftui v{OutboundAPIs.version})")
    ApplicationGlobals.darkmode = not args.light_mode
    if (
        which(ApplicationGlobals.executable) is None
        and which(f"{ApplicationGlobals.executable}.exe") is None
    ):
        print(
            f"Executable '{ApplicationGlobals.executable}' not found. Please install and try again."
        )
        exit(1)


def main() -> None:
    parse_command_line()
    OutboundAPIs.post_usage("started application", platform=platform.platform())

    result = ""
    try:
        app = TerraformTUI()
        result = app.run()
    finally:
        if app.return_code > 0:
            ApplicationGlobals.successful_termination = False

    if result is not None:
        print(result)
    if ApplicationGlobals.successful_termination:
        OutboundAPIs.post_usage("exited successfully")
    else:
        error_message = re.sub(
            r"(?<=[/\\])[^\s/\\]+(?=[/\\])",
            "***",
            app.error_message or str(result).strip(),
        ).split("\n")
        logger.debug(error_message)
        OutboundAPIs.post_usage("exited unsuccessfully", error_message=error_message)

    if OutboundAPIs.is_new_version_available:
        print("\n*** New version available. ***")

    print(
        """
For questions and suggestions, please visit https://github.com/idoavrah/terraform-tui/discussions
For issues and bugs, please visit https://github.com/idoavrah/terraform-tui/issues

Bye!
"""
    )


if __name__ == "__main__":
    main()
