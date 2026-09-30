"""Optional TOML configuration files.

Two files, either or neither of which may exist:

* a **user** file, for preferences that follow you between projects —
  ``$XDG_CONFIG_HOME/tftui/config.toml``, or ``~/.config/tftui/config.toml``;
* a **project** file, ``.tftui.toml``, read from the directory Terraform runs in,
  for settings that belong to one codebase (its var-files, its executable).

They sit at the bottom of the precedence order, below the environment and the
command line, so a config file can never stop a flag from doing what it says:

    defaults < user file < project file < TFTUI_* environment < flags

Keys are the long flag names without the leading dashes (``var-file``,
``no-init``); the snake_case spelling of each is accepted too, since that is
what most people type in TOML. An unrecognised key is reported rather than
ignored silently, because a typo in a config file is otherwise invisible.

``chdir`` is accepted only in the user file. In a project file it would be
circular — the file is found *because* the working directory is already known.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # Python 3.10 is supported by the project, and predates tomllib.
    import tomli as tomllib

PROJECT_FILE = ".tftui.toml"
USER_FILE = Path("tftui") / "config.toml"

#: Config key -> the ``Settings`` field it sets, and whether the value is negated.
#: Negated keys exist because the flags are written as opt-outs (``--no-init``
#: turns ``run_init`` off), and the file should read like the flag, not like the
#: internal field.
_KEYS: dict[str, tuple[str, bool]] = {
    "executable": ("executable", False),
    "var-file": ("var_files", False),
    "no-init": ("run_init", True),
    "offline": ("offline", False),
    "disable-usage-tracking": ("usage_tracking", True),
    "light-mode": ("light_mode", False),
    "generate-debug-log": ("debug_log", False),
    "chdir": ("working_dir", False),
}

#: Only the user file may set the working directory.
_USER_ONLY = frozenset({"chdir"})

_BOOL_FIELDS = frozenset({"run_init", "offline", "usage_tracking", "light_mode", "debug_log"})


@dataclass(frozen=True, slots=True)
class LoadedConfig:
    """What the config files asked for, and anything wrong with how they asked."""

    values: dict[str, Any] = field(default_factory=dict)
    """Settings fields to override. Only keys the files actually set appear."""

    warnings: tuple[str, ...] = ()
    """Problems worth telling the user about: bad keys, bad types, bad TOML."""

    sources: tuple[Path, ...] = ()
    """The files that were read, in the order they were applied."""


def user_config_path(env: dict[str, str] | None = None) -> Path:
    """Where the user-level config file lives, honouring ``XDG_CONFIG_HOME``."""
    source = os.environ if env is None else env
    xdg = source.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / USER_FILE


def project_config_path(directory: Path) -> Path:
    return directory / PROJECT_FILE


def load(*, working_dir: Path, env: dict[str, str] | None = None) -> LoadedConfig:
    """Read both config files and merge them, user file first.

    Missing files are not an error — neither is required. A file that cannot be
    parsed is reported and skipped rather than taking the application down,
    because a broken config file should not make tftui unusable.
    """
    values: dict[str, Any] = {}
    warnings: list[str] = []
    sources: list[Path] = []

    files = ((user_config_path(env), True), (project_config_path(working_dir), False))
    for path, user_level in files:
        parsed = _read(path, warnings)
        if parsed is None:
            continue
        sources.append(path)
        values.update(_interpret(parsed, path, user_level=user_level, warnings=warnings))

    return LoadedConfig(values=values, warnings=tuple(warnings), sources=tuple(sources))


def _read(path: Path, warnings: list[str]) -> dict[str, Any] | None:
    """Parse one file. ``None`` when it does not exist or cannot be used."""
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as error:
        warnings.append(f"{path}: cannot be read ({error.strerror or error})")
        return None

    try:
        parsed: dict[str, Any] = tomllib.loads(raw.decode("utf-8"))
    except UnicodeDecodeError:
        warnings.append(f"{path}: is not valid UTF-8; ignored")
        return None
    except tomllib.TOMLDecodeError as error:
        warnings.append(f"{path}: is not valid TOML ({error}); ignored")
        return None
    return parsed


def _interpret(
    parsed: dict[str, Any], path: Path, *, user_level: bool, warnings: list[str]
) -> dict[str, Any]:
    """Turn one file's contents into ``Settings`` field overrides."""
    values: dict[str, Any] = {}

    for raw_key, value in parsed.items():
        key = raw_key.replace("_", "-")
        entry = _KEYS.get(key)
        if entry is None:
            warnings.append(f"{path}: unknown setting {raw_key!r}; ignored")
            continue
        if key in _USER_ONLY and not user_level:
            warnings.append(f"{path}: {raw_key!r} only applies in the user config file; ignored")
            continue

        field_name, negated = entry
        converted = _convert(field_name, value, raw_key, path, warnings)
        if converted is not _INVALID:
            values[field_name] = (not converted) if negated else converted

    return values


class _Invalid:
    """Sentinel: the value could not be used, and has been reported."""


_INVALID = _Invalid()


def _convert(field_name: str, value: Any, raw_key: str, path: Path, warnings: list[str]) -> Any:
    """Coerce and validate one value, reporting anything unusable."""
    if field_name in _BOOL_FIELDS:
        if isinstance(value, bool):
            return value
        warnings.append(f"{path}: {raw_key!r} must be true or false; ignored")
        return _INVALID

    if field_name == "var_files":
        if isinstance(value, str):
            return (value,)
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return tuple(value)
        warnings.append(f"{path}: {raw_key!r} must be a string or a list of strings; ignored")
        return _INVALID

    if field_name == "working_dir":
        if isinstance(value, str) and value:
            return Path(value).expanduser()
        warnings.append(f"{path}: {raw_key!r} must be a non-empty string; ignored")
        return _INVALID

    # executable
    if isinstance(value, str) and value:
        return value
    warnings.append(f"{path}: {raw_key!r} must be a non-empty string; ignored")
    return _INVALID
