#!/usr/bin/env python3
"""Refuse to publish to TestPyPI if a file there would silently be left stale.

TestPyPI is uploaded to with ``skip-existing: true``, because re-running a
release for the same commit must not fail on files that are already there.
That flag cannot tell "the identical file is already uploaded" from "a
*different* file claims that name" - and the second case is the dangerous one:
PyPI and TestPyPI permanently reserve a filename, so a version reworked after
its first TestPyPI upload can never replace it. The upload is skipped, the run
goes green, and TestPyPI keeps serving the superseded build.

So compare digests first. Identical files are fine and say so. A mismatch stops
the release with the only real remedy: bump the version.

TestPyPI being unreachable is *not* fatal. It is a smoke test, not the release
gate - unlike ``should_release.py``, which fails closed because a double
publish to PyPI cannot be undone.
"""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

TESTPYPI_URL = "https://test.pypi.org/pypi/tftui/json"
TIMEOUT = 30.0


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


#: What twine actually uploads. `uv build` also writes a .gitignore into the
#: output directory, and that is not a distribution.
DIST_SUFFIXES = (".whl", ".tar.gz")


def local_files(dist: Path) -> dict[str, str]:
    """Filename to sha256 for each distribution built into ``dist``."""
    return {
        path.name: digest(path)
        for path in sorted(dist.iterdir())
        if path.is_file() and path.name.endswith(DIST_SUFFIXES)
    }


def published_files() -> dict[str, str] | None:
    """Filename to sha256 for every file TestPyPI holds, or ``None`` if unreachable."""
    request = urllib.request.Request(TESTPYPI_URL, headers={"User-Agent": "tftui-release"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return {}
        print(f"::warning::TestPyPI returned HTTP {error.code}")
        return None
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        print(f"::warning::could not reach TestPyPI: {error}")
        return None

    found: dict[str, str] = {}
    for files in payload.get("releases", {}).values():
        for entry in files:
            name = entry.get("filename")
            sha = entry.get("digests", {}).get("sha256")
            if name and sha:
                found[name] = sha
    return found


def compare(local: dict[str, str], published: dict[str, str]) -> tuple[list[str], list[str]]:
    """Split the files we are about to upload into (already there, conflicting)."""
    identical: list[str] = []
    conflicting: list[str] = []
    for name, sha in sorted(local.items()):
        if name not in published:
            continue
        (identical if published[name] == sha else conflicting).append(name)
    return identical, conflicting


def main() -> int:
    dist = Path(sys.argv[1] if len(sys.argv) > 1 else "dist")
    try:
        local = local_files(dist)
    except OSError as error:
        print(f"::error::cannot read {dist}: {error}")
        return 1
    if not local:
        print(f"::error::nothing to publish in {dist}")
        return 1

    published = published_files()
    if published is None:
        print("::notice::skipping the TestPyPI digest check; it could not be reached")
        return 0

    identical, conflicting = compare(local, published)

    for name in identical:
        print(f"already on TestPyPI, byte-identical: {name}")
    for name in conflicting:
        print(f"::error::{name} is on TestPyPI with different contents")

    if conflicting:
        print(
            "::error::This version was already uploaded to TestPyPI from a different "
            "build. TestPyPI reserves a filename permanently, so the upload would be "
            "skipped and TestPyPI would keep serving the older build. Bump the version "
            "in pyproject.toml."
        )
        return 1

    print(f"TestPyPI check passed for {len(local)} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
