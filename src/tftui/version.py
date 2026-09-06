"""Package version, resolved without assuming tftui is installed."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _metadata_version

#: Used when running straight from a source checkout that was never installed.
_FALLBACK = "0.0.0+dev"


def _resolve() -> str:
    try:
        return _metadata_version("tftui")
    except PackageNotFoundError:  # pragma: no cover - only hit in odd checkouts
        return _FALLBACK


__version__ = _resolve()

__all__ = ["__version__"]
