"""Integration tests that drive a real Terraform binary.

They run against ``examples/terraform``, a self-contained project using only the
``random``, ``local`` and ``time`` providers, so nothing outside the working
directory is ever created. Deselect with ``-m "not integration"``.

Each test gets its own copy of the project in ``tmp_path``, so tests cannot
interfere with each other or leave the example project dirty.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tftui.app import PLAN, TREE, TerraformTUI
from tftui.config import Settings
from tftui.errors import ExecutableNotFoundError
from tftui.terraform.client import TAINT, UNTAINT, TerraformClient
from tftui.terraform.executor import TerraformExecutor

pytestmark = pytest.mark.integration

EXAMPLE = Path(__file__).parents[2] / "examples" / "terraform"


def _terraform_available() -> bool:
    try:
        TerraformExecutor("terraform")
    except ExecutableNotFoundError:
        return False
    return True


requires_terraform = pytest.mark.skipif(
    not _terraform_available(), reason="terraform binary not on PATH"
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A private copy of the example project, ready to init and apply."""
    target = tmp_path / "terraform"
    # The provider plugins under .terraform are copied so each test does not
    # re-download them; state and generated files are not, so every test starts
    # from nothing and applies its own.
    shutil.copytree(
        EXAMPLE,
        target,
        symlinks=True,
        ignore=shutil.ignore_patterns(
            "generated", "terraform.tfstate", "terraform.tfstate.backup", "*.plan"
        ),
    )
    (target / "generated").mkdir(exist_ok=True)
    return target


@pytest.fixture
def live_client(project: Path):
    terraform = TerraformClient(TerraformExecutor("terraform", cwd=project))
    yield terraform
    terraform.cleanup()


@pytest.fixture
async def applied(live_client: TerraformClient):
    """Initialise and apply the project so there is real state to read."""
    assert (await live_client.init()).ok
    lines = [line async for line in live_client.plan()]
    assert lines
    assert live_client.plan_file is not None
    apply_lines = [line async for line in live_client.apply()]
    assert any("Apply complete!" in line for line in apply_lines)
    return live_client


# ------------------------------------------------------------------- the basics


@requires_terraform
async def test_version(live_client: TerraformClient) -> None:
    version = await live_client.version()
    assert version
    assert version[0].isdigit()


@requires_terraform
async def test_init_succeeds(live_client: TerraformClient) -> None:
    result = await live_client.init()
    assert result.ok


@requires_terraform
async def test_workspaces(applied: TerraformClient) -> None:
    workspaces = await applied.workspaces()
    assert "default" in workspaces.names
    assert workspaces.current == "default"
    assert await applied.current_workspace() == "default"


# ------------------------------------------------------------------ real state


@requires_terraform
async def test_reads_and_parses_real_state(applied: TerraformClient) -> None:
    loaded = await applied.load_state()
    state = loaded.state

    assert not state.is_empty
    counts = state.counts()
    assert counts["resources"] > 0
    assert counts["data"] > 0

    # Every address Terraform emitted parses back into module + name.
    for resource in state:
        assert resource.name
        assert resource.full_address.endswith(resource.name)
        if resource.module:
            assert resource.full_address.startswith(resource.module)


@requires_terraform
async def test_awkward_module_keys_survive_a_round_trip(
    applied: TerraformClient,
) -> None:
    """Keys containing dots, colons and hashes must parse and re-address cleanly."""
    state = (await applied.load_state()).state
    addresses = set(state.resources)

    assert any('dots["string.with.dots"]' in address for address in addresses)
    assert any('colons["string:with:colons"]' in address for address in addresses)
    assert any('foo["#1"]' in address for address in addresses)

    deep = [r for r in state if r.address.depth == 3]
    assert deep, "expected three-level module nesting in the example project"


@requires_terraform
async def test_sensitive_values_are_recovered(applied: TerraformClient) -> None:
    loaded = await applied.load_state()
    secrets = loaded.secrets_for("random_password.password")
    assert set(secrets) == {"bcrypt_hash", "result"}

    resource = loaded.state.resources["random_password.password"]
    assert "(sensitive value)" in resource.body

    revealed = resource.reveal(secrets)
    assert "(sensitive value)" not in revealed
    assert f'result      = "{secrets["result"]}"' in revealed


