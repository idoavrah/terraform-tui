"""The TestPyPI guard, which stops a release that would leave a stale artifact.

A filename on PyPI or TestPyPI is spent for good: it cannot be replaced, even
after deleting the release. Uploading with `skip-existing` therefore hides the
one case that matters - a rebuilt file claiming a name that is already taken -
so the digests are compared before the upload runs.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

_PATH = Path(__file__).parents[2] / "scripts" / "check_testpypi.py"
_SPEC = importlib.util.spec_from_file_location("check_testpypi", _PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
check_testpypi = importlib.util.module_from_spec(_SPEC)
sys.modules["check_testpypi"] = check_testpypi
_SPEC.loader.exec_module(check_testpypi)

compare = check_testpypi.compare

WHEEL = "tftui-0.14.0-py3-none-any.whl"
SDIST = "tftui-0.14.0.tar.gz"


def test_a_first_upload_has_nothing_to_compare() -> None:
    identical, conflicting = compare({WHEEL: "aaa"}, {})
    assert identical == []
    assert conflicting == []


def test_reuploading_the_identical_file_is_fine() -> None:
    """Re-running a release for the same commit must not be treated as drift."""
    identical, conflicting = compare({WHEEL: "aaa"}, {WHEEL: "aaa"})
    assert identical == [WHEEL]
    assert conflicting == []


def test_a_rebuilt_file_under_the_same_name_conflicts() -> None:
    """The case `skip-existing` hides: TestPyPI would keep serving the old build."""
    identical, conflicting = compare({WHEEL: "bbb"}, {WHEEL: "aaa"})
    assert identical == []
    assert conflicting == [WHEEL]


def test_other_versions_on_testpypi_are_ignored() -> None:
    identical, conflicting = compare({WHEEL: "aaa"}, {"tftui-0.13.4.tar.gz": "zzz"})
    assert identical == []
    assert conflicting == []


def test_one_conflicting_file_among_several_is_reported() -> None:
    identical, conflicting = compare(
        {WHEEL: "aaa", SDIST: "ccc"},
        {WHEEL: "aaa", SDIST: "bbb"},
    )
    assert identical == [WHEEL]
    assert conflicting == [SDIST]


def test_local_files_hashes_the_build(tmp_path: Path) -> None:
    (tmp_path / WHEEL).write_bytes(b"wheel")
    (tmp_path / "sub").mkdir()  # directories are not distribution files

    assert check_testpypi.local_files(tmp_path) == {WHEEL: hashlib.sha256(b"wheel").hexdigest()}


def test_main_passes_when_the_build_is_new(tmp_path: Path, monkeypatch, capsys) -> None:
    (tmp_path / WHEEL).write_bytes(b"wheel")
    monkeypatch.setattr(check_testpypi, "published_files", dict)
    monkeypatch.setattr(sys, "argv", ["check_testpypi.py", str(tmp_path)])

    assert check_testpypi.main() == 0
    assert "check passed" in capsys.readouterr().out


def test_main_fails_on_a_conflict(tmp_path: Path, monkeypatch, capsys) -> None:
    (tmp_path / WHEEL).write_bytes(b"rebuilt")
    monkeypatch.setattr(check_testpypi, "published_files", lambda: {WHEEL: "aaa"})
    monkeypatch.setattr(sys, "argv", ["check_testpypi.py", str(tmp_path)])

    assert check_testpypi.main() == 1
    assert "Bump the version" in capsys.readouterr().out


def test_main_does_not_block_a_release_when_testpypi_is_down(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """TestPyPI is a smoke test; PyPI is the gate. Only the latter fails closed."""
    (tmp_path / WHEEL).write_bytes(b"wheel")
    monkeypatch.setattr(check_testpypi, "published_files", lambda: None)
    monkeypatch.setattr(sys, "argv", ["check_testpypi.py", str(tmp_path)])

    assert check_testpypi.main() == 0
    assert "could not be reached" in capsys.readouterr().out


def test_main_fails_on_an_empty_dist(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["check_testpypi.py", str(tmp_path)])

    assert check_testpypi.main() == 1
    assert "nothing to publish" in capsys.readouterr().out
