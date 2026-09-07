"""The pane that renders a single resource's state."""

from __future__ import annotations

from typing import Any

from rich.syntax import Syntax

from tftui.terraform.state import Resource
from tftui.widgets.reflowing_log import ReflowingLog


def syntax_theme(*, dark: bool) -> str:
    """The Rich syntax theme matching the application's light or dark mode.

    The ANSI themes are used deliberately: they emit the terminal's own palette
    rather than fixed RGB values, so highlighted code sits inside the user's
    colour scheme instead of fighting it.
    """
    return "ansi_dark" if dark else "ansi_light"


def highlight(code: str, *, dark: bool) -> Syntax:
    """Render ``code`` as HCL, with no background of its own.

    ``background_color`` is deliberately not set. Passing it - even as
    "default" - stamps an explicit background onto every segment, which then
    overrides the pane's own background: the highlighted cells end up a
    different shade from the whitespace around them.
    """
    return Syntax(
        code,
        "hcl",
        theme=syntax_theme(dark=dark),
        word_wrap=True,
    )


class ResourceView(ReflowingLog):
    """Shows one resource block, with sensitive values hidden until asked for.

    HCL syntax highlighting replaces the previous generic value highlighting,
    which is what makes a 200-line resource readable at a glance.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            highlight=False,
            markup=False,
            wrap=True,
            auto_scroll=False,
            **kwargs,
        )
        self.resource: Resource | None = None
        self.revealed = False
        self._body = ""

    def show(
        self,
        resource: Resource,
        *,
        revealed: bool = False,
        secrets: dict[str, str] | None = None,
    ) -> None:
        """Render ``resource``, optionally substituting its sensitive values."""
        secrets = secrets or {}
        self.resource = resource
        self.revealed = revealed and bool(secrets)
        self._body = resource.reveal(secrets) if self.revealed else resource.body
        self._draw()
        self.scroll_home(animate=False)

    def rerender(self) -> None:
        """Redraw at the current theme. Called when light/dark mode is toggled."""
        if self.resource is not None:
            self._draw()

    def _draw(self) -> None:
        self.reset_content()
        self.append(highlight(self._body, dark=self._dark))

    @property
    def _dark(self) -> bool:
        return bool(self.app.current_theme.dark)

    @property
    def body(self) -> str:
        """Exactly what is on screen - so copy and full-screen agree with the view."""
        return self._body

    @property
    def title(self) -> str:
        return self.resource.full_address if self.resource is not None else ""

    def reset(self) -> None:
        self.resource = None
        self.revealed = False
        self._body = ""
        self.reset_content()
