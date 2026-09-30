"""Runtime settings, assembled from defaults, environment and the command line.

Precedence, lowest to highest: built-in defaults, ``TFTUI_*`` environment
variables, command-line flags. Environment support is new; every flag that
existed before keeps its short and long form.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any


def split_var_files(value: str | None) -> tuple[str, ...]:
    """Split a ``TFTUI_VAR_FILE`` value into individual files.

    Uses the platform list separator (``:`` on POSIX, ``;`` on Windows) so that
    several files can be given in one variable.
    """
    if not value:
        return ()
    return tuple(part.strip() for part in value.split(os.pathsep) if part.strip())


_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"0", "false", "no", "off", ""})

DEFAULT_EXECUTABLE = "terraform"


@dataclass(frozen=True, slots=True)
class Settings:
    """Everything the application needs to know before it starts."""

    executable: str = DEFAULT_EXECUTABLE
    """The Terraform-compatible binary to drive (terraform, tofu, terragrunt...)."""

    var_files: tuple[str, ...] = ()
    """Default ``-var-file`` arguments, in order, for init and plan.

    OpenTofu 1.8 evaluates variables early enough to use them in a backend
    block, so these are passed to ``init`` as well as to ``plan``.
    """

    run_init: bool = True
    """Whether to run ``terraform init`` on startup."""

    offline: bool = False
    """Suppress every outbound call: version check and usage tracking alike."""

    usage_tracking: bool = True
    """Whether anonymous usage tracking is enabled (opt-out)."""

    light_mode: bool = False
    """Start in the light theme rather than the dark one."""

    debug_log: bool = False
    """Write a verbose ``tftui.log`` into the working directory."""

    working_dir: Path | None = None
    """Directory to run Terraform in. Defaults to the current directory."""

    @property
    def telemetry_enabled(self) -> bool:
        """Usage tracking only happens when it is enabled *and* we are online."""
        return self.usage_tracking and not self.offline

    @property
    def version_check_enabled(self) -> bool:
        return not self.offline

    @property
    def directory(self) -> Path:
        return self.working_dir if self.working_dir is not None else Path.cwd()

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Settings:
        """Build settings from ``TFTUI_*`` environment variables."""
        return replace(cls(), **env_overrides(env))


def env_overrides(env: dict[str, str] | None = None) -> dict[str, Any]:
    """The settings the environment actually asks for, and only those.

    Returning just the keys that are present is what lets a config file sit
    *below* the environment in the precedence order: an unset variable has to be
    distinguishable from one set to its default, which a fully-populated
    ``Settings`` cannot express.
    """
    source = os.environ if env is None else env
    values: dict[str, Any] = {}

    executable = source.get("TFTUI_EXECUTABLE")
    if executable:
        values["executable"] = executable

    var_files = split_var_files(source.get("TFTUI_VAR_FILE"))
    if var_files:
        values["var_files"] = var_files

    working_dir = source.get("TFTUI_WORKING_DIR")
    if working_dir:
        values["working_dir"] = Path(working_dir)

    for name, key, negated in (
        ("TFTUI_NO_INIT", "run_init", True),
        ("TFTUI_OFFLINE", "offline", False),
        ("TFTUI_DISABLE_USAGE_TRACKING", "usage_tracking", True),
        ("TFTUI_LIGHT_MODE", "light_mode", False),
        ("TFTUI_DEBUG_LOG", "debug_log", False),
    ):
        if name in source:
            flag = _flag(source, name, default=False)
            values[key] = (not flag) if negated else flag

    return values


def _flag(source: dict[str, str] | os._Environ[str], name: str, *, default: bool) -> bool:
    """Interpret an environment variable as a boolean."""
    raw = source.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    return default
