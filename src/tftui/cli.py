"""Command line parsing, and the precedence order everything resolves through.

Every flag from previous releases keeps its short form, its long form and its
meaning. Lowest to highest:

    defaults < user config file < project config file < TFTUI_* environment < flags

The working directory has to be settled before the project config file can be
found, so it is resolved from the layers above the project file first, and the
project file is then read from wherever that landed.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from tftui import config_file
from tftui.config import Settings, env_overrides
from tftui.version import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tftui",
        description="TFTUI - the Terraform terminal user interface",
        epilog=(
            "Every flag can also be set through an environment variable "
            "(TFTUI_EXECUTABLE, TFTUI_VAR_FILE, TFTUI_NO_INIT, TFTUI_OFFLINE, "
            "TFTUI_DISABLE_USAGE_TRACKING, TFTUI_LIGHT_MODE, TFTUI_DEBUG_LOG, "
            "TFTUI_WORKING_DIR), or in a .tftui.toml beside your Terraform files "
            "or ~/.config/tftui/config.toml. Flags win over the environment, "
            "which wins over the files. Enjoy!"
        ),
    )
    parser.add_argument(
        "-e",
        "--executable",
        metavar="COMMAND",
        help="set executable command (default 'terraform')",
    )
    parser.add_argument(
        "-n",
        "--no-init",
        action="store_true",
        default=None,
        help="do not run terraform init on startup (default run)",
    )
    parser.add_argument(
        "-f",
        "--var-file",
        metavar="FILE",
        action="append",
        dest="var_files",
        help="tfvars filename to use; repeat the flag for several files",
    )
    parser.add_argument(
        "-o",
        "--offline",
        action="store_true",
        default=None,
        help="run in offline mode (i.e. no outbound API calls; default online)",
    )
    parser.add_argument(
        "-d",
        "--disable-usage-tracking",
        action="store_true",
        default=None,
        help="disable usage tracking (default enabled)",
    )
    parser.add_argument(
        "-l",
        "--light-mode",
        action="store_true",
        default=None,
        help="enable light mode (default dark)",
    )
    parser.add_argument(
        "-g",
        "--generate-debug-log",
        action="store_true",
        default=None,
        help="generate debug log file (default disabled)",
    )
    parser.add_argument(
        "-C",
        "--chdir",
        metavar="DIR",
        help="switch to DIR before running terraform (default current directory)",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="store_true",
        help="show version information",
    )
    return parser


def flag_overrides(args: argparse.Namespace) -> dict[str, Any]:
    """The settings the command line actually asks for, and only those.

    The boolean flags default to ``None`` rather than ``False`` precisely so that
    "not passed" can be told from "passed", which is what keeps a flag's absence
    from overriding a config file.
    """
    values: dict[str, Any] = {}
    if args.executable:
        values["executable"] = args.executable
    if args.var_files:
        values["var_files"] = tuple(args.var_files)
    if args.chdir:
        values["working_dir"] = Path(args.chdir)
    if args.no_init:
        values["run_init"] = False
    if args.offline:
        values["offline"] = True
    if args.disable_usage_tracking:
        values["usage_tracking"] = False
    if args.light_mode:
        values["light_mode"] = True
    if args.generate_debug_log:
        values["debug_log"] = True
    return values


def resolve(
    argv: Sequence[str] | None = None,
    *,
    env: dict[str, str] | None = None,
) -> tuple[Settings, bool, tuple[str, ...]]:
    """Resolve every source into one ``Settings``.

    Returns the settings, whether ``--version`` was asked for, and any warnings
    the config files produced — a bad key or unparseable TOML is reported to the
    user rather than silently dropped.
    """
    args = build_parser().parse_args(argv)
    flags = flag_overrides(args)
    environment = env_overrides(env)

    # Where the project file lives depends on --chdir / TFTUI_WORKING_DIR, so the
    # working directory is settled first, from every layer that outranks it.
    user_only = config_file.load(working_dir=Path.cwd(), env=env)
    provisional = replace(Settings(), **{**user_only.values, **environment, **flags})

    loaded = config_file.load(working_dir=provisional.directory, env=env)
    settings = replace(Settings(), **{**loaded.values, **environment, **flags})

    return settings, bool(args.version), loaded.warnings


def parse_args(argv: Sequence[str] | None = None) -> tuple[Settings, bool]:
    """Resolve settings, discarding config-file warnings.

    Kept for callers that do not surface warnings.
    """
    settings, wants_version, _ = resolve(argv)
    return settings, wants_version


def version_banner(update_suffix: str = "") -> str:
    return f"\ntftui v{__version__}{update_suffix}\n"
