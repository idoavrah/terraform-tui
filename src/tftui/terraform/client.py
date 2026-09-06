"""High-level Terraform operations used by the UI.

This is the only layer that knows which Terraform subcommands exist. The UI
talks to it in terms of resources and plans, never in terms of argv.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import tempfile
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from tftui.errors import TerraformError
from tftui.terraform.executor import CommandResult, TerraformExecutor, target_args
from tftui.terraform.state import State, extract_sensitive_values, parse_state

logger = logging.getLogger(__name__)

#: Operations that may be applied to a selection of resources.
Operation = str
TAINT: Operation = "taint"
UNTAINT: Operation = "untaint"
DELETE: Operation = "delete"

_OPERATION_ARGS: dict[Operation, tuple[str, ...]] = {
    TAINT: ("taint",),
    UNTAINT: ("untaint",),
    DELETE: ("state", "rm"),
}


@dataclass(slots=True)
class LoadedState:
    """A parsed state plus the sensitive values recovered alongside it."""

    state: State
    secrets: dict[str, dict[str, str]]

    def secrets_for(self, address: str) -> dict[str, str]:
        return self.secrets.get(address, {})


@dataclass(slots=True)
class Workspaces:
    names: tuple[str, ...]
    current: str


class TerraformClient:
    """Terraform operations, expressed in the vocabulary the UI cares about."""

    def __init__(self, executor: TerraformExecutor) -> None:
        self._exec = executor
        self._plan_dir: Path | None = None
        self._plan_file: Path | None = None

    # ------------------------------------------------------------------ meta

    @property
    def executable(self) -> str:
        return self._exec.name

    @property
    def cwd(self) -> Path:
        return self._exec.cwd

    @property
    def plan_file(self) -> Path | None:
        """The plan file produced by the most recent successful plan, if any."""
        return self._plan_file

    async def version(self) -> str:
        result = await self._exec.run("version", "-json")
        if not result.ok:
            return ""
        try:
            return str(json.loads(result.output).get("terraform_version", ""))
        except (json.JSONDecodeError, AttributeError):
            return ""

    async def init(self) -> CommandResult:
        """Run ``terraform init``. Safe to call when already initialised."""
        return await self._exec.run("init", "-no-color", "-input=false")

    # ----------------------------------------------------------------- state

    async def load_state(self) -> LoadedState:
        """Read the state twice, concurrently: once as text, once as JSON.

        The text form is what the UI renders; the JSON form only supplies real
        values for attributes the text form redacts. A failure to read the JSON
        is not fatal - the UI simply cannot reveal secrets for that run.
        """
        text_task = asyncio.create_task(self._exec.run("show", "-no-color"))
        json_task = asyncio.create_task(self._exec.run("show", "-json"))

        try:
            text_result = await text_task
        except BaseException:
            json_task.cancel()
            raise

        if not text_result.ok:
            json_task.cancel()
            raise TerraformError(text_result.command, text_result.returncode, text_result.output)

        state = parse_state(text_result.output)

        secrets: dict[str, dict[str, str]] = {}
        try:
            json_result = await json_task
            if json_result.ok:
                secrets = extract_sensitive_values(json.loads(json_result.output))
        except asyncio.CancelledError:
            raise
        except (json.JSONDecodeError, OSError, ValueError) as error:
            logger.warning("could not read sensitive values: %s", error)

        return LoadedState(state=state, secrets=secrets)

    # ------------------------------------------------------------ operations

    async def operate(self, operation: Operation, addresses: Sequence[str]) -> list[CommandResult]:
        """Apply ``operation`` to each address, stopping at the first failure."""
        args = _OPERATION_ARGS[operation]
        results: list[CommandResult] = []
        for address in addresses:
            result = await self._exec.run(*args, "-no-color", address)
            results.append(result)
            if not result.ok:
                logger.error("%s failed for %s: %s", operation, address, result.output)
                break
        return results

    # ------------------------------------------------------------ workspaces

    async def workspaces(self) -> Workspaces:
        """List workspaces and identify the active one."""
        result = (await self._exec.run("workspace", "list", "-no-color")).raise_for_status()

        names: list[str] = []
        current = ""
        for raw in result.output.splitlines():
            line = raw.strip()
            if not line:
                continue
            active = line.startswith("*")
            name = line.removeprefix("*").strip()
            if not name:
                continue
            names.append(name)
            if active:
                current = name

        return Workspaces(names=tuple(names), current=current or (names[0] if names else ""))

    async def current_workspace(self) -> str:
        result = await self._exec.run("workspace", "show", "-no-color")
        return result.output.strip() if result.ok else ""

    async def select_workspace(self, name: str) -> CommandResult:
        return await self._exec.run("workspace", "select", "-no-color", name)

    # ------------------------------------------------------------------ plan

    async def plan(
        self,
        *,
        var_file: str | None = None,
        targets: Sequence[str] = (),
        destroy: bool = False,
    ) -> AsyncIterator[str]:
        """Stream a ``terraform plan``, writing the plan to a private temp file.

        The plan file is written under a 0700 temporary directory rather than
        into the working directory: plan files embed resource attributes,
        including values Terraform marks sensitive, and leaving one lying
        around in a repo is an easy way to commit a secret by accident.
        """
        plan_path = self._new_plan_path()
        args = [
            "plan",
            "-no-color",
            "-input=false",
            "-detailed-exitcode",
            f"-out={plan_path}",
        ]
        if var_file:
            args.append(f"-var-file={var_file}")
        if destroy:
            args.append("-destroy")
        args.extend(target_args(targets))

        exit_codes: list[int] = []
        async for line in self._exec.stream_with_result(*args, sink=exit_codes):
            yield line

        code = exit_codes[0] if exit_codes else -1
        if code == 2:
            self._plan_file = plan_path
        else:
            self._plan_file = None
            plan_path.unlink(missing_ok=True)

    async def apply(self) -> AsyncIterator[str]:
        """Stream ``terraform apply`` of the saved plan, then discard the plan."""
        plan_path = self._plan_file
        if plan_path is None:
            raise TerraformError("apply", 1, "No active plan to apply.")

        exit_codes: list[int] = []
        try:
            async for line in self._exec.stream_with_result(
                "apply", "-no-color", "-input=false", str(plan_path), sink=exit_codes
            ):
                yield line
        finally:
            # A plan can only be applied once; drop it either way so a stale
            # plan can never be applied against a state that has moved on.
            self._plan_file = None
            plan_path.unlink(missing_ok=True)

    def discard_plan(self) -> None:
        """Forget and delete any saved plan."""
        if self._plan_file is not None:
            self._plan_file.unlink(missing_ok=True)
            self._plan_file = None

    def cleanup(self) -> None:
        """Remove the private plan directory. Safe to call more than once."""
        self._plan_file = None
        if self._plan_dir is not None:
            shutil.rmtree(self._plan_dir, ignore_errors=True)
            self._plan_dir = None

    def _new_plan_path(self) -> Path:
        if self._plan_dir is None:
            self._plan_dir = Path(tempfile.mkdtemp(prefix="tftui-"))
        self.discard_plan()
        return self._plan_dir / "tftui.plan"