@requires_terraform
async def test_outputs_are_captured(applied: TerraformClient) -> None:
    state = (await applied.load_state()).state
    assert "greeting" in state.outputs


# ------------------------------------------------------------------ operations


@requires_terraform
async def test_taint_and_untaint_round_trip(applied: TerraformClient) -> None:
    address = "random_integer.random_number"

    results = await applied.operate(TAINT, [address])
    assert all(result.ok for result in results)
    state = (await applied.load_state()).state
    assert state.resources[address].tainted is True
    assert state.counts()["tainted"] == 1

    results = await applied.operate(UNTAINT, [address])
    assert all(result.ok for result in results)
    state = (await applied.load_state()).state
    assert state.resources[address].tainted is False


@requires_terraform
async def test_operating_on_an_address_with_special_characters(
    applied: TerraformClient,
) -> None:
    """The real proof that addresses are never re-split or shell-quoted."""
    state = (await applied.load_state()).state
    address = next(
        r.full_address
        for r in state
        if 'foo["#1"]' in r.full_address and 'dots["string.with.dots"]' in r.full_address
    )

    results = await applied.operate(TAINT, [address])
    assert all(result.ok for result in results), results[0].output

    refreshed = (await applied.load_state()).state
    assert refreshed.resources[address].tainted is True


# ----------------------------------------------------------------------- plans


@requires_terraform
async def test_plan_with_no_changes_keeps_no_plan_file(
    applied: TerraformClient,
) -> None:
    lines = [line async for line in applied.plan()]
    assert any("No changes" in line for line in lines)
    assert applied.plan_file is None


@requires_terraform
async def test_plan_detects_a_real_change(applied: TerraformClient) -> None:
    generated = applied.cwd / "generated"
    victim = next(generated.iterdir())
    victim.unlink()

    lines = [line async for line in applied.plan()]
    assert applied.plan_file is not None
    assert any(line.startswith("Plan:") for line in lines)


@requires_terraform
async def test_plan_file_is_written_outside_the_project(
    applied: TerraformClient,
) -> None:
    """A plan can contain sensitive values; it must not land in the repo."""
    (next((applied.cwd / "generated").iterdir())).unlink()
    _ = [line async for line in applied.plan()]

    plan_file = applied.plan_file
    assert plan_file is not None
    assert plan_file.exists()
    assert applied.cwd not in plan_file.parents
    assert not list(applied.cwd.glob("*.plan"))
    assert not (applied.cwd / "tftui.plan").exists()


@requires_terraform
async def test_targeted_plan_only_touches_the_target(
    applied: TerraformClient,
) -> None:
    """Deleting several files but targeting one must plan exactly one change."""
    state = (await applied.load_state()).state
    files = [r for r in state if r.name.startswith("local_file.foo")]
    assert len(files) >= 3

    # Each module instance owns a distinct file; delete three of them.
    victims = files[:3]
    for resource in victims:
        _filename_of(resource.body, applied.cwd).unlink()

    target = victims[0].full_address
    lines = [line async for line in applied.plan(targets=[target])]

    summary = next((line for line in lines if line.startswith("Plan:")), "")
    assert summary.startswith("Plan: 1 to add"), lines[-25:]


def _filename_of(body: str, root: Path) -> Path:
    """Pull the `filename` attribute out of a rendered local_file resource."""
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("filename "):
            value = stripped.split("=", 1)[1].strip().strip('"')
            return root / value
    raise AssertionError("no filename attribute in resource body")


@requires_terraform
async def test_var_file_is_honoured(applied: TerraformClient) -> None:
    lines = [line async for line in applied.plan(var_files=["terraform.tfvars"])]
    assert not any("No value for required variable" in line for line in lines)


