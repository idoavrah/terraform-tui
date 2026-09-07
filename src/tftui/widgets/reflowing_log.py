"""A :class:`RichLog` that renders at the pane's real width, and re-wraps on resize."""

from __future__ import annotations

from typing import Any

from rich.console import RenderableType
from textual.events import Resize, Show
from textual.widgets import RichLog


class ReflowingLog(RichLog):
    """A log that keeps its source renderables so it can re-render them.

    ``RichLog`` is not quite right for streamed output on its own:

    * it wraps each line at whatever width was in effect when the line was
      written, and never re-wraps, so resizing the terminal leaves stale
      wrapping behind;
    * left to compute its own width it measures against the *application*
      console rather than the pane it lives in, so output written before the
      pane has been laid out wraps at 80 columns however wide the terminal is.
      Terraform's long resource addresses make that immediately visible.

    This subclass remembers what it was given, always renders at the pane's
    actual content width, and replays everything when that width changes.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._content: list[RenderableType] = []
        self._rendered_width = 0
        #: First rendered row of each item in ``_content``. Wrapping means one
        #: item can occupy several rows, so this is what lets a caller scroll to
        #: a particular item rather than guessing.
        self._rows: list[int] = []

    def append(self, renderable: RenderableType) -> None:
        """Write ``renderable`` and remember it for future re-wrapping."""
        self._content.append(renderable)

        width = self._current_width()
        if not width:
            # Not laid out yet - the resize that gives this pane a size will
            # replay everything buffered so far.
            return
        if width != self._rendered_width:
            self._replay()
        else:
            self._rows.append(len(self.lines))
            self.write(renderable, width=width)

    def replace_content(self, renderables: list[RenderableType]) -> None:
        """Swap the remembered content wholesale and redraw."""
        self._content = list(renderables)
        self._rendered_width = 0
        self._replay()

    def row_of(self, index: int) -> int | None:
        """The first rendered row of content item ``index``, if it is known."""
        if 0 <= index < len(self._rows):
            return self._rows[index]
        return None

    def reset_content(self) -> None:
        """Drop everything, on screen and remembered."""
        self._content.clear()
        self._rows.clear()
        self._rendered_width = 0
        self.clear()

    def _current_width(self) -> int:
        return self.scrollable_content_region.width

    def on_resize(self, event: Resize) -> None:
        del event
        self._render_if_stale()

    def on_show(self, event: Show) -> None:
        """Render anything written while this pane was hidden.

        Content written to a hidden pane cannot be laid out, so it is buffered
        and drawn once a width is known. Waiting only for a resize makes that
        depend on event ordering; becoming visible is the other moment a width
        first becomes available, and it is the one that matters when a pane is
        filled in before the switcher brings it forward.
        """
        del event
        self._render_if_stale()

    def _render_if_stale(self) -> None:
        if self._current_width() != self._rendered_width:
            self._replay()

    def _replay(self) -> None:
        width = self._current_width()
        if not width:
            return

        offset = self.scroll_offset.y
        follow, self.auto_scroll = self.auto_scroll, False
        self.clear()
        self._rows = []
        for renderable in self._content:
            self._rows.append(len(self.lines))
            self.write(renderable, width=width)
        self._rendered_width = width
        self.auto_scroll = follow

        if follow:
            self.scroll_end(animate=False)
        elif offset:
            self.scroll_to(y=offset, animate=False)
