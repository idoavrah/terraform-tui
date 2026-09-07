"""The tftui application."""

from __future__ import annotations

import traceback
from collections.abc import Sequence
from typing import ClassVar

from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.widgets import ContentSwitcher, Footer, Input, Tree

from tftui.config import Settings
from tftui.errors import TftuiError
from tftui.logging_setup import get_logger
from tftui.screens.confirm import ConfirmScreen
from tftui.screens.fulltext import FullTextScreen
from tftui.screens.help import HelpScreen
from tftui.screens.plan_inputs import PlanInputsScreen, PlanRequest
from tftui.screens.workspace import WorkspaceScreen
from tftui.telemetry import NullTelemetry, Telemetry
from tftui.terraform.client import DELETE, TAINT, UNTAINT, Operation, TerraformClient
from tftui.terraform.state import Resource
from tftui.version import __version__
from tftui.widgets.header import AppHeader
from tftui.widgets.plan_view import PlanView
from tftui.widgets.resource_view import ResourceView
from tftui.widgets.searchable_log import SearchableLog
from tftui.widgets.state_tree import NodeData, StateTree

logger = get_logger("app")

TREE = "tree"
RESOURCE = "resource"
PLAN = "plan"

_SEARCH_PLACEHOLDER = {
    TREE: "Filter resources…",
    RESOURCE: "Search this resource…",
    PLAN: "Search the plan…",
}

DARK_THEME = "textual-dark"
LIGHT_THEME = "textual-light"

_OPERATION_LABELS: dict[Operation, str] = {
    TAINT: "taint",
    UNTAINT: "untaint",
    DELETE: "remove from state",
}


