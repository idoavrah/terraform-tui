"""Exception hierarchy for tftui.

Every failure that the UI is expected to render travels as a ``TftuiError``.
Anything else escaping to the top level is a genuine bug and is reported as such.
"""

from __future__ import annotations


class TftuiError(Exception):
    """Base class for every expected, user-facing tftui failure."""


class ExecutableNotFoundError(TftuiError):
    """The configured terraform executable could not be located on PATH."""

    def __init__(self, executable: str) -> None:
        super().__init__(f"Executable {executable!r} not found. Please install it and try again.")
        self.executable = executable


class InvalidExecutableError(TftuiError):
    """The configured executable name is not a plausible command name."""

    def __init__(self, executable: str) -> None:
        super().__init__(
            f"Executable {executable!r} is not a valid command name. "
            "Provide a bare command (e.g. 'terraform', 'tofu', 'terragrunt') or a path to one."
        )
        self.executable = executable


class TerraformError(TftuiError):
    """A terraform invocation exited non-zero."""

    def __init__(self, command: str, returncode: int, output: str) -> None:
        super().__init__(output.strip() or f"{command} exited with code {returncode}")
        self.command = command
        self.returncode = returncode
        self.output = output


class StateParseError(TftuiError):
    """`terraform show` produced output that could not be parsed."""
