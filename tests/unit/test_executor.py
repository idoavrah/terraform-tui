"""Process execution - the security-sensitive layer."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tftui.errors import ExecutableNotFoundError, InvalidExecutableError, TerraformError
from tftui.terraform.executor import (
    CommandResult,
    TerraformExecutor,
    resolve_executable,
    target_args,
)

# ------------------------------------------------------------ executable name


@pytest.mark.parametrize(
    "hostile",
    [
        "terraform; rm -rf /",
        "terraform && curl evil.example",
        "terraform | tee /tmp/x",
        "$(whoami)",
        "`id`",
        "terraform\nrm -rf /",
        "terra form",
        "",
        "   ",
    ],
)
def test_rejects_names_containing_shell_syntax(hostile: str) -> None:
    with pytest.raises(InvalidExecutableError):
        resolve_executable(hostile)


def test_rejects_missing_executable() -> None:
    with pytest.raises(ExecutableNotFoundError):
        resolve_executable("definitely-not-installed-xyz")


def test_resolves_a_real_executable() -> None:
    resolved = resolve_executable("python3")
    assert Path(resolved).is_absolute()
    assert Path(resolved).name.startswith("python")


def test_accepts_a_path_to_an_executable() -> None:
    assert resolve_executable(sys.executable) == sys.executable


# ---------------------------------------------------------------- arg passing


def test_target_args_do_not_quote_or_split() -> None:
    """Each address becomes one argv entry, so quoting is never needed."""
    addresses = [
        'module.dots["a.b"].random_integer.n',
        'local_file.foo["#1"]',
        "resource.with space",
        'resource.with"quote',
        "resource.with$dollar",
    ]
    args = target_args(addresses)
    assert args == [f"-target={address}" for address in addresses]
    assert len(args) == len(addresses)


def test_build_puts_resolved_path_first() -> None:
    executor = TerraformExecutor(sys.executable, resolve=False)
    assert executor.build("show", "-json") == (sys.executable, "show", "-json")


# ------------------------------------------------------------- command result


def test_command_result_ok_and_raise() -> None:
    ok = CommandResult(("terraform", "show"), 0, "fine")
    assert ok.ok
    assert ok.raise_for_status() is ok

    bad = CommandResult(("terraform", "show"), 1, "Error: boom")
    assert not bad.ok
    with pytest.raises(TerraformError) as caught:
        bad.raise_for_status()
    assert "Error: boom" in str(caught.value)
    assert caught.value.returncode == 1


# --------------------------------------------------------------- real running


@pytest.fixture
def python_executor(tmp_path: Path) -> TerraformExecutor:
    return TerraformExecutor(sys.executable, cwd=tmp_path, resolve=False)


async def test_run_captures_output(python_executor: TerraformExecutor) -> None:
    result = await python_executor.run("-c", "print('hello')")
    assert result.ok
    assert result.output.strip() == "hello"


async def test_run_captures_stderr_too(python_executor: TerraformExecutor) -> None:
    result = await python_executor.run("-c", "import sys; sys.stderr.write('oops\\n'); sys.exit(3)")
    assert result.returncode == 3
    assert "oops" in result.output


async def test_run_check_raises(python_executor: TerraformExecutor) -> None:
    with pytest.raises(TerraformError):
        await python_executor.run("-c", "raise SystemExit(2)", check=True)


async def test_arguments_are_not_split_on_whitespace(
    python_executor: TerraformExecutor,
) -> None:
    """A single argument containing spaces stays a single argument."""
    result = await python_executor.run("-c", "import sys; print(sys.argv[1])", "a b c")
    assert result.output.strip() == "a b c"


async def test_shell_metacharacters_are_inert(python_executor: TerraformExecutor) -> None:
    """No shell is involved, so metacharacters arrive verbatim."""
    payload = "; rm -rf / #$(id)`whoami`"
    result = await python_executor.run("-c", "import sys; print(sys.argv[1])", payload)
    assert result.output.strip() == payload


async def test_runs_in_the_configured_directory(tmp_path: Path) -> None:
    executor = TerraformExecutor(sys.executable, cwd=tmp_path, resolve=False)
    result = await executor.run("-c", "import os; print(os.getcwd())")
    assert Path(result.output.strip()).resolve() == tmp_path.resolve()


async def test_stream_yields_lines_and_exit_code(
    python_executor: TerraformExecutor,
) -> None:
    codes: list[int] = []
    lines = [
        line
        async for line in python_executor.stream_with_result(
            "-c",
            "print('one'); print('two'); raise SystemExit(2)",
            sink=codes,
        )
    ]
    assert lines == ["one", "two"]
    assert codes == [2]


async def test_stdin_is_closed_so_terraform_cannot_prompt(
    python_executor: TerraformExecutor,
) -> None:
    result = await python_executor.run("-c", "import sys; print(repr(sys.stdin.read()))")
    assert result.output.strip() == "''"


async def test_automation_env_vars_are_set(python_executor: TerraformExecutor) -> None:
    result = await python_executor.run(
        "-c", "import os; print(os.environ['TF_IN_AUTOMATION'], os.environ['TF_INPUT'])"
    )
    assert result.output.strip() == "1 0"
