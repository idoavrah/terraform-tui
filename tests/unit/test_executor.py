"""Process execution - the security-sensitive layer."""

from __future__ import annotations

import sys
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from tftui.errors import ExecutableNotFoundError, InvalidExecutableError, TerraformError
from tftui.terraform.executor import (
    CommandResult,
    TerraformExecutor,
    is_plausible_command,
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


# The two path flavours are checked explicitly rather than only on the running
# platform: an absolute Windows path was rejected outright, and CI on Linux and
# macOS could not have caught it.


@pytest.mark.parametrize(
    "candidate",
    [
        r"D:\a\terraform-tui\.venv\Scripts\python.exe",
        r"C:\Program Files\Terraform\terraform.exe",  # the usual install location
        r"C:\tools\terraform.exe",
        r"\\server\share\terraform.exe",  # UNC
        r"..\tools\terraform.exe",
        "terraform.exe",
    ],
)
def test_accepts_real_windows_paths(candidate: str) -> None:
    assert is_plausible_command(candidate, PureWindowsPath)


@pytest.mark.parametrize(
    "candidate",
    [
        "/usr/local/bin/terraform",
        "/usr/bin/tofu",
        "./bin/terraform",
        "terraform",
    ],
)
def test_accepts_real_posix_paths(candidate: str) -> None:
    assert is_plausible_command(candidate, PurePosixPath)


@pytest.mark.parametrize(
    "hostile",
    [
        "terraform; rm -rf /",
        "terraform && curl evil.example",
        "$(whoami)",
        "`id`",
        "terraform\nrm -rf /",
        "",
    ],
)
@pytest.mark.parametrize("flavour", [PureWindowsPath, PurePosixPath])
def test_shell_syntax_is_rejected_on_both_flavours(hostile: str, flavour: type) -> None:
    assert not is_plausible_command(hostile, flavour)


@pytest.mark.parametrize(
    "hostile",
    [
        r"C:\tools\terra;form.exe",
        r"C:\tools\$(id)\terraform.exe",
        r"C:\tools\a|b\terraform.exe",
    ],
)
def test_shell_syntax_inside_a_windows_path_is_rejected(hostile: str) -> None:
    """The drive anchor is skipped, but every other component is still checked."""
    assert not is_plausible_command(hostile, PureWindowsPath)


def test_a_name_with_a_space_is_not_found_rather_than_invalid() -> None:
    """Spaces are legal in a path, so this is a lookup failure, not a syntax one."""
    with pytest.raises(ExecutableNotFoundError):
        resolve_executable("terra form")


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
