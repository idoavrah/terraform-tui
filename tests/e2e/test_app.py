"""End-to-end tests: drive the real application with Textual's Pilot.

These exercise the full stack - keybindings, workers, widgets, the client and
the parsers - against canned Terraform output, so they run in milliseconds and
need no Terraform binary.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest

from tftui.app import PLAN, RESOURCE, TREE, TerraformTUI
from tftui.config import Settings
from tftui.screens.confirm import ConfirmScreen
from tftui.screens.help import HelpScreen
from tftui.screens.plan_inputs import PlanInputsScreen
from tftui.screens.workspace import WorkspaceScreen
from tftui.terraform.client import TerraformClient
from tftui.widgets.header import LOGO

SIZE = (150, 45)


@asynccontextmanager
async def running(
    client: TerraformClient, settings: Settings
) -> AsyncIterator[tuple[TerraformTUI, object]]:
    """Start the app and wait until the initial state load has finished."""
    app = TerraformTUI(client, settings)
    async with app.run_test(size=SIZE) as pilot:
        for _ in range(200):
            if len(app.state_tree.state) and not app.state_tree.loading:
                break
            await pilot.pause(0.02)
        else:  # pragma: no cover - only on a genuine hang
            pytest.fail("state never loaded")
        await pilot.pause()
        yield app, pilot


@pytest.fixture
async def app_pilot(client: TerraformClient, settings: Settings):
    async with running(client, settings) as pair:
        yield pair


# ---------------------------------------------------------------------- startup


async def test_loads_state_into_the_tree(app_pilot) -> None:
    app, _ = app_pilot
    assert len(app.state_tree.state) == 96
    assert app.view == TREE
    assert app.state_tree.root.children


async def test_does_not_run_init_when_disabled(app_pilot, stub) -> None:
    assert not any(call[0] == "init" for call in stub.calls)


async def test_runs_init_when_enabled(client: TerraformClient, stub) -> None:
    async with running(client, Settings(run_init=True, offline=True, usage_tracking=False)):
        assert any(call[0] == "init" for call in stub.calls)


async def test_shows_the_active_workspace(app_pilot) -> None:
    app, pilot = app_pilot
    for _ in range(50):
        if app.query_one("#header").workspace == "default":
            break
        await pilot.pause(0.02)
    assert app.query_one("#header").workspace == "default"


async def test_empty_state_is_not_fatal(client: TerraformClient, stub, settings) -> None:
    """An empty state used to shut the program down; now you can still plan."""
    stub.responses[("show", "-no-color")] = (0, "")
    app = TerraformTUI(client, settings)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause(0.2)
        assert app.state_tree.state.is_empty
        assert app.is_running


# ------------------------------------------------------------------ navigation


async def test_enter_opens_the_resource_view(app_pilot) -> None:
    app, pilot = app_pilot
    await pilot.press("1")
    for _ in range(12):
        await pilot.press("j")
        if app.state_tree.highlighted is not None:
            break
    await pilot.press("enter")
    await pilot.pause()
    assert app.view == RESOURCE
    assert app.resource_view.resource is not None
    assert app.switcher.border_title == app.resource_view.resource.full_address


async def test_escape_returns_to_the_tree(app_pilot) -> None:
    app, pilot = app_pilot
    await pilot.press("1")
    for _ in range(12):
        await pilot.press("j")
        if app.state_tree.highlighted is not None:
            break
    await pilot.press("enter")
    await pilot.pause()
    await pilot.press("escape")
    await pilot.pause()
    assert app.view == TREE


@pytest.mark.parametrize(("down", "up"), [("j", "k"), ("down", "up")])
async def test_arrow_and_vim_keys_move_the_cursor(app_pilot, down: str, up: str) -> None:
    app, pilot = app_pilot
    await pilot.press("1")
    start = app.state_tree.cursor_line
    await pilot.press(down, down)
    assert app.state_tree.cursor_line == start + 2
    await pilot.press(up)
    assert app.state_tree.cursor_line == start + 1


@pytest.mark.parametrize(("collapse", "expand"), [("h", "l"), ("left", "right")])
async def test_arrow_and_vim_keys_collapse_and_expand(
    app_pilot, collapse: str, expand: str
) -> None:
    """Textual's Tree binds neither plain left nor right, so tftui must."""
    app, pilot = app_pilot
    await pilot.press("1")

    # Land on the first module, which is expandable.
    await pilot.press(expand)
    node = app.state_tree.cursor_node
    while node is not None and not node.allow_expand:
        await pilot.press("j")
        node = app.state_tree.cursor_node
    assert node is not None
    assert node.allow_expand

    if not node.is_expanded:
        await pilot.press(expand)
        await pilot.pause()
    assert node.is_expanded

    await pilot.press(collapse)
    await pilot.pause()
    assert not node.is_expanded


