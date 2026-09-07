"""Asynchronous execution of the terraform (or compatible) binary.

Design notes
------------
* Commands are always built as an argument **list** and executed with
  :func:`asyncio.create_subprocess_exec`. There is no shell anywhere in this
  module, and arguments are never re-split on whitespace, so resource
  addresses containing spaces, quotes or shell metacharacters are safe.
* The executable is resolved once, up front, via :func:`shutil.which` and is
  validated against a conservative pattern so a hostile ``--executable`` value
  cannot smuggle in shell syntax.
* Long-running commands stream their output line by line so the UI can render
  progress instead of freezing until completion.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
from collections.abc import AsyncIterator, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path, PurePath

from tftui.errors import ExecutableNotFoundError, InvalidExecutableError, TerraformError

logger = logging.getLogger(__name__)

# One component of a command name or of a path to one. Spaces are allowed
# because `C:\Program Files\Terraform\terraform.exe` is the ordinary Windows
# install location; every shell metacharacter is still excluded.
_PATH_COMPONENT = re.compile(r"^[A-Za-z0-9._+ -]+$")


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Outcome of a completed command."""

    args: tuple[str, ...]
    returncode: int
    output: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    @property
    def command(self) -> str:
        return " ".join(self.args)

    def raise_for_status(self) -> CommandResult:
        """Return self, or raise :class:`TerraformError` if the command failed."""
        if not self.ok:
            raise TerraformError(self.command, self.returncode, self.output)
        return self


def is_plausible_command(candidate: str, flavour: type[PurePath] = PurePath) -> bool:
    """Whether ``candidate`` looks like a command name, or a path to one.

    ``flavour`` selects the path syntax and defaults to the running platform's.
    Passing :class:`PureWindowsPath` or :class:`PurePosixPath` explicitly lets
    either platform's behaviour be tested from the other.

    The path's anchor - ``/`` on POSIX, ``C:\\`` or ``\\\\server\\share\\`` on
    Windows - is excluded from the check. It comes from the path parser rather
    than from the user, so it cannot smuggle anything in, and requiring it to
    match a command-name pattern rejects every absolute Windows path.
    """
    if not candidate:
        return False
    path = flavour(candidate)
    parts = path.parts[1:] if path.anchor else path.parts
    return bool(parts) and all(_PATH_COMPONENT.match(part) for part in parts)


def resolve_executable(executable: str) -> str:
    """Validate and resolve ``executable`` to an absolute path.

    Raises:
        InvalidExecutableError: if the name contains shell metacharacters.
        ExecutableNotFoundError: if it cannot be found on PATH.
    """
    candidate = executable.strip()
    if not is_plausible_command(candidate):
        raise InvalidExecutableError(executable)

    for name in (candidate, f"{candidate}.exe"):
        found = shutil.which(name)
        if found:
            return found

    raise ExecutableNotFoundError(executable)


class TerraformExecutor:
    """Runs terraform commands in a fixed working directory."""

    def __init__(
        self,
        executable: str = "terraform",
        *,
        cwd: Path | None = None,
        resolve: bool = True,
    ) -> None:
        self.name = executable
        self.path = resolve_executable(executable) if resolve else executable
        self.cwd = Path(cwd) if cwd is not None else Path.cwd()

    def build(self, *args: str) -> tuple[str, ...]:
        """Build the full argv for ``args``, with the resolved executable in front."""
        return (self.path, *args)

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        # Terraform must never try to open an editor or prompt: the TUI owns the tty.
        env.setdefault("TF_IN_AUTOMATION", "1")
        env.setdefault("TF_INPUT", "0")
        env.setdefault("CHECKPOINT_DISABLE", "1")
        return env

    async def run(self, *args: str, check: bool = False) -> CommandResult:
        """Run a command to completion and capture its combined output."""
        argv = self.build(*args)
        logger.debug("exec: %s (cwd=%s)", argv, self.cwd)

        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            stdin=asyncio.subprocess.DEVNULL,
            cwd=self.cwd,
            env=self._env(),
        )
        try:
            stdout, _ = await proc.communicate()
        except asyncio.CancelledError:
            _terminate(proc)
            raise

        output = stdout.decode("utf-8", errors="replace")
        returncode = proc.returncode if proc.returncode is not None else -1
        logger.debug("exec done: %s -> %s (%d bytes)", args, returncode, len(output))

        result = CommandResult(argv, returncode, output)
        return result.raise_for_status() if check else result

    async def stream(self, *args: str) -> AsyncIterator[str]:
        """Run a command, yielding output lines as they arrive.

        The final item yielded is never a line: callers should use
        :meth:`stream_with_result` when they also need the exit code.
        """
        async for line in self.stream_with_result(*args, sink=None):
            yield line

    async def stream_with_result(
        self,
        *args: str,
        sink: list[int] | None,
    ) -> AsyncIterator[str]:
        """Stream output lines; append the return code to ``sink`` when finished."""
        argv = self.build(*args)
        logger.debug("stream: %s (cwd=%s)", argv, self.cwd)

        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            stdin=asyncio.subprocess.DEVNULL,
            cwd=self.cwd,
            env=self._env(),
        )
        assert proc.stdout is not None  # noqa: S101 - guaranteed by PIPE above

        try:
            while True:
                try:
                    raw = await proc.stdout.readline()
                except ValueError:
                    # A single line exceeded the stream buffer limit; skip it rather
                    # than aborting the whole run.
                    logger.warning("dropping over-long output line from %s", args)
                    continue
                if not raw:
                    break
                yield raw.decode("utf-8", errors="replace").rstrip("\r\n")
        except asyncio.CancelledError:
            _terminate(proc)
            raise
        finally:
            with_code = await _wait_quietly(proc)
            if sink is not None:
                sink.append(with_code)


def _terminate(proc: asyncio.subprocess.Process) -> None:
    """Best-effort termination of a subprocess we are abandoning."""
    if proc.returncode is None:
        with suppress(ProcessLookupError):  # may have exited on its own already
            proc.terminate()


async def _wait_quietly(proc: asyncio.subprocess.Process) -> int:
    try:
        return await proc.wait()
    except asyncio.CancelledError:  # pragma: no cover - shutdown path
        _terminate(proc)
        raise


def var_file_args(var_files: Sequence[str]) -> list[str]:
    """Render var-file paths as ``-var-file=`` arguments, in the order given.

    Order matters: Terraform lets a later file override an earlier one.
    """
    return [f"-var-file={var_file}" for var_file in var_files]


def target_args(targets: Sequence[str]) -> list[str]:
    """Render resource addresses as ``-target=`` arguments.

    Each address is passed as its own argv entry, so no quoting is required and
    addresses containing ``"``, spaces or ``$`` are handled correctly.
    """
    return [f"-target={target}" for target in targets]