class TerraformTUI(App[str]):
    """Browse and act on Terraform state."""

    CSS_PATH = "ui.tcss"
    TITLE = "Terraform TUI"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "go_back", "Back", show=False),
        Binding("space", "noop", "Select", show=False),
        Binding("f", "fullscreen", "Full"),
        Binding("d", "delete", "Delete"),
        Binding("t", "taint", "Taint"),
        Binding("u", "untaint", "Untaint"),
        Binding("c", "copy", "Copy"),
        Binding("r", "reload", "Reload"),
        Binding("p", "plan", "Plan"),
        Binding("a", "apply", "Apply"),
        Binding("ctrl+d", "destroy", "Destroy"),
        Binding("slash", "search", "Search", key_display="/"),
        Binding("0", "collapse(0)", "Collapse", key_display="0-9"),
        Binding("w", "workspaces", "Workspace"),
        Binding("x", "sensitive", "Secrets"),
        Binding("m", "toggle_theme", "Theme"),
        Binding("question_mark", "help", "Help", key_display="?"),
        Binding("q", "quit", "Quit"),
        Binding("ctrl+a", "clear_selection", "Clear selection", show=False),
        Binding("n", "next_match", "Next match", show=False),
        Binding("N", "previous_match", "Previous match", show=False),
        *[Binding(str(level), f"collapse({level})", show=False) for level in range(1, 10)],
    ]

    def __init__(
        self,
        client: TerraformClient,
        settings: Settings,
        telemetry: Telemetry | None = None,
    ) -> None:
        super().__init__()
        self.client = client
        self.settings = settings
        self.telemetry = telemetry or NullTelemetry()
        self.error_message = ""
        self._pending_operation: Operation | None = None
        #: Which pane the search box is currently driving.
        self._search_target = TREE

    # --------------------------------------------------------------- compose

    def compose(self) -> ComposeResult:
        yield AppHeader(
            version=f"{__version__}{self.telemetry.update_suffix}",
            directory=str(self.client.cwd),
            id="header",
        )
        # `select_on_focus=False`: returning to the box must let the existing
        # text be extended or corrected, not replaced by the first keystroke.
        yield Input(
            id="search",
            placeholder=_SEARCH_PLACEHOLDER[TREE],
            select_on_focus=False,
        )
        with ContentSwitcher(id="switcher", initial=TREE):
            yield StateTree("State", id=TREE)
            yield ResourceView(id=RESOURCE)
            yield PlanView(id=PLAN)
        # Compact, and without the command-palette hint: tftui has enough
        # bindings that every spare column matters.
        yield Footer(compact=True, show_command_palette=False)

    def on_mount(self) -> None:
        self.theme = LIGHT_THEME if self.settings.light_mode else DARK_THEME
        self.sub_title = f"v{__version__}{self.telemetry.update_suffix}"
        self.startup()

    # ------------------------------------------------------------- shortcuts

    @property
    def state_tree(self) -> StateTree:
        """The state tree widget.

        Deliberately not named `tree`: `DOMNode.tree` is Textual's own DOM
        debugging view, and shadowing it breaks the devtools.
        """
        return self.query_one(f"#{TREE}", StateTree)

    @property
    def resource_view(self) -> ResourceView:
        return self.query_one(f"#{RESOURCE}", ResourceView)

    @property
    def plan_view(self) -> PlanView:
        return self.query_one(f"#{PLAN}", PlanView)

    @property
    def switcher(self) -> ContentSwitcher:
        return self.query_one("#switcher", ContentSwitcher)

    @property
    def search_input(self) -> Input:
        return self.query_one("#search", Input)

    @property
    def view(self) -> str:
        return self.switcher.current or TREE

    def _show(self, view: str, title: str = "") -> None:
        self.switcher.current = view
        if view == TREE and not title:
            title = _selection_title(len(self.state_tree.selected))
        self.switcher.border_title = title

    # --------------------------------------------------------------- startup

    @work(exclusive=True, group="state")
    async def startup(self) -> None:
        """Initialise Terraform if asked to, then load the state."""
        if self.settings.run_init:
            self.state_tree.loading = True
            self.notify(f"Running {self.client.executable} init")
            result = await self.client.init(var_files=self.settings.var_files)
            if not result.ok:
                self.state_tree.loading = False
                self._fail(TftuiError(result.output))
                return

        await self._load_state()
        self.refresh_workspace()

    @work(exclusive=True, group="workspace")
    async def refresh_workspace(self) -> None:
        workspace = await self.client.current_workspace()
        self.query_one("#header", AppHeader).workspace = workspace or "unknown"

    def action_reload(self) -> None:
        self.notify("Refreshing state")
        self.reload_state()

    @work(exclusive=True, group="state")
    async def reload_state(self) -> None:
        await self._load_state()

    async def _load_state(self, *, show_tree: bool = True) -> None:
        """Reload the state into the tree.

        ``show_tree`` is false after an apply: the state has changed and the
        tree must be rebuilt, but the user is still reading the apply output
        and should not be thrown back to the tree mid-sentence.
        """
        tree = self.state_tree
        tree.loading = True
        self.search_input.value = ""
        try:
            loaded = await self.client.load_state()
        except TftuiError as error:
            tree.loading = False
            self._fail(error)
            return

        tree.load(loaded)
        tree.loading = False
        if show_tree:
            self._show(TREE)
            tree.focus()
        self.telemetry.capture("refreshed state", size=str(len(loaded.state)))

        if loaded.state.is_empty:
            self.notify(
                "No resources in state. You can still create a plan with 'p'.",
                severity="warning",
            )

    def _fail(self, error: Exception) -> None:
        """Abort with a user-facing message rather than a traceback."""
        logger.error("fatal: %s", error)
        self.exit(str(error), return_code=1)

    # ---------------------------------------------------------------- search

    @property
    def _searchable(self) -> SearchableLog | None:
        """The pane the search box drives, when it is not the tree."""
        if self._search_target == PLAN:
            return self.plan_view
        if self._search_target == RESOURCE:
            return self.resource_view
        return None

    @on(Input.Changed, "#search")
    def on_search_changed(self, event: Input.Changed) -> None:
        """Filter the tree, or highlight in place within a resource or plan."""
        pane = self._searchable
        if pane is None:
            if self.state_tree.loading:
                return
            self.state_tree.rebuild(event.value.strip())
            return

        count = pane.search(event.value)
        self.switcher.border_title = self._search_title()
        self.search_input.set_class(bool(event.value) and not count, "nomatch")

    @on(Input.Submitted, "#search")
    def on_search_submitted(self) -> None:
        """Enter hands focus to the pane so n/N and scrolling work."""
        pane = self._searchable
        (pane or self.state_tree).focus()

    def action_search(self) -> None:
        """Search the current pane: the tree filters, the others highlight."""
        target = self.view if self.view in (RESOURCE, PLAN) else TREE
        if target == TREE:
            self._show(TREE)

        # Re-entering the search box must keep what is already typed, so it can
        # be extended or corrected. The text only means something within one
        # pane, so switching panes starts afresh.
        if target != self._search_target:
            self._clear_search()
            self._search_target = target
        self.search_input.placeholder = _SEARCH_PLACEHOLDER[target]
        self.search_input.focus()

    def action_next_match(self) -> None:
        self._step_match(1)

    def action_previous_match(self) -> None:
        self._step_match(-1)

    def _step_match(self, delta: int) -> None:
        pane = self._searchable
        if pane is None or not pane.match_count:
            return
        pane.step_match(delta)
        self.switcher.border_title = self._search_title()

    def _search_title(self) -> str:
        """The pane title, with the search position appended while searching."""
        pane = self._searchable
        title = pane.title if pane is not None else ""
        if pane is None or not pane.needle:
            return title
        if not pane.match_count:
            return f"{title}  -  no match"
        return f"{title}  -  match {pane.match_position}/{pane.match_count}"

    def _clear_search(self) -> None:
        """Drop any in-pane search, in whichever pane owns it."""
        pane = self._searchable
        if pane is not None:
            pane.clear_search()
        self._search_target = TREE
        self.search_input.value = ""
        self.search_input.remove_class("nomatch")
        self.search_input.placeholder = _SEARCH_PLACEHOLDER[TREE]

    # ------------------------------------------------------------------ tree

    @on(StateTree.NodeSelected)
    def on_node_selected(self, event: Tree.NodeSelected[NodeData]) -> None:
        resource = event.node.data
        if not isinstance(resource, Resource):
            return
        secrets = self.state_tree.loaded.secrets_for(resource.full_address)
        if self._search_target == RESOURCE:
            self._clear_search()
        self.resource_view.show(resource, secrets=secrets)
        self._show(RESOURCE, resource.full_address)

    @on(StateTree.SelectionChanged)
    def on_selection_changed(self, event: StateTree.SelectionChanged) -> None:
        """Show the selection count on the pane border.

        There is no Textual `Header` in this layout, so `sub_title` only ever
        reaches the terminal's own title bar. Selecting a whole module can pick
        up dozens of resources, most of them scrolled out of sight, so the count
        needs somewhere on screen to live.
        """
        self.sub_title = (
            f"v{__version__}{self.telemetry.update_suffix}"
            if not event.count
            else f"{event.count} selected"
        )
        if self.view == TREE:
            self.switcher.border_title = _selection_title(event.count)

    def action_noop(self) -> None:
        """Placeholder so Space shows in the footer; the tree handles the key."""

    def action_clear_selection(self) -> None:
        self.state_tree.clear_selection()

    def action_collapse(self, level: int = 0) -> None:
        if self.view != TREE:
            return
        self.state_tree.collapse_to(level)

    def action_go_back(self) -> None:
        if self.focused is self.search_input:
            (self._searchable or self.state_tree).focus()
            return
        if self.view == TREE:
            return
        self._clear_search()
        self._show(TREE)
        self.state_tree.focus()

    # ------------------------------------------------------------ inspection

    def action_sensitive(self) -> None:
        if self.view != RESOURCE:
            return
        view = self.resource_view
        resource = view.resource
        if resource is None:
            return
        secrets = self.state_tree.loaded.secrets_for(resource.full_address)
        if not secrets:
            self.notify("This resource has no sensitive values", severity="warning")
            return
        view.show(resource, revealed=not view.revealed, secrets=secrets)
        if view.revealed:
            self.telemetry.capture("revealed sensitive values")

    def action_fullscreen(self) -> None:
        if self.view == RESOURCE:
            self.push_screen(FullTextScreen(self.resource_view.body, syntax=True))
        elif self.view == PLAN:
            self.push_screen(FullTextScreen(self.plan_view.fulltext))

    def action_copy(self) -> None:
        payload = self._copy_payload()
        if not payload:
            return
        try:
            import pyperclip

            pyperclip.copy(payload)
        except Exception:
            self.notify("Clipboard is unavailable in this terminal", severity="warning")
            return
        self.notify("Copied to clipboard")

    def _copy_payload(self) -> str:
        if self.view == RESOURCE:
            return self.resource_view.body
        if self.view == PLAN:
            return self.plan_view.fulltext.plain
        highlighted = self.state_tree.highlighted
        return highlighted.full_address if highlighted is not None else ""

    # ------------------------------------------------------------ operations

    def action_taint(self) -> None:
        self._confirm_operation(TAINT)

    def action_untaint(self) -> None:
        self._confirm_operation(UNTAINT)

    def action_delete(self) -> None:
        self._confirm_operation(DELETE)

    def _confirm_operation(self, operation: Operation) -> None:
        if self.view != TREE:
            return
        targets = self.state_tree.targets()
        if not targets:
            self.notify("Select a resource first (data sources cannot be changed)")
            return

        label = _OPERATION_LABELS[operation]
        question = Text.assemble(
            ("Are you sure you wish to ", "bold"),
            (label, "bold red"),
            (f" {_count(len(targets))}?\n\n", "bold"),
            "\n".join(f"  - {resource.full_address}" for resource in targets),
        )
        self._pending_operation = operation
        self.push_screen(ConfirmScreen(question), self._run_operation)

    def _run_operation(self, confirmed: bool | None) -> None:
        operation = self._pending_operation
        self._pending_operation = None
        if confirmed and operation is not None:
            self.execute_operation(operation)

    @work(exclusive=True, group="state")
    async def execute_operation(self, operation: Operation) -> None:
        targets = self.state_tree.targets()
        if not targets:
            return

        self.switcher.loading = True
        self.notify(f"Running {self.client.executable} {_OPERATION_LABELS[operation]}")
        results = await self.client.operate(
            operation, [resource.full_address for resource in targets]
        )
        self.switcher.loading = False

        failures = [result for result in results if not result.ok]
        if failures:
            self.notify(_first_line(failures[0].output), severity="error", timeout=10)
        else:
            self.telemetry.capture(f"applied {operation}", size=str(len(targets)))

        self.state_tree.clear_selection()
        await self._load_state()

    # ------------------------------------------------------------------ plan

    def action_plan(self) -> None:
        self._ask_for_plan(destroy=False)

    def action_destroy(self) -> None:
        self._ask_for_plan(destroy=True)

    def _ask_for_plan(self, *, destroy: bool) -> None:
        targets = self.state_tree.targets()
        self._destroy_plan = destroy
        self.push_screen(
            PlanInputsScreen(
                var_files=self.settings.var_files,
                targets_available=bool(targets),
                destroy=destroy,
            ),
            self._start_plan,
        )

    def _start_plan(self, request: PlanRequest | None) -> None:
        if request is None:
            return
        targets = (
            [resource.full_address for resource in self.state_tree.targets()]
            if request.targeted
            else []
        )
        self.create_plan(request.var_files, targets, destroy=self._destroy_plan)

    @work(exclusive=True, group="plan")
    async def create_plan(
        self,
        var_files: Sequence[str],
        targets: list[str],
        *,
        destroy: bool,
    ) -> None:
        view = self.plan_view
        self._clear_search()
        view.begin(follow=False)
        self._show(PLAN, "Planning…")
        self.switcher.loading = True
        view.focus()

        first = True
        async for line in self.client.plan(var_files=var_files, targets=targets, destroy=destroy):
            if first:
                self.switcher.loading = False
                first = False
            view.feed(line)

        self.switcher.loading = False
        self.switcher.border_title = view.title
        self.telemetry.capture(
            "created plan",
            destroy=str(destroy),
            targeted=str(bool(targets)),
        )

        if self.client.plan_file is None and not view.styler.no_changes:
            self.notify("Plan failed - see the output above", severity="error")

    def action_apply(self) -> None:
        if self.client.plan_file is None:
            self.notify("No active plan to apply", severity="warning")
            return

        question = Text.assemble(
            ("Apply the current plan?\n\n", "bold"),
            self.plan_view.summary,
        )
        self.push_screen(ConfirmScreen(question), self._run_apply)

    def _run_apply(self, confirmed: bool | None) -> None:
        if confirmed:
            self.execute_apply()

    @work(exclusive=True, group="plan")
    async def execute_apply(self) -> None:
        view = self.plan_view
        self._clear_search()
        view.begin(follow=True)
        self._show(PLAN, "Applying…")
        self.switcher.loading = True
        self.telemetry.capture("applied plan")

        first = True
        async for line in self.client.apply():
            if first:
                self.switcher.loading = False
                first = False
            view.feed(line)

        self.switcher.loading = False
        self.switcher.border_title = "Apply complete - press Escape for the tree"
        # Refresh the tree behind the scenes; the output stays on screen to read.
        await self._load_state(show_tree=False)
        view.focus()

    # ------------------------------------------------------------ workspaces

    def action_workspaces(self) -> None:
        if self.view != TREE:
            return
        self.open_workspace_picker()

    @work(exclusive=True, group="workspace")
    async def open_workspace_picker(self) -> None:
        try:
            workspaces = await self.client.workspaces()
        except TftuiError as error:
            self.notify(_first_line(str(error)), severity="error")
            return
        if not workspaces.names:
            self.notify("No workspaces found", severity="warning")
            return
        self.push_screen(
            WorkspaceScreen(workspaces.names, workspaces.current),
            self._switch_workspace,
        )

    def _switch_workspace(self, name: str | None) -> None:
        if name:
            self.change_workspace(name)

    @work(exclusive=True, group="state")
    async def change_workspace(self, name: str) -> None:
        result = await self.client.select_workspace(name)
        if not result.ok:
            self.notify(_first_line(result.output), severity="error")
            return
        self.client.discard_plan()
        self.query_one("#header", AppHeader).workspace = name
        self.telemetry.capture("switched workspace")
        await self._load_state()

    # ----------------------------------------------------------------- chrome

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_toggle_theme(self) -> None:
        self.theme = LIGHT_THEME if self.theme == DARK_THEME else DARK_THEME
        # Syntax highlighting is chosen per theme, so the resource pane has to
        # be redrawn; nothing else on screen carries theme-dependent content.
        self.resource_view.rerender()

    # -------------------------------------------------------------- teardown

    def _handle_exception(self, error: Exception) -> None:
        self.error_message = "".join(
            traceback.format_exception(type(error), error, error.__traceback__)
        )
        super()._handle_exception(error)


def _selection_title(count: int) -> str:
    if not count:
        return ""
    return f"{count} resource selected" if count == 1 else f"{count} resources selected"


def _count(number: int) -> str:
    return "this resource" if number == 1 else f"these {number} resources"


def _first_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return "Command failed"