@pytest.mark.parametrize("key", ["h", "left"])
async def test_collapse_key_steps_out_to_the_parent(app_pilot, key: str) -> None:
    app, pilot = app_pilot
    await pilot.press("0")
    # Descend into the first module, onto a child.
    await pilot.press("j", "j")
    node = app.state_tree.cursor_node
    assert node is not None
    parent = node.parent
    assert parent is not None

    if node.allow_expand and node.is_expanded:
        await pilot.press(key)  # first press collapses
        await pilot.pause()
    await pilot.press(key)  # then steps out
    await pilot.pause()
    assert app.state_tree.cursor_line == parent.line


async def test_collapse_levels(app_pilot) -> None:
    app, pilot = app_pilot
    await pilot.press("1")
    depth_one = app.state_tree.last_line
    await pilot.press("2")
    depth_two = app.state_tree.last_line
    await pilot.press("0")
    everything = app.state_tree.last_line
    assert depth_one < depth_two < everything


# ---------------------------------------------------------------------- search


async def test_search_filters_the_tree(app_pilot) -> None:
    app, pilot = app_pilot
    await pilot.press("slash")
    for char in "mars":
        await pilot.press(char)
    await pilot.pause()
    assert app.search_input.value == "mars"
    assert app.state_tree.search == "mars"
    # Every leaf left in the tree matches.
    leaves = [node for node in _walk(app.state_tree.root) if not node.allow_expand]
    assert leaves
    assert all("mars" in str(node.label) for node in leaves)


async def test_typing_in_search_does_not_navigate_the_tree(app_pilot) -> None:
    """`j` and `k` are tree bindings, so they type normally in the filter box."""
    app, pilot = app_pilot
    await pilot.press("slash")
    for char in "jupiter":
        await pilot.press(char)
    await pilot.pause()
    assert app.search_input.value == "jupiter"


async def test_search_is_case_insensitive(app_pilot) -> None:
    app, pilot = app_pilot
    await pilot.press("slash")
    for char in "MARS":
        await pilot.press(char)
    await pilot.pause()
    assert [node for node in _walk(app.state_tree.root) if not node.allow_expand]


# ------------------------------------------------------------------- selection


async def test_space_selects_a_resource(app_pilot) -> None:
    app, pilot = app_pilot
    resource = _select_first_managed(app)
    await pilot.pause()
    assert app.state_tree.selected == {resource.full_address}
    assert app.sub_title == "1 selected"


async def test_data_sources_cannot_be_selected(app_pilot) -> None:
    app, pilot = app_pilot
    await pilot.press("1")
    while app.state_tree.highlighted is None or not app.state_tree.highlighted.is_data:
        await pilot.press("j")
    await pilot.press("space")
    await pilot.pause()
    assert app.state_tree.selected == set()


async def test_selection_survives_a_search(app_pilot) -> None:
    """Selection is tracked by address, so filtering does not lose it."""
    app, pilot = app_pilot
    resource = _select_first_managed(app)
    await pilot.press("slash")
    for char in "mars":
        await pilot.press(char)
    await pilot.pause()
    assert resource.full_address in app.state_tree.selected


async def test_ctrl_a_clears_the_selection(app_pilot) -> None:
    app, pilot = app_pilot
    _select_first_managed(app)
    await pilot.press("ctrl+a")
    await pilot.pause()
    assert app.state_tree.selected == set()


# ------------------------------------------------------------------ operations


async def test_taint_asks_before_acting(app_pilot, stub) -> None:
    app, pilot = app_pilot
    _select_first_managed(app)
    await pilot.press("t")
    await pilot.pause()
    assert isinstance(app.screen, ConfirmScreen)
    assert not any(call[0] == "taint" for call in stub.calls)


async def test_declining_the_confirmation_does_nothing(app_pilot, stub) -> None:
    app, pilot = app_pilot
    _select_first_managed(app)
    await pilot.press("t")
    await pilot.pause()
    await pilot.press("n")
    await pilot.pause(0.2)
    assert not any(call[0] == "taint" for call in stub.calls)


