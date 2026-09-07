"""The release gate: it decides whether a push to main publishes.

A wrong answer here is expensive in both directions - a missed release, or a
version published twice - so the decision function is tested directly.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from packaging.version import Version

_PATH = Path(__file__).parents[2] / "scripts" / "should_release.py"
_SPEC = importlib.util.spec_from_file_location("should_release", _PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
should_release = importlib.util.module_from_spec(_SPEC)
sys.modules["should_release"] = should_release
_SPEC.loader.exec_module(should_release)

decide = should_release.decide


def _versions(*raw: str) -> set[Version]:
    return {Version(value) for value in raw}


def test_releases_when_nothing_is_published() -> None:
    release, _ = decide(Version("0.14.0"), set())
    assert release is True


def test_releases_a_newer_version() -> None:
    release, reason = decide(Version("0.14.0"), _versions("0.13.4", "0.13.3"))
    assert release is True
    assert "0.13.4" in reason


def test_refuses_a_version_already_on_pypi() -> None:
    """Re-pushing main, or reverting an unrelated commit, must not republish."""
    release, reason = decide(Version("0.13.4"), _versions("0.13.4", "0.13.3"))
    assert release is False
    assert "already on PyPI" in reason


def test_refuses_a_downgrade() -> None:
    """A botched bump, or a stale branch merged late, is caught before publishing."""
    release, reason = decide(Version("0.13.0"), _versions("0.13.4"))
    assert release is False
    assert "not newer" in reason


def test_refuses_a_version_equal_to_the_newest() -> None:
    release, _ = decide(Version("0.13.4"), _versions("0.13.4"))
    assert release is False


def test_refuses_when_pypi_is_unreachable() -> None:
    """Unknown is not the same as new; failing closed cannot double-publish."""
    release, reason = decide(Version("9.9.9"), None)
    assert release is False
    assert "unreachable" in reason


def test_a_deleted_or_yanked_version_is_not_reused() -> None:
    """PyPI lists yanked releases, and the number is spent either way."""
    release, _ = decide(Version("0.13.4"), _versions("0.13.4", "0.14.0"))
    assert release is False


@pytest.mark.parametrize(
    ("current", "published", "expected"),
    [
        ("1.0.0", ("0.14.0",), True),
        ("0.14.1", ("0.14.0",), True),
        ("0.14.0", ("0.14.0rc1",), True),
        ("0.14.0rc1", ("0.14.0",), False),
        ("0.9.0", ("0.10.0",), False),  # not a string comparison
    ],
)
def test_ordering_uses_real_version_semantics(
    current: str, published: tuple[str, ...], expected: bool
) -> None:
    release, _ = decide(Version(current), _versions(*published))
    assert release is expected


def test_emit_writes_github_outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / "gh-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    should_release.emit(True, Version("0.14.0"))
    written = output.read_text()
    assert "release=true" in written
    assert "version=0.14.0" in written


def test_emit_is_a_no_op_outside_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    should_release.emit(False, Version("0.14.0"))  # must not raise


def test_reads_the_real_packaged_version() -> None:
    """Guards against the script and pyproject drifting apart."""
    from tftui import __version__

    assert str(should_release.packaged_version()) == __version__
