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


async def test_vim_keys_move_the_cursor(app_pilot) -> None:
    app, pilot = app_pilot
    await pilot.press("1")
    start = app.state_tree.cursor_line
    await pilot.press("j", "j")
    assert app.state_tree.cursor_line == start + 2
    await pilot.press("k")
    assert app.state_tree.cursor_line == start + 1


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