async def test_accepting_the_confirmation_runs_the_command(app_pilot, stub) -> None:
    app, pilot = app_pilot
    resource = _select_first_managed(app)
    await pilot.press("t")
    await pilot.pause()
    await pilot.press("y")
    for _ in range(100):
        await pilot.pause(0.02)
        if any(call[0] == "taint" for call in stub.calls):
            break
    taint = next(call for call in stub.calls if call[0] == "taint")
    assert taint[-1] == resource.full_address


async def test_delete_uses_state_rm(app_pilot, stub) -> None:
    app, pilot = app_pilot
    _select_first_managed(app)
    await pilot.press("d")
    await pilot.pause()
    await pilot.press("y")
    for _ in range(100):
        await pilot.pause(0.02)
        if any(call[:2] == ("state", "rm") for call in stub.calls):
            break
    assert any(call[:2] == ("state", "rm") for call in stub.calls)


async def test_operations_are_refused_with_nothing_selected(app_pilot) -> None:
    app, pilot = app_pilot
    await pilot.press("0")
    # The cursor sits on the root, which is not a resource.
    app.state_tree.cursor_line = 0
    await pilot.press("t")
    await pilot.pause()
    assert not isinstance(app.screen, ConfirmScreen)


# ------------------------------------------------------------------------ plan


async def test_plan_dialog_then_streamed_output(app_pilot, stub) -> None:
    app, pilot = app_pilot
    await pilot.press("p")
    await pilot.pause()
    assert isinstance(app.screen, PlanInputsScreen)

    await pilot.press("enter")
    for _ in range(200):
        await pilot.pause(0.02)
        if app.client.plan_file is not None:
            break

    assert app.view == PLAN
    assert app.plan_view.styler.summary == "Plan: 30 to add, 0 to change, 0 to destroy."
    assert app.switcher.border_title == app.plan_view.styler.summary
    assert app.client.plan_file is not None


async def test_cancelling_the_plan_dialog_runs_nothing(app_pilot, stub) -> None:
    _, pilot = app_pilot
    await pilot.press("p")
    await pilot.pause()
    await pilot.press("escape")
    await pilot.pause(0.2)
    assert not any(call[0] == "plan" for call in stub.calls)


async def test_destroy_plan_passes_the_destroy_flag(app_pilot, stub) -> None:
    _, pilot = app_pilot
    await pilot.press("ctrl+d")
    await pilot.pause()
    await pilot.press("enter")
    for _ in range(200):
        await pilot.pause(0.02)
        if any(call[0] == "plan" for call in stub.calls):
            break
    plan = next(call for call in stub.calls if call[0] == "plan")
    assert "-destroy" in plan


async def test_targeted_plan_uses_the_selection(app_pilot, stub) -> None:
    app, pilot = app_pilot
    resource = _select_first_managed(app)
    await pilot.press("p")
    await pilot.pause()
    await pilot.press("enter")
    for _ in range(200):
        await pilot.pause(0.02)
        if any(call[0] == "plan" for call in stub.calls):
            break
    plan = next(call for call in stub.calls if call[0] == "plan")
    assert f"-target={resource.full_address}" in plan


async def test_apply_without_a_plan_is_refused(app_pilot, stub) -> None:
    app, pilot = app_pilot
    await pilot.press("a")
    await pilot.pause()
    assert not isinstance(app.screen, ConfirmScreen)
    assert not any(call[0] == "apply" for call in stub.calls)


async def test_apply_leaves_the_output_on_screen(app_pilot) -> None:
    """After applying, the output stays readable instead of snapping to the tree.

    The state still has to be reloaded, because the apply changed it.
    """
    app, pilot = app_pilot
    await _make_a_plan(app, pilot)

    await pilot.press("a")
    await pilot.pause()
    await pilot.press("y")
    for _ in range(300):
        await pilot.pause(0.02)
        if "Apply complete" in str(app.switcher.border_title):
            break

    assert app.view == PLAN, "apply output was replaced by the tree"
    assert "Apply complete!" in app.plan_view.fulltext.plain
    # The tree was still refreshed behind the scenes.
    assert len(app.state_tree.state) == 96
    assert not app.state_tree.loading

    # Escape is the way back, as the border title says.
    await pilot.press("escape")
    await pilot.pause()
    assert app.view == TREE


