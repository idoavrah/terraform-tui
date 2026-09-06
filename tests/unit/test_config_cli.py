"""Settings resolution: defaults, environment, then flags."""

from __future__ import annotations

from pathlib import Path

import pytest

from tftui.cli import parse_args
from tftui.config import Settings


def test_defaults() -> None:
    settings = Settings()
    assert settings.executable == "terraform"
    assert settings.run_init is True
    assert settings.offline is False
    assert settings.usage_tracking is True
    assert settings.telemetry_enabled is True
    assert settings.version_check_enabled is True


def test_offline_disables_every_outbound_call() -> None:
    settings = Settings(offline=True)
    assert settings.telemetry_enabled is False
    assert settings.version_check_enabled is False


def test_disabling_tracking_leaves_the_update_check_alone() -> None:
    """`-d` opts out of usage tracking only; `-o` is the full offline switch."""
    settings = Settings(usage_tracking=False)
    assert settings.telemetry_enabled is False
    assert settings.version_check_enabled is True


# ------------------------------------------------------------------ from_env


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_env_truthy(value: str) -> None:
    assert Settings.from_env({"TFTUI_OFFLINE": value}).offline is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "", "nonsense"])
def test_env_falsy(value: str) -> None:
    assert Settings.from_env({"TFTUI_OFFLINE": value}).offline is False


def test_env_values() -> None:
    settings = Settings.from_env(
        {
            "TFTUI_EXECUTABLE": "tofu",
            "TFTUI_VAR_FILE": "prod.tfvars",
            "TFTUI_WORKING_DIR": "/infra",
            "TFTUI_NO_INIT": "1",
            "TFTUI_LIGHT_MODE": "1",
            "TFTUI_DEBUG_LOG": "1",
            "TFTUI_DISABLE_USAGE_TRACKING": "1",
        }
    )
    assert settings.executable == "tofu"
    assert settings.var_file == "prod.tfvars"
    assert settings.working_dir == Path("/infra")
    assert settings.run_init is False
    assert settings.light_mode is True
    assert settings.debug_log is True
    assert settings.usage_tracking is False


# ---------------------------------------------------------------------- CLI


def test_cli_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TFTUI_EXECUTABLE", raising=False)
    settings, wants_version = parse_args([])
    assert settings.executable == "terraform"
    assert wants_version is False


@pytest.mark.parametrize(
    ("argv", "attribute", "expected"),
    [
        (["-e", "tofu"], "executable", "tofu"),
        (["--executable", "terragrunt"], "executable", "terragrunt"),
        (["-f", "a.tfvars"], "var_file", "a.tfvars"),
        (["--var-file", "b.tfvars"], "var_file", "b.tfvars"),
        (["-n"], "run_init", False),
        (["--no-init"], "run_init", False),
        (["-o"], "offline", True),
        (["--offline"], "offline", True),
        (["-d"], "usage_tracking", False),
        (["--disable-usage-tracking"], "usage_tracking", False),
        (["-l"], "light_mode", True),
        (["--light-mode"], "light_mode", True),
        (["-g"], "debug_log", True),
        (["--generate-debug-log"], "debug_log", True),
    ],
)
def test_every_legacy_flag_still_works(
    argv: list[str], attribute: str, expected: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Backward compatibility: every flag from previous releases is preserved."""
    for name in list(dict.fromkeys(["TFTUI_EXECUTABLE", "TFTUI_VAR_FILE"])):
        monkeypatch.delenv(name, raising=False)
    settings, _ = parse_args(argv)
    assert getattr(settings, attribute) == expected


def test_version_flag() -> None:
    _, wants_version = parse_args(["-v"])
    assert wants_version is True


def test_chdir_flag() -> None:
    settings, _ = parse_args(["-C", "/infra"])
    assert settings.working_dir == Path("/infra")
    assert settings.directory == Path("/infra")


def test_flags_beat_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TFTUI_EXECUTABLE", "tofu")
    settings, _ = parse_args(["-e", "terragrunt"])
    assert settings.executable == "terragrunt"


def test_environment_applies_when_no_flag_is_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TFTUI_EXECUTABLE", "tofu")
    settings, _ = parse_args([])
    assert settings.executable == "tofu"


def test_directory_defaults_to_cwd() -> None:
    assert Settings().directory == Path.cwd()
