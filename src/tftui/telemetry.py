"""Anonymous usage tracking, and the update check that runs alongside it.

Behaviour is unchanged from previous releases: tracking is **opt-out**, the
user is identified only by a two-word handle derived from a hash of their
machine's name, and ``-d`` / ``-o`` turn it off. What changed is the engineering
around it:

* Nothing here can block or crash the UI. Every call is dispatched to a daemon
  thread pool and every exception is swallowed and logged.
* ``posthog`` is imported lazily, on first use, and only when tracking is on -
  so a user who opts out never pays its import cost and never loads it at all.
* The update check uses :mod:`urllib` with a hard timeout instead of pulling in
  ``requests``.
* File paths in crash reports are redacted before they leave the machine.
"""

from __future__ import annotations

import hashlib
import json
import logging
import platform
import re
import socket
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from functools import lru_cache
from importlib.resources import files
from typing import Any

from tftui.version import __version__

logger = logging.getLogger(__name__)

_PYPI_URL = "https://pypi.org/pypi/tftui/json"
_POSTHOG_HOST = "https://app.posthog.com"
_POSTHOG_API_KEY = "phc_tjGzx7V6Y85JdNfOFWxQLXo5wtUs6MeVLvoVfybqz09"
_NETWORK_TIMEOUT = 5.0

#: Replaces every intermediate path component, so a redacted traceback keeps
#: its shape (and the failing file name) without leaking directory structure.
_PATH_COMPONENT = re.compile(r"(?<=[/\\])[^\s/\\]+(?=[/\\])")


def redact(text: str) -> str:
    """Strip directory names out of ``text`` before it is sent anywhere."""
    return _PATH_COMPONENT.sub("***", text)


@lru_cache(maxsize=1)
def _wordlists() -> tuple[list[str], list[str]]:
    data = json.loads(files("tftui.data").joinpath("handle_words.json").read_text(encoding="utf-8"))
    return data["adjectives"], data["nouns"]


@lru_cache(maxsize=1)
def machine_handle() -> str:
    """A stable, non-reversible two-word handle for this machine.

    Derived from the same fingerprint as previous releases, so a returning user
    keeps the same handle across the rewrite.
    """
    fingerprint = (
        f"{platform.system()}-{platform.node()}-{platform.release()}-{socket.gethostname()}"
    )
    return handle_for(fingerprint)


def handle_for(fingerprint: str) -> str:
    """Derive a two-word handle from an arbitrary fingerprint string."""
    adjectives, nouns = _wordlists()
    digest = int(hashlib.sha256(fingerprint.encode()).hexdigest(), 16)
    return f"{adjectives[digest % len(adjectives)]} {nouns[digest % len(nouns)]}"


def latest_version() -> str | None:
    """Fetch the newest published version from PyPI, or ``None`` on any failure."""
    try:
        request = urllib.request.Request(
            _PYPI_URL,
            headers={"User-Agent": f"tftui/{__version__}"},
        )
        with urllib.request.urlopen(request, timeout=_NETWORK_TIMEOUT) as response:  # noqa: S310
            payload = json.load(response)
        version = payload["info"]["version"]
    except (urllib.error.URLError, OSError, ValueError, KeyError, TimeoutError) as error:
        logger.debug("update check failed: %s", error)
        return None
    return str(version) if isinstance(version, str) else None


class Telemetry:
    """Fire-and-forget usage tracking.

    Every public method returns immediately. Work happens on a single daemon
    worker thread, so events keep their order but never delay a keystroke.
    """

    def __init__(self, *, enabled: bool, check_updates: bool) -> None:
        self.enabled = enabled
        self.check_updates = check_updates
        self.latest_version: str | None = None
        self._client: Any = None
        self._pool: ThreadPoolExecutor | None = None

    @property
    def update_available(self) -> bool:
        """True only when PyPI is genuinely *ahead* of what is installed.

        Comparing for inequality would announce an "update" to anyone running a
        development or pre-release build that is newer than the published one.
        """
        if self.latest_version is None:
            return False
        return _is_newer(self.latest_version, __version__)

    @property
    def update_suffix(self) -> str:
        """``' (new version available)'`` when an update exists, else empty."""
        return " (new version available)" if self.update_available else ""

    # ------------------------------------------------------------- lifecycle

    def _submit(self, fn: Any, *args: Any) -> None:
        if self._pool is None:
            self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tftui-telemetry")
        with suppress(RuntimeError):  # pool already shut down during exit
            self._pool.submit(_guarded, fn, *args)

    def start_update_check(self) -> None:
        """Kick off the PyPI version check in the background."""
        if not self.check_updates:
            return
        self._submit(self._do_update_check)

    def _do_update_check(self) -> None:
        self.latest_version = latest_version()

    def refresh_update_check(self) -> None:
        """Run the update check synchronously. Used by ``--version``."""
        if self.check_updates:
            self._do_update_check()

    def capture(self, event: str, **properties: Any) -> None:
        """Record a usage event. Never raises, never blocks."""
        if not self.enabled:
            return
        self._submit(self._do_capture, event, properties)

    def capture_error(self, event: str, traceback_text: str) -> None:
        """Record a crash, with file paths redacted first."""
        if not self.enabled:
            return
        self.capture(event, error_message=redact(traceback_text).splitlines())

    def _do_capture(self, event: str, properties: dict[str, Any]) -> None:
        client = self._ensure_client()
        if client is None:
            return
        client.capture(
            distinct_id=machine_handle(),
            event=event,
            properties={"tftui_version": __version__, **properties},
        )

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from posthog import Posthog
        except ImportError:  # pragma: no cover - posthog is an optional extra
            logger.debug("posthog is not installed; usage tracking disabled")
            self.enabled = False
            return None
        self._client = Posthog(
            project_api_key=_POSTHOG_API_KEY,
            host=_POSTHOG_HOST,
            disable_geoip=False,
        )
        return self._client

    def shutdown(self, timeout: float = 2.0) -> None:
        """Flush pending events, giving up after ``timeout`` seconds."""
        pool, self._pool = self._pool, None
        if pool is not None:
            pool.shutdown(wait=True, cancel_futures=False)
        client, self._client = self._client, None
        if client is not None:
            _guarded(client.flush)
        _ = timeout  # posthog's own flush has an internal deadline

    def platform_properties(self) -> dict[str, str]:
        return {"platform": platform.platform()}


def _release_parts(version: str) -> tuple[int, ...]:
    """The leading numeric release segment of a version, e.g. '1.2.3rc1' -> (1, 2, 3)."""
    parts: list[int] = []
    for chunk in version.split("."):
        digits = ""
        for char in chunk:
            if not char.isdigit():
                break
            digits += char
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def _is_newer(candidate: str, current: str) -> bool:
    """Whether ``candidate`` is a later release than ``current``."""
    left, right = _release_parts(candidate), _release_parts(current)
    if not left or not right:
        # Unparseable on either side: fall back to "different means newer".
        return candidate != current
    return left > right


def _guarded(fn: Any, *args: Any) -> None:
    """Run ``fn``, logging and discarding anything it raises.

    Usage tracking must never be able to take the application down, and it must
    never surface a network error to someone who is just trying to read state.
    """
    try:
        fn(*args)
    except Exception as error:
        logger.debug("telemetry call failed: %s", error)


class NullTelemetry(Telemetry):
    """A telemetry object that does nothing. Used in tests and offline mode."""

    def __init__(self) -> None:
        super().__init__(enabled=False, check_updates=False)