async def test_apply_confirms_then_runs(app_pilot, stub) -> None:
    app, pilot = app_pilot
    await pilot.press("p")
    await pilot.pause()
    await pilot.press("enter")
    for _ in range(200):
        await pilot.pause(0.02)
        if app.client.plan_file is not None:
            break

    await pilot.press("a")
    await pilot.pause()
    assert isinstance(app.screen, ConfirmScreen)

    await pilot.press("y")
    for _ in range(200):
        await pilot.pause(0.02)
        if any(call[0] == "apply" for call in stub.calls):
            break
    assert any(call[0] == "apply" for call in stub.calls)


async def test_plan_output_drops_the_refresh_preamble(app_pilot) -> None:
    """The pane opens on the diff, not on pages of `Refreshing state...`."""
    app, pilot = app_pilot
    await pilot.press("p")
    await pilot.pause()
    await pilot.press("enter")
    for _ in range(200):
        await pilot.pause(0.02)
        if app.client.plan_file is not None:
            break
    text = app.plan_view.fulltext.plain
    assert "Refreshing state..." not in text
    assert text.startswith("Terraform will perform the following actions:")


# ------------------------------------------------------------------- sensitive


async def test_x_reveals_and_hides_sensitive_values(app_pilot) -> None:
    app, pilot = app_pilot
    _open_resource(app, "random_password.password")
    await pilot.pause()
    assert "(sensitive value)" in app.resource_view.body

    await pilot.press("x")
    await pilot.pause()
    assert app.resource_view.revealed
    assert "(sensitive value)" not in app.resource_view.body

    await pilot.press("x")
    await pilot.pause()
    assert not app.resource_view.revealed
    assert "(sensitive value)" in app.resource_view.body


async def test_x_on_a_resource_without_secrets_says_so(app_pilot) -> None:
    app, pilot = app_pilot
    _open_resource(app, "random_integer.random_number")
    await pilot.pause()
    await pilot.press("x")
    await pilot.pause()
    assert not app.resource_view.revealed


# ------------------------------------------------------------------ workspaces


async def test_workspace_picker_lists_workspaces(app_pilot) -> None:
    app, pilot = app_pilot
    await pilot.press("w")
    for _ in range(100):
        await pilot.pause(0.02)
        if isinstance(app.screen, WorkspaceScreen):
            break
    assert isinstance(app.screen, WorkspaceScreen)
    assert app.screen.workspaces == ("default", "staging", "production")


async def test_switching_workspace_reloads_state(app_pilot, stub) -> None:
    app, pilot = app_pilot
    await pilot.press("w")
    for _ in range(100):
        await pilot.pause(0.02)
        if isinstance(app.screen, WorkspaceScreen):
            break
    app.screen.options.highlighted = 1
    await pilot.press("enter")
    for _ in range(200):
        await pilot.pause(0.02)
        if any(call[:2] == ("workspace", "select") for call in stub.calls):
            break
    select = next(call for call in stub.calls if call[:2] == ("workspace", "select"))
    assert select[-1] == "staging"


# ----------------------------------------------------------------------- chrome


async def test_help_screen_opens_and_closes(app_pilot) -> None:
    app, pilot = app_pilot
    await pilot.press("question_mark")
    await pilot.pause()
    assert isinstance(app.screen, HelpScreen)
    await pilot.press("escape")
    await pilot.pause()
    assert not isinstance(app.screen, HelpScreen)


async def test_theme_toggle(app_pilot) -> None:
    app, pilot = app_pilot
    first = app.theme
    await pilot.press("m")
    await pilot.pause()
    assert app.theme != first
    await pilot.press("m")
    await pilot.pause()
    assert app.theme == first


async def test_light_mode_setting(client: TerraformClient) -> None:
    settings = Settings(run_init=False, offline=True, usage_tracking=False, light_mode=True)
    async with running(client, settings) as (app, _):
        assert app.theme == "textual-light"


async def test_refresh_reloads_state(app_pilot, stub) -> None:
    _, pilot = app_pilot
    before = sum(1 for call in stub.calls if call[:2] == ("show", "-no-color"))
    await pilot.press("r")
    for _ in range(200):
        await pilot.pause(0.02)
        after = sum(1 for call in stub.calls if call[:2] == ("show", "-no-color"))
        if after > before:
            break
    assert after > before


