"""The pane that renders a single resource's state."""

from __future__ import annotations

from typing import Any

from rich.syntax import Syntax
from rich.text import Text

from tftui.terraform.state import Resource
from tftui.widgets.searchable_log import SearchableLog


def syntax_theme(*, dark: bool) -> str:
    """The Rich syntax theme matching the application's light or dark mode.

    The ANSI themes are used deliberately: they emit the terminal's own palette
    rather than fixed RGB values, so highlighted code sits inside the user's
    colour scheme instead of fighting it.
    """
    return "ansi_dark" if dark else "ansi_light"


def highlight_lines(code: str, *, dark: bool) -> list[Text]:
    """Highlight ``code`` as HCL and return it one styled line at a time.

    Rendering line by line rather than as a single ``Syntax`` block is what lets
    the pane be searched: matches are marked on individual lines, and each line
    can be scrolled to. It also keeps the output free of any background of its
    own, so the pane's colour shows through.
    """
    highlighted = Syntax(code, "hcl", theme=syntax_theme(dark=dark)).highlight(code)
    lines = highlighted.split("\n")
    # `split` keeps a trailing empty line for a trailing newline; drop it so the
    # pane does not end in a blank row.
    rendered = list(lines)
    if rendered and not rendered[-1].plain:
        rendered.pop()
    return rendered


class ResourceView(SearchableLog):
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
        self.set_lines(highlight_lines(self._body, dark=self._dark))

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
        self.clear_lines()
