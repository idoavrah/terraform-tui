"""The banner across the top of the application."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widgets import Static

LOGO = r""" ______   ______   ______   __  __    __
/\__  _\ /\  ___\ /\__  _\ /\ \/\ \  /\ \
\/_/\ \/ \ \  __\ \/_/\ \/ \ \ \_\ \ \ \ \
   \ \_\  \ \_\      \ \_\  \ \_____\ \ \_\
    \/_/   \/_/       \/_/   \/_____/  \/_/
"""

_LABELS = "TFTUI version:\n\nWorking folder:\n\nWorkspace:\n"

#: Below this width the ASCII logo is dropped so the facts stay readable.
_LOGO_MIN_WIDTH = 100


class AppHeader(Horizontal):
    """Shows the version, working directory and active workspace.

    Each field is a reactive, so the workspace can be updated in place after a
    switch instead of rebuilding the widget.
    """

    BORDER_TITLE = "TFTUI - the Terraform terminal user interface"

    version = reactive("", init=False)
    directory = reactive("", init=False)
    workspace = reactive("", init=False)

    def __init__(self, *, version: str, directory: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._info = Static(classes="header-box header-info")
        self._logo = Static(LOGO, classes="header-box header-logo")
        self.set_reactive(AppHeader.version, version)
        self.set_reactive(AppHeader.directory, directory)
        self.set_reactive(AppHeader.workspace, "…")

    def compose(self) -> ComposeResult:
        yield Static(_LABELS, classes="header-box header-labels")
        yield self._info
        yield self._logo

    def on_mount(self) -> None:
        self._render_info()

    def watch_version(self) -> None:
        self._render_info()

    def watch_directory(self) -> None:
        self._render_info()

    def watch_workspace(self) -> None:
        self._render_info()

    def _render_info(self) -> None:
        self._info.update(f"{self.version}\n\n{self.directory}\n\n{self.workspace}\n")

    def on_resize(self) -> None:
        self._logo.display = self.size.width >= _LOGO_MIN_WIDTH