# --------------------------------------------------------------------- helpers


async def _make_a_plan(app, pilot) -> None:
    """Create a plan through the UI and wait for it to finish."""
    await pilot.press("p")
    await pilot.pause()
    await pilot.press("enter")
    for _ in range(300):
        await pilot.pause(0.02)
        if app.client.plan_file is not None:
            return
    raise AssertionError("plan never completed")


def _walk(node):
    for child in node.children:
        yield child
        yield from _walk(child)


def _select_first_managed(app):
    """Select the first actionable resource, and return it."""
    for node in _walk(app.state_tree.root):
        resource = node.data
        if hasattr(resource, "is_actionable") and resource.is_actionable:
            app.state_tree.cursor_line = node.line
            app.state_tree.action_toggle_selection()
            return resource
    raise AssertionError("no managed resource in the tree")


def _open_resource(app, address: str):
    """Open ``address`` in the resource view, as pressing Enter on it would."""
    resource = app.state_tree.state.resources[address]
    app.resource_view.show(resource, secrets=app.state_tree.loaded.secrets_for(address))
    app.switcher.current = RESOURCE
    return resource


# ------------------------------------------------------------------ rendering


def _backgrounds(widget) -> set:
    """Every explicit background colour the widget's own content paints."""
    return {
        segment.style.bgcolor
        for strip in widget.lines
        for segment in strip
        if segment.style is not None and segment.style.bgcolor is not None
    }


async def test_resource_view_paints_no_background_of_its_own(app_pilot) -> None:
    """Syntax highlighting must inherit the pane's background.

    Stamping a background onto the highlighted segments - even the terminal
    "default" - leaves the code a different shade from the whitespace around it.
    """
    app, pilot = app_pilot
    _open_resource(app, "random_password.password")
    await pilot.pause()
    assert app.resource_view.lines, "nothing was rendered"
    assert _backgrounds(app.resource_view) == set()


def _foregrounds(widget) -> set:
    return {
        segment.style.color
        for strip in widget.lines
        for segment in strip
        if segment.style is not None and segment.style.color is not None
    }


async def test_resource_view_follows_the_theme(app_pilot) -> None:
    """Toggling light/dark re-highlights the pane and keeps it background-free."""
    app, pilot = app_pilot
    _open_resource(app, "random_password.password")
    await pilot.pause()
    dark_colours = _foregrounds(app.resource_view)

    await pilot.press("m")
    await pilot.pause()
    light_colours = _foregrounds(app.resource_view)

    assert dark_colours
    assert dark_colours != light_colours
    assert app.resource_view.body  # content survived the re-render
    assert _backgrounds(app.resource_view) == set()


# --------------------------------------------------------------------- header


def _screen_lines(app) -> list[str]:
    return [
        "".join(segment.text for segment in strip)
        for strip in app.screen._compositor.render_strips()
    ]


async def test_logo_is_not_sheared_by_alignment(app_pilot) -> None:
    """The banner is pre-formatted art; its lines must keep their relative offsets.

    Its five lines differ in length, so aligning them individually (right or
    centre) shifts each by a different amount and shears the lettering.
    """
    app, pilot = app_pilot
    await pilot.pause()

    source = LOGO.rstrip("\n").split("\n")
    lines = _screen_lines(app)

    rendered: list[int] = []
    for line in source:
        art = line.strip()
        row = next((row for row in lines if art in row), None)
        assert row is not None, f"logo line not found on screen: {art!r}"
        rendered.append(row.index(art))

    def normalise(values: list[int]) -> list[int]:
        return [value - min(values) for value in values]

    expected = normalise([len(line) - len(line.lstrip()) for line in source])
    assert normalise(rendered) == expected


# ------------------------------------------------ module selection (issue #82)


def _first_module_node(app):
    for node in _walk(app.state_tree.root):
        if isinstance(node.data, str):
            return node
    raise AssertionError("no module in the tree")


def _resources_under(node) -> list:
    return [
        child.data
        for child in _walk(node)
        if hasattr(child.data, "is_actionable") and child.data.is_actionable
    ]


async def test_space_on_a_module_selects_everything_under_it(app_pilot) -> None:
    """Issue #82: selecting a whole module by hand is the tedious case."""
    app, pilot = app_pilot
    await pilot.press("0")
    node = _first_module_node(app)
    expected = {resource.full_address for resource in _resources_under(node)}
    assert len(expected) > 1, "need a module with several resources"

    app.state_tree.cursor_line = node.line
    await pilot.press("space")
    await pilot.pause()

    assert app.state_tree.selected == expected


