"""Command line parsing.

Every flag from previous releases keeps its short form, its long form and its
meaning. ``--chdir`` is the only addition, and it is optional.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from tftui.config import Settings
from tftui.version import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tftui",
        description="TFTUI - the Terraform terminal user interface",
        epilog=(
            "Every flag can also be set through an environment variable "
            "(TFTUI_EXECUTABLE, TFTUI_VAR_FILE, TFTUI_NO_INIT, TFTUI_OFFLINE, "
            "TFTUI_DISABLE_USAGE_TRACKING, TFTUI_LIGHT_MODE, TFTUI_DEBUG_LOG, "
            "TFTUI_WORKING_DIR). Flags win over the environment. Enjoy!"
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
        help="tfvars filename to be used in planning",
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


def parse_args(argv: Sequence[str] | None = None) -> tuple[Settings, bool]:
    """Parse ``argv`` into settings.

    Returns the settings and whether ``--version`` was requested.
    """
    args = build_parser().parse_args(argv)
    settings = Settings.from_env()

    if args.executable:
        settings = replace(settings, executable=args.executable)
    if args.var_file:
        settings = replace(settings, var_file=args.var_file)
    if args.chdir:
        settings = replace(settings, working_dir=Path(args.chdir))
    if args.no_init:
        settings = replace(settings, run_init=False)
    if args.offline:
        settings = replace(settings, offline=True)
    if args.disable_usage_tracking:
        settings = replace(settings, usage_tracking=False)
    if args.light_mode:
        settings = replace(settings, light_mode=True)
    if args.generate_debug_log:
        settings = replace(settings, debug_log=True)

    return settings, bool(args.version)


def version_banner(update_suffix: str = "") -> str:
    return f"\ntftui v{__version__}{update_suffix}\n"
