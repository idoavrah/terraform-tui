"""Shared fixtures.

The unit and e2e suites never touch a real Terraform binary: they drive the
real :class:`TerraformClient` over a stub executor fed with output captured
from an actual ``terraform show``. The integration suite (``-m integration``)
is the one that shells out for real.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator, Sequence
from pathlib import Path

import pytest

from tftui.config import Settings
from tftui.terraform.client import TerraformClient
from tftui.terraform.executor import CommandResult
from tftui.terraform.state import State, parse_state

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def state_text() -> str:
    """Captured output of ``terraform show -no-color`` for the example project."""
    return (FIXTURES / "state_show.txt").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def state_json() -> str:
    """Captured output of ``terraform show -json`` for the same state."""
    return (FIXTURES / "state_show.json").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def plan_text() -> str:
    """Captured output of ``terraform plan`` with changes pending."""
    return (FIXTURES / "plan_changes.txt").read_text(encoding="utf-8")


@pytest.fixture
def state(state_text: str) -> State:
    return parse_state(state_text)


class StubExecutor:
    """A drop-in for :class:`TerraformExecutor` backed by canned output.

    Commands are matched on a prefix of their arguments, so a test can stub
    ``show`` without caring about the flags the client chooses to pass.
    """

    def __init__(self, responses: dict[tuple[str, ...], tuple[int, str]]) -> None:
        self.name = "terraform"
        self.path = "/usr/bin/terraform"
        self.cwd = Path("/tmp/project")
        self.responses = responses
        self.calls: list[tuple[str, ...]] = []

    def _lookup(self, args: Sequence[str]) -> tuple[int, str]:
        for prefix, response in self.responses.items():
            if tuple(args[: len(prefix)]) == prefix:
                return response
        return (1, f"stub has no response for {' '.join(args)}")

    def build(self, *args: str) -> tuple[str, ...]:
        return (self.path, *args)

    async def run(self, *args: str, check: bool = False) -> CommandResult:
        self.calls.append(args)
        returncode, output = self._lookup(args)
        result = CommandResult(self.build(*args), returncode, output)
        return result.raise_for_status() if check else result

    async def stream_with_result(self, *args: str, sink: list[int] | None) -> AsyncIterator[str]:
        self.calls.append(args)
        returncode, output = self._lookup(args)
        # Behave like terraform: a plan that finds changes writes its -out file,
        # so tests can check that the file is really created and really removed.
        if args and args[0] == "plan" and returncode == 2:
            for arg in args:
                if arg.startswith("-out="):
                    Path(arg.removeprefix("-out=")).write_text("stub plan")
        try:
            for line in output.splitlines():
                yield line
        finally:
            if sink is not None:
                sink.append(returncode)


@pytest.fixture
def responses(state_text: str, state_json: str, plan_text: str) -> dict:
    """The default canned command set: a populated state, no plan yet."""
    return {
        ("init",): (0, "Terraform has been successfully initialized!"),
        ("show", "-no-color"): (0, state_text),
        ("show", "-json"): (0, state_json),
        ("workspace", "list"): (0, "* default\n  staging\n  production\n"),
        ("workspace", "show"): (0, "default\n"),
        ("workspace", "select"): (0, ""),
        ("taint",): (0, "Resource instance ... has been marked as tainted."),
        ("untaint",): (0, "Resource instance ... has been successfully untainted."),
        ("state", "rm"): (0, "Removed ...\nSuccessfully removed 1 resource instance(s)."),
        ("plan",): (2, plan_text),
        ("apply",): (0, "Apply complete! Resources: 1 added, 0 changed, 0 destroyed."),
    }


@pytest.fixture
def stub(responses: dict) -> StubExecutor:
    return StubExecutor(responses)


@pytest.fixture
def client(stub: StubExecutor) -> Iterator[TerraformClient]:
    terraform = TerraformClient(stub)  # type: ignore[arg-type]
    yield terraform
    terraform.cleanup()


@pytest.fixture
def settings() -> Settings:
    """Settings that keep tests hermetic: no init, no network, no tracking."""
    return Settings(run_init=False, offline=True, usage_tracking=False)


@pytest.fixture
def sensitive_addresses(state_json: str) -> set[str]:
    document = json.loads(state_json)
    found: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            sensitive = node.get("sensitive_values")
            address = node.get("address")
            if isinstance(address, str) and isinstance(sensitive, dict) and any(sensitive.values()):
                found.add(address)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(document)
    return found