async def test_space_on_a_selected_module_deselects_it(app_pilot) -> None:
    app, pilot = app_pilot
    await pilot.press("0")
    node = _first_module_node(app)
    app.state_tree.cursor_line = node.line

    await pilot.press("space")
    await pilot.pause()
    assert app.state_tree.selected

    await pilot.press("space")
    await pilot.pause()
    assert app.state_tree.selected == set()


async def test_partly_selected_module_selects_the_rest(app_pilot) -> None:
    """Space on a half-selected module completes it rather than clearing it."""
    app, pilot = app_pilot
    await pilot.press("0")
    node = _first_module_node(app)
    resources = _resources_under(node)
    app.state_tree.selected.add(resources[0].full_address)

    app.state_tree.cursor_line = node.line
    await pilot.press("space")
    await pilot.pause()

    assert app.state_tree.selected == {r.full_address for r in resources}


async def test_module_selection_skips_data_sources(app_pilot) -> None:
    app, pilot = app_pilot
    await pilot.press("0")
    node = _first_module_node(app)
    app.state_tree.cursor_line = node.line
    await pilot.press("space")
    await pilot.pause()

    chosen = [app.state_tree.state.resources[a] for a in app.state_tree.selected]
    assert chosen
    assert not any(resource.is_data for resource in chosen)


async def test_module_selection_feeds_a_targeted_plan(app_pilot, stub) -> None:
    app, pilot = app_pilot
    await pilot.press("0")
    node = _first_module_node(app)
    app.state_tree.cursor_line = node.line
    await pilot.press("space")
    await pilot.pause()
    selected = set(app.state_tree.selected)

    await pilot.press("p")
    await pilot.pause()
    await pilot.press("enter")
    for _ in range(300):
        await pilot.pause(0.02)
        if any(call[0] == "plan" for call in stub.calls):
            break

    plan = next(call for call in stub.calls if call[0] == "plan")
    targeted = {arg.removeprefix("-target=") for arg in plan if arg.startswith("-target=")}
    assert targeted == selected


async def test_enter_still_expands_a_module(app_pilot) -> None:
    """Space no longer toggles, so Enter must still open a module."""
    app, pilot = app_pilot
    await pilot.press("1")
    node = _first_module_node(app)
    app.state_tree.cursor_line = node.line
    was_expanded = node.is_expanded

    await pilot.press("enter")
    await pilot.pause()
    assert node.is_expanded is not was_expanded


# ---------------------------------------------------- plan search (issue #89)


async def test_slash_searches_within_the_plan(app_pilot) -> None:
    """Issue #89: `/` should work on plan output, not only the tree."""
    app, pilot = app_pilot
    await _make_a_plan(app, pilot)

    await pilot.press("slash")
    for char in "local_file":
        await pilot.press(char)
    await pilot.pause()

    assert app.view == PLAN, "searching must not leave the plan"
    assert app.plan_view.needle == "local_file"
    assert app.plan_view.match_count > 1
    assert "match 1/" in str(app.switcher.border_title)


async def test_plan_search_keeps_every_line(app_pilot) -> None:
    """Matches are highlighted, not filtered: a diff needs its context."""
    app, pilot = app_pilot
    await _make_a_plan(app, pilot)
    before = app.plan_view.fulltext.plain

    await pilot.press("slash")
    for char in "content":
        await pilot.press(char)
    await pilot.pause()

    assert app.plan_view.fulltext.plain == before


async def test_n_steps_through_plan_matches(app_pilot) -> None:
    app, pilot = app_pilot
    await _make_a_plan(app, pilot)

    await pilot.press("slash")
    for char in "local_file":
        await pilot.press(char)
    await pilot.pause()
    await pilot.press("escape")  # leave the input, stay on the plan
    await pilot.pause()

    assert app.plan_view.match_position == 1
    await pilot.press("n")
    await pilot.pause()
    assert app.plan_view.match_position == 2

    await pilot.press("N")
    await pilot.pause()
    assert app.plan_view.match_position == 1


