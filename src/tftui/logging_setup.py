"""Logging configuration.

By default tftui logs nothing: a TUI cannot share stdout with a log stream, and
silently creating files in someone's Terraform directory would be rude. Passing
``-g`` turns on a debug log written to ``tftui.log`` in the working directory.
"""

from __future__ import annotations

import logging
from pathlib import Path

LOGGER_NAME = "tftui"
LOG_FILENAME = "tftui.log"

_FORMAT = "%(asctime)s %(levelname)-7s [%(name)s:%(funcName)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_logger(name: str | None = None) -> logging.Logger:
    """Return the package logger, or a child of it."""
    return logging.getLogger(LOGGER_NAME if name is None else f"{LOGGER_NAME}.{name}")


def configure_logging(*, debug: bool, directory: Path | None = None) -> logging.Logger:
    """Configure the package logger and return it.

    When ``debug`` is false the logger is left with a null handler, so library
    code can log freely without ever producing output.
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.handlers.clear()
    logger.propagate = False

    if not debug:
        logger.addHandler(logging.NullHandler())
        logger.setLevel(logging.CRITICAL)
        return logger

    target = (directory or Path.cwd()) / LOG_FILENAME
    handler = logging.FileHandler(target, encoding="utf-8")
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    return logger
