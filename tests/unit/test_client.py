"""The client layer: which subcommands run, and how plan files are handled."""

from __future__ import annotations

from pathlib import Path

import pytest

from tftui.errors import TerraformError
from tftui.terraform.client import DELETE, TAINT, UNTAINT, TerraformClient


async def test_load_state_parses_and_collects_secrets(client: TerraformClient) -> None:
    loaded = await client.load_state()
    assert len(loaded.state) == 96
    assert loaded.secrets_for("random_password.password").keys() == {"bcrypt_hash", "result"}
    assert loaded.secrets_for("random_integer.random_number") == {}


async def test_load_state_reads_text_and_json(client: TerraformClient, stub) -> None:
    await client.load_state()
    assert ("show", "-no-color") in stub.calls
    assert ("show", "-json") in stub.calls


async def test_load_state_raises_when_show_fails(client: TerraformClient, stub) -> None:
    stub.responses[("show", "-no-color")] = (1, "Error: no state file")
    with pytest.raises(TerraformError, match="no state file"):
        await client.load_state()


async def test_broken_json_does_not_break_state_loading(client: TerraformClient, stub) -> None:
    """Losing the JSON only costs the ability to reveal secrets."""
    stub.responses[("show", "-json")] = (0, "not json at all {{{")
    loaded = await client.load_state()
    assert len(loaded.state) == 96
    assert loaded.secrets == {}


# ------------------------------------------------------------------ workspaces


async def test_workspaces_marks_the_active_one(client: TerraformClient) -> None:
    workspaces = await client.workspaces()
    assert workspaces.names == ("default", "staging", "production")
    assert workspaces.current == "default"


async def test_workspaces_handles_a_non_default_active(client: TerraformClient, stub) -> None:
    stub.responses[("workspace", "list")] = (0, "  default\n* staging\n")
    workspaces = await client.workspaces()
    assert workspaces.current == "staging"


async def test_workspaces_raises_on_failure(client: TerraformClient, stub) -> None:
    stub.responses[("workspace", "list")] = (1, "Error: not initialized")
    with pytest.raises(TerraformError):
        await client.workspaces()


# ------------------------------------------------------------------ operations


@pytest.mark.parametrize(
    ("operation", "expected"),
    [(TAINT, ("taint",)), (UNTAINT, ("untaint",)), (DELETE, ("state", "rm"))],
)
async def test_operations_use_the_right_subcommand(
    client: TerraformClient, stub, operation: str, expected: tuple[str, ...]
) -> None:
    await client.operate(operation, ["random_integer.n"])
    call = stub.calls[-1]
    assert call[: len(expected)] == expected
    # The address is passed as its own argv entry, never interpolated.
    assert call[-1] == "random_integer.n"


async def test_operations_stop_at_the_first_failure(client: TerraformClient, stub) -> None:
    stub.responses[("taint",)] = (1, "Error: no such resource")
    results = await client.operate(TAINT, ["a.b", "c.d", "e.f"])
    assert len(results) == 1
    assert not results[0].ok


async def test_awkward_addresses_pass_through_intact(client: TerraformClient, stub) -> None:
    address = 'module.dots["a.b"].module.venus[0].local_file.foo["#1"]'
    await client.operate(TAINT, [address])
    assert stub.calls[-1][-1] == address


# ------------------------------------------------------------------------ plan


async def test_plan_writes_outside_the_working_directory(client: TerraformClient, stub) -> None:
    """Plan files can contain sensitive values, so they never land in the repo."""
    lines = [line async for line in client.plan()]
    assert lines

    plan_file = client.plan_file
    assert plan_file is not None
    assert plan_file.exists()
    assert plan_file.parent != client.cwd
    assert client.cwd not in plan_file.parents

    out_arg = next(arg for arg in stub.calls[-1] if arg.startswith("-out="))
    assert str(client.cwd) not in out_arg


async def test_plan_records_a_plan_file_when_changes_exist(
    client: TerraformClient,
) -> None:
    _ = [line async for line in client.plan()]
    assert client.plan_file is not None


async def test_plan_discards_the_file_when_there_are_no_changes(
    client: TerraformClient, stub
) -> None:
    stub.responses[("plan",)] = (0, "No changes. Your infrastructure matches.")
    _ = [line async for line in client.plan()]
    assert client.plan_file is None


async def test_plan_discards_the_file_on_error(client: TerraformClient, stub) -> None:
    stub.responses[("plan",)] = (1, "Error: invalid configuration")
    _ = [line async for line in client.plan()]
    assert client.plan_file is None


async def test_plan_passes_var_file_and_targets(client: TerraformClient, stub) -> None:
    _ = [
        line
        async for line in client.plan(
            var_file="prod.tfvars",
            targets=['module.a["x"].random_integer.n', "local_file.foo"],
            destroy=True,
        )
    ]
    call = stub.calls[-1]
    assert "-var-file=prod.tfvars" in call
    assert "-destroy" in call
    assert '-target=module.a["x"].random_integer.n' in call
    assert "-target=local_file.foo" in call


async def test_plan_always_disables_input_and_colour(client: TerraformClient, stub) -> None:
    _ = [line async for line in client.plan()]
    call = stub.calls[-1]
    assert "-no-color" in call
    assert "-input=false" in call
    assert "-detailed-exitcode" in call


async def test_a_second_plan_replaces_the_first(client: TerraformClient) -> None:
    _ = [line async for line in client.plan()]
    first = client.plan_file
    assert first is not None
    _ = [line async for line in client.plan()]
    second = client.plan_file
    assert second is not None
    assert second.parent == first.parent
    assert second.exists()


# ----------------------------------------------------------------------- apply


async def test_apply_requires_a_plan(client: TerraformClient) -> None:
    with pytest.raises(TerraformError, match="No active plan"):
        _ = [line async for line in client.apply()]


async def test_apply_consumes_the_plan(client: TerraformClient) -> None:
    _ = [line async for line in client.plan()]
    plan_file = client.plan_file
    assert plan_file is not None

    _ = [line async for line in client.apply()]

    # A plan may only be applied once; it must not survive to be reapplied.
    assert client.plan_file is None
    assert not plan_file.exists()


async def test_apply_passes_the_plan_path(client: TerraformClient, stub) -> None:
    _ = [line async for line in client.plan()]
    expected = str(client.plan_file)
    _ = [line async for line in client.apply()]
    assert expected in stub.calls[-1]


async def test_discard_plan_removes_the_file(client: TerraformClient) -> None:
    _ = [line async for line in client.plan()]
    plan_file = client.plan_file
    assert plan_file is not None
    client.discard_plan()
    assert client.plan_file is None
    assert not plan_file.exists()


async def test_cleanup_removes_the_private_directory(client: TerraformClient) -> None:
    _ = [line async for line in client.plan()]
    plan_dir = Path(str(client.plan_file)).parent
    assert plan_dir.exists()
    client.cleanup()
    assert not plan_dir.exists()
    client.cleanup()  # idempotent
