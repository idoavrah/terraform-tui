"""Entry point: wire settings, logging, telemetry and Terraform, then run the app."""

from __future__ import annotations

import sys

from tftui.app import TerraformTUI
from tftui.cli import parse_args, version_banner
from tftui.config import Settings
from tftui.errors import TftuiError
from tftui.logging_setup import configure_logging
from tftui.telemetry import Telemetry
from tftui.terraform.client import TerraformClient
from tftui.terraform.executor import TerraformExecutor
from tftui.version import __version__

FAREWELL = """
For questions and suggestions: https://github.com/idoavrah/terraform-tui/discussions
For issues and bugs:           https://github.com/idoavrah/terraform-tui/issues

Bye!
"""


def main(argv: list[str] | None = None) -> int:
    """Run tftui. Returns the process exit code."""
    settings, wants_version = parse_args(argv)

    telemetry = Telemetry(
        enabled=settings.telemetry_enabled,
        check_updates=settings.version_check_enabled,
    )

    if wants_version:
        telemetry.refresh_update_check()
        print(version_banner(telemetry.update_suffix))
        return 0

    logger = configure_logging(debug=settings.debug_log, directory=settings.directory)
    logger.debug("starting tftui v%s with %s", __version__, settings)

    telemetry.start_update_check()

    try:
        client = _build_client(settings)
    except TftuiError as error:
        print(error, file=sys.stderr)
        telemetry.shutdown()
        return 1

    telemetry.capture("started application", **telemetry.platform_properties())

    exit_code = _run(client, settings, telemetry)

    if telemetry.update_available:
        print("\n*** A new version of tftui is available. ***")
    print(FAREWELL)

    telemetry.shutdown()
    return exit_code


def _build_client(settings: Settings) -> TerraformClient:
    directory = settings.directory
    if not directory.is_dir():
        raise TftuiError(f"Working directory {directory} does not exist.")
    executor = TerraformExecutor(settings.executable, cwd=directory)
    return TerraformClient(executor)


def _run(client: TerraformClient, settings: Settings, telemetry: Telemetry) -> int:
    app = TerraformTUI(client, settings, telemetry)
    try:
        result = app.run()
    finally:
        client.cleanup()

    if app.error_message:
        telemetry.capture_error("exited unsuccessfully", app.error_message)
        print(app.error_message, file=sys.stderr)
        return 1

    if result:
        # The app exited deliberately with a message: a Terraform failure the
        # user needs to read, not a crash.
        print(result, file=sys.stderr)
        telemetry.capture_error("exited unsuccessfully", result)
        return app.return_code or 1

    telemetry.capture("exited successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
