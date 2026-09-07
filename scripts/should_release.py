#!/usr/bin/env python3
"""Decide whether the version in pyproject.toml should be released.

Run on every push to main. The answer is yes only when the packaged version is
**both** absent from PyPI and newer than everything already published, so that:

* re-pushing, merging, or reverting an unrelated commit never republishes;
* a version that was yanked or deleted from PyPI is not silently re-uploaded;
* a downgrade — a botched bump, or a long-lived branch merged late — is caught
  here rather than by PyPI rejecting the upload half way through a release.

Writes ``release`` and ``version`` to ``$GITHUB_OUTPUT`` and prints its
reasoning. Exits non-zero only on an error it cannot interpret; "do not
release" is a normal, successful answer.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from packaging.version import InvalidVersion, Version

if sys.version_info >= (3, 11):
    import tomllib
else:  # Python 3.10 is supported by the project, and predates tomllib.
    import tomli as tomllib

PYPI_URL = "https://pypi.org/pypi/tftui/json"
TIMEOUT = 30.0

ROOT = Path(__file__).resolve().parents[1]


def packaged_version() -> Version:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return Version(data["project"]["version"])


def published_versions() -> set[Version] | None:
    """Every version PyPI knows about, or ``None`` if PyPI could not be reached.

    Yanked releases are included: the version number is spent either way, and
    re-using it would confuse anyone who already installed it.
    """
    request = urllib.request.Request(PYPI_URL, headers={"User-Agent": "tftui-release"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return set()
        print(f"::warning::PyPI returned HTTP {error.code}")
        return None
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        print(f"::warning::could not reach PyPI: {error}")
        return None

    found: set[Version] = set()
    for raw in payload.get("releases", {}):
        try:
            found.add(Version(raw))
        except InvalidVersion:
            continue
    return found


def decide(current: Version, published: set[Version] | None) -> tuple[bool, str]:
    """Return whether to release, and why."""
    if published is None:
        return False, "PyPI is unreachable, so it is not safe to say this is new"
    if not published:
        return True, "nothing is published yet"
    if current in published:
        return False, f"{current} is already on PyPI"

    newest = max(published)
    if current <= newest:
        return False, f"{current} is not newer than the published {newest}"
    return True, f"{current} is new and newer than {newest}"


def emit(release: bool, version: Version) -> None:
    output = os.environ.get("GITHUB_OUTPUT")
    if not output:
        return
    with Path(output).open("a", encoding="utf-8") as handle:
        handle.write(f"release={'true' if release else 'false'}\n")
        handle.write(f"version={version}\n")


def main() -> int:
    try:
        current = packaged_version()
    except (OSError, KeyError, InvalidVersion) as error:
        print(f"::error::cannot read the version from pyproject.toml: {error}")
        return 1

    release, reason = decide(current, published_versions())

    print(f"packaged version: {current}")
    print(f"release: {release} ({reason})")
    if release:
        print(f"::notice::releasing {current}: {reason}")
    else:
        print(f"::notice::not releasing: {reason}")

    emit(release, current)
    return 0


if __name__ == "__main__":
    sys.exit(main())
