"""A :class:`RichLog` that renders at the pane's real width, and re-wraps on resize."""

from __future__ import annotations

from typing import Any

from rich.console import RenderableType
from textual.events import Resize
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
            self.write(renderable, width=width)

    def reset_content(self) -> None:
        """Drop everything, on screen and remembered."""
        self._content.clear()
        self._rendered_width = 0
        self.clear()

    def _current_width(self) -> int:
        return self.scrollable_content_region.width

    def on_resize(self, event: Resize) -> None:
        del event
        if self._current_width() != self._rendered_width:
            self._replay()

    def _replay(self) -> None:
        width = self._current_width()
        if not width:
            return

        offset = self.scroll_offset.y
        follow, self.auto_scroll = self.auto_scroll, False
        self.clear()
        for renderable in self._content:
            self.write(renderable, width=width)
        self._rendered_width = width
        self.auto_scroll = follow

        if follow:
            self.scroll_end(animate=False)
        elif offset:
            self.scroll_to(y=offset, animate=False)