async def test_plan_search_reports_no_match(app_pilot) -> None:
    app, pilot = app_pilot
    await _make_a_plan(app, pilot)

    await pilot.press("slash")
    for char in "zzzz":
        await pilot.press(char)
    await pilot.pause()

    assert app.plan_view.match_count == 0
    assert "no match" in str(app.switcher.border_title)
    assert app.search_input.has_class("nomatch")


async def test_leaving_the_plan_clears_its_search(app_pilot) -> None:
    app, pilot = app_pilot
    await _make_a_plan(app, pilot)
    await pilot.press("slash")
    for char in "local_file":
        await pilot.press(char)
    await pilot.pause()

    await pilot.press("escape")  # out of the input
    await pilot.pause()
    await pilot.press("escape")  # out of the plan
    await pilot.pause()

    assert app.view == TREE
    assert app.plan_view.needle == ""
    assert not app.search_input.has_class("nomatch")


async def test_slash_in_the_tree_still_filters(app_pilot) -> None:
    """The tree keeps filtering; only the plan highlights in place."""
    app, pilot = app_pilot
    await pilot.press("slash")
    for char in "mars":
        await pilot.press(char)
    await pilot.pause()
    assert app.state_tree.search == "mars"


# ----------------------------------------- search within a resource, and reuse


async def test_slash_searches_within_a_resource(app_pilot) -> None:
    """`/` on an open resource searches it, rather than dropping back to the tree."""
    app, pilot = app_pilot
    _open_resource(app, "random_password.password")
    await pilot.pause()

    await pilot.press("slash")
    for char in "min_lower":
        await pilot.press(char)
    await pilot.pause()

    assert app.view == RESOURCE, "searching a resource must not leave it"
    assert app.resource_view.needle == "min_lower"
    assert app.resource_view.match_count == 1
    assert "match 1/1" in str(app.switcher.border_title)


async def test_resource_search_keeps_every_line(app_pilot) -> None:
    app, pilot = app_pilot
    _open_resource(app, "random_password.password")
    await pilot.pause()
    before = app.resource_view.fulltext.plain

    await pilot.press("slash")
    for char in "min":
        await pilot.press(char)
    await pilot.pause()

    assert app.resource_view.fulltext.plain == before
    assert app.resource_view.match_count > 1


async def test_n_steps_through_resource_matches(app_pilot) -> None:
    app, pilot = app_pilot
    _open_resource(app, "random_password.password")
    await pilot.pause()

    await pilot.press("slash")
    for char in "min":
        await pilot.press(char)
    await pilot.pause()
    await pilot.press("escape")
    await pilot.pause()

    assert app.resource_view.match_position == 1
    await pilot.press("n")
    await pilot.pause()
    assert app.resource_view.match_position == 2


async def test_reopening_the_search_keeps_what_was_typed(app_pilot) -> None:
    """Pressing / again must not wipe the box; it is how you refine a search."""
    app, pilot = app_pilot
    await pilot.press("slash")
    for char in "mars":
        await pilot.press(char)
    await pilot.pause()

    await pilot.press("escape")  # focus the tree
    await pilot.pause()
    await pilot.press("slash")  # back to the box
    await pilot.pause()

    assert app.search_input.value == "mars"
    assert app.state_tree.search == "mars"

    # ...and it can be extended in place.
    for char in "xyz":
        await pilot.press(char)
    await pilot.pause()
    assert app.search_input.value == "marsxyz"


async def test_switching_pane_starts_a_fresh_search(app_pilot) -> None:
    """A tree filter means nothing inside a plan, so changing pane resets it."""
    app, pilot = app_pilot
    await pilot.press("slash")
    for char in "mars":
        await pilot.press(char)
    await pilot.pause()
    await pilot.press("escape")
    await pilot.pause()

    await _make_a_plan(app, pilot)
    await pilot.press("slash")
    await pilot.pause()

    assert app.search_input.value == ""
    assert app.plan_view.needle == ""


async def test_leaving_a_resource_clears_its_search(app_pilot) -> None:
    app, pilot = app_pilot
    _open_resource(app, "random_password.password")
    await pilot.pause()
    await pilot.press("slash")
    for char in "min":
        await pilot.press(char)
    await pilot.pause()

    await pilot.press("escape")  # out of the input
    await pilot.pause()
    await pilot.press("escape")  # out of the resource
    await pilot.pause()

    assert app.view == TREE
    assert app.resource_view.needle == ""
    assert app.search_input.value == ""