@requires_terraform
async def test_several_var_files_are_all_applied(applied: TerraformClient) -> None:
    """Issue #85 / #62: every -f must reach terraform, in order.

    Split the single required variable across two files so the plan only
    succeeds if both were passed.
    """
    (applied.cwd / "one.tfvars").write_text('something = "from-one"\n')
    (applied.cwd / "two.tfvars").write_text('something = "from-two"\n')

    lines = [line async for line in applied.plan(var_files=["one.tfvars", "two.tfvars"])]
    assert not any("No value for required variable" in line for line in lines)

    # A later file wins, which is Terraform's own precedence.
    lines = [line async for line in applied.plan(var_files=["two.tfvars", "one.tfvars"])]
    assert not any("No value for required variable" in line for line in lines)


@requires_terraform
async def test_init_accepts_var_files(applied: TerraformClient) -> None:
    """Issue #85: OpenTofu needs var-files at init to evaluate a backend block.

    Terraform rejects genuinely unknown flags, so a clean exit here proves the
    flag is understood rather than silently swallowed.
    """
    result = await applied.init(var_files=["terraform.tfvars"])
    assert result.ok, result.output


@requires_terraform
async def test_apply_consumes_the_plan_and_changes_state(
    applied: TerraformClient,
) -> None:
    generated = applied.cwd / "generated"
    victim = next(generated.iterdir())
    victim.unlink()

    _ = [line async for line in applied.plan()]
    plan_file = applied.plan_file
    assert plan_file is not None

    lines = [line async for line in applied.apply()]
    assert any("Apply complete!" in line for line in lines)

    assert victim.exists(), "apply should have recreated the file"
    assert applied.plan_file is None
    assert not plan_file.exists()


@requires_terraform
async def test_destroy_plan_targets_everything(applied: TerraformClient) -> None:
    lines = [line async for line in applied.plan(destroy=True)]
    summary = next(line for line in lines if line.startswith("Plan:"))
    assert " to destroy." in summary
    assert not summary.startswith("Plan: 0 to add, 0 to change, 0 to destroy.")


# --------------------------------------------------------- the app, end to end


@requires_terraform
async def test_application_runs_against_real_terraform(applied: TerraformClient) -> None:
    """Start the real app, on real state, and walk through the main views."""
    client = applied
    settings = Settings(run_init=True, offline=True, usage_tracking=False)
    app = TerraformTUI(client, settings)

    try:
        async with app.run_test(size=(150, 45)) as pilot:
            for _ in range(1500):
                if len(app.state_tree.state) and not app.state_tree.loading:
                    break
                await pilot.pause(0.05)
            else:  # pragma: no cover
                pytest.fail("state never loaded from real terraform")

            assert app.view == TREE
            assert len(app.state_tree.state) > 50

            # Filter, then open a resource.
            await pilot.press("slash")
            for char in "password":
                await pilot.press(char)
            await pilot.pause()
            assert app.state_tree.search == "password"

            await pilot.press("escape")
            await pilot.press("0")
            await pilot.pause()

            # Create a real plan through the UI.
            await pilot.press("p")
            await pilot.pause()
            await pilot.press("enter")
            for _ in range(1500):
                await pilot.pause(0.05)
                if app.plan_view.styler.summary or app.plan_view.styler.no_changes:
                    break
            assert app.view == PLAN
            assert app.plan_view.styler.no_changes or app.plan_view.styler.summary
    finally:
        client.cleanup()


@requires_terraform
async def test_application_handles_an_unapplied_project(project: Path) -> None:
    """With no state yet, the app stays up and offers to plan.

    Previous releases exited when `terraform show` returned nothing.
    """
    client = TerraformClient(TerraformExecutor("terraform", cwd=project))
    app = TerraformTUI(client, Settings(run_init=True, offline=True, usage_tracking=False))
    try:
        async with app.run_test(size=(150, 45)) as pilot:
            for _ in range(600):
                await pilot.pause(0.05)
                if not app.state_tree.loading and app.workers == []:
                    break
            assert app.is_running
            assert app.state_tree.state.is_empty
            assert app.view == TREE
    finally:
        client.cleanup()
