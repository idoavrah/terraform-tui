"""Usage tracking: it must stay anonymous, quiet, and unable to break the app."""

from __future__ import annotations

import pytest

from tftui.telemetry import NullTelemetry, Telemetry, handle_for, machine_handle, redact

# --------------------------------------------------------------- handle words


@pytest.mark.parametrize(
    ("fingerprint", "expected"),
    [
        ("Linux-host-1-6.1", "dizzy movie"),
        ("Darwin-mac-23.0-mac", "wooden category"),
        ("", "determined kill"),
        ("a", "angelic tennis"),
    ],
)
def test_handles_match_previous_releases(fingerprint: str, expected: str) -> None:
    """Returning users must keep the same handle across the rewrite.

    These values were computed with the pre-rewrite implementation; the word
    lists moved from a Python module to a data file but did not change.
    """
    assert handle_for(fingerprint) == expected


def test_handle_is_stable_and_two_words() -> None:
    assert machine_handle() == machine_handle()
    assert len(machine_handle().split()) == 2


def test_handle_does_not_leak_the_fingerprint() -> None:
    secret = "super-secret-hostname"
    assert secret not in handle_for(f"Linux-{secret}-6.1-{secret}")


# -------------------------------------------------------------------- redact


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("/home/alice/infra/main.tf", "/***/***/***/main.tf"),
        (r"C:\Users\bob\infra\main.tf", r"C:\***\***\***\main.tf"),
        ("no paths here", "no paths here"),
    ],
)
def test_redact_removes_directory_names(text: str, expected: str) -> None:
    assert redact(text) == expected


def test_redact_keeps_the_failing_filename() -> None:
    """The file name is the useful part of a crash report; the path is not."""
    line = '  File "/home/alice/projects/tftui/app.py", line 12, in action_plan'
    redacted = redact(line)
    assert "app.py" in redacted
    assert "alice" not in redacted
    assert "projects" not in redacted


# ------------------------------------------------------------------- capture


def test_disabled_telemetry_never_builds_a_client() -> None:
    telemetry = Telemetry(enabled=False, check_updates=False)
    telemetry.capture("something")
    telemetry.shutdown()
    assert telemetry._client is None


def test_null_telemetry_is_inert() -> None:
    telemetry = NullTelemetry()
    assert telemetry.enabled is False
    assert telemetry.check_updates is False
    telemetry.capture("x")
    telemetry.capture_error("y", "trace")
    telemetry.start_update_check()
    telemetry.shutdown()


def test_capture_never_raises_when_the_backend_fails() -> None:
    """A broken analytics backend must not take a Terraform browser down."""
    telemetry = Telemetry(enabled=True, check_updates=False)

    class Exploding:
        def capture(self, **_: object) -> None:
            raise RuntimeError("posthog is down")

        def flush(self) -> None:
            raise RuntimeError("still down")

    telemetry._client = Exploding()
    telemetry.capture("started application")
    telemetry.shutdown()  # joins the worker; must not propagate


def test_capture_error_redacts_before_sending() -> None:
    telemetry = Telemetry(enabled=True, check_updates=False)
    sent: list[dict[str, object]] = []

    class Recorder:
        def capture(self, **kwargs: object) -> None:
            sent.append(kwargs)

        def flush(self) -> None:
            pass

    telemetry._client = Recorder()
    telemetry.capture_error("exited unsuccessfully", '  File "/home/alice/x/app.py", line 1')
    telemetry.shutdown()

    assert sent
    payload = str(sent[0]["properties"])
    assert "alice" not in payload
    assert "app.py" in payload


def test_update_suffix() -> None:
    telemetry = Telemetry(enabled=False, check_updates=False)
    assert telemetry.update_suffix == ""

    telemetry.latest_version = "99.0.0"
    assert telemetry.update_available is True
    assert telemetry.update_suffix == " (new version available)"


def test_update_check_is_skipped_when_disabled() -> None:
    telemetry = Telemetry(enabled=False, check_updates=False)
    telemetry.refresh_update_check()
    assert telemetry.latest_version is None
    assert telemetry.update_available is False


@pytest.mark.parametrize(
    ("published", "installed", "expected"),
    [
        ("1.0.1", "1.0.0", True),
        ("1.1.0", "1.0.9", True),
        ("2.0.0", "1.99.99", True),
        ("1.0.0", "1.0.0", False),
        # Running ahead of PyPI must not be reported as an available update.
        ("0.13.4", "1.0.0", False),
        ("1.0.0", "1.0.1", False),
        ("1.0.0", "1.0.0+dev", False),
    ],
)
def test_update_is_only_offered_when_pypi_is_ahead(
    published: str, installed: str, expected: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("tftui.telemetry.__version__", installed)
    telemetry = Telemetry(enabled=False, check_updates=False)
    telemetry.latest_version = published
    assert telemetry.update_available is expected
