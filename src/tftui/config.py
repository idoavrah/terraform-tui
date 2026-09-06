"""Runtime settings, assembled from defaults, environment and the command line.

Precedence, lowest to highest: built-in defaults, ``TFTUI_*`` environment
variables, command-line flags. Environment support is new; every flag that
existed before keeps its short and long form.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"0", "false", "no", "off", ""})

DEFAULT_EXECUTABLE = "terraform"


@dataclass(frozen=True, slots=True)
class Settings:
    """Everything the application needs to know before it starts."""

    executable: str = DEFAULT_EXECUTABLE
    """The Terraform-compatible binary to drive (terraform, tofu, terragrunt...)."""

    var_file: str | None = None
    """Default ``-var-file`` offered when creating a plan."""

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
        source = os.environ if env is None else env
        settings = cls()

        executable = source.get("TFTUI_EXECUTABLE")
        var_file = source.get("TFTUI_VAR_FILE")
        working_dir = source.get("TFTUI_WORKING_DIR")

        return replace(
            settings,
            executable=executable or settings.executable,
            var_file=var_file or settings.var_file,
            working_dir=Path(working_dir) if working_dir else settings.working_dir,
            run_init=not _flag(source, "TFTUI_NO_INIT", default=False),
            offline=_flag(source, "TFTUI_OFFLINE", default=False),
            usage_tracking=not _flag(source, "TFTUI_DISABLE_USAGE_TRACKING", default=False),
            light_mode=_flag(source, "TFTUI_LIGHT_MODE", default=False),
            debug_log=_flag(source, "TFTUI_DEBUG_LOG", default=False),
        )


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
