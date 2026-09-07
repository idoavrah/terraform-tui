"""The pane that streams and colours ``terraform plan`` and ``terraform apply``."""

from __future__ import annotations

from typing import Any

from rich.text import Text
from textual.message import Message

from tftui.terraform.plan import PlanStyler, is_banner
from tftui.widgets.reflowing_log import ReflowingLog

#: Deliberately a reverse video style rather than a fixed colour pair, so it
#: stays visible against whatever colour the diff already painted the line.
_MATCH_STYLE = "reverse bold"


class PlanView(ReflowingLog):
    """Streams plan and apply output, colourised line by line.

    All the colouring logic lives in :mod:`tftui.terraform.plan`; this widget
    only decides what to clear and when.
    """

    class PlanReady(Message):
        """Posted when a plan finishes, whether or not it produced changes."""

        def __init__(self, *, has_changes: bool, title: str) -> None:
            super().__init__()
            self.has_changes = has_changes
            self.title = title

    class ApplyFinished(Message):
        """Posted when an apply finishes, so the state can be reloaded."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            highlight=False,
            markup=False,
            wrap=True,
            auto_scroll=False,
            **kwargs,
        )
        self.styler = PlanStyler()
        self._lines: list[Text] = []
        self._seen_banner = False
        self._needle = ""
        #: Indices into ``_lines`` that match the current search.
        self._matches: list[int] = []
        self._match = -1

    # ------------------------------------------------------------- streaming

    def begin(self, *, follow: bool) -> None:
        """Prepare for a new run. ``follow`` scrolls to the tail, as apply wants."""
        self.styler.reset()
        self._lines = []
        self._seen_banner = False
        self.clear_search()
        self.auto_scroll = follow
        self.reset_content()

    def feed(self, line: str) -> None:
        """Append one line of output."""
        # Terraform prints refresh chatter before the plan proper; once the real
        # plan starts, drop what came before so the pane opens on the diff.
        if not self._seen_banner and is_banner(line):
            self._seen_banner = True
            self._lines = []
            self.reset_content()

        styled = self.styler.style(line)
        self._lines.append(styled)
        self.append(_with_highlight(styled, self._needle) if self._needle else styled)
        if self._needle and self._needle in styled.plain.lower():
            self._matches.append(len(self._lines) - 1)

    # ---------------------------------------------------------------- output

    @property
    def fulltext(self) -> Text:
        """Everything written so far, for the full-screen view."""
        if not self._lines:
            return Text("")
        joined = Text("")
        for line in self._lines:
            joined.append_text(line)
            joined.append("\n")
        return joined

    @property
    def summary(self) -> Text:
        """A short digest of the current plan, shown in the apply confirmation."""
        return self.styler.summary_text()

    @property
    def title(self) -> str:
        return self.styler.title()

    # ---------------------------------------------------------------- search

    @property
    def needle(self) -> str:
        return self._needle

    @property
    def match_count(self) -> int:
        return len(self._matches)

    @property
    def match_position(self) -> int:
        """1-based position within the matches, or 0 when there is no match."""
        return self._match + 1 if self._matches else 0

    def search(self, needle: str) -> int:
        """Highlight every line containing ``needle`` and jump to the first.

        Matching lines are highlighted in place rather than filtered out: a
        plan only makes sense with its surrounding diff, so hiding the
        non-matching lines would destroy the thing being searched.
        """
        self._needle = needle.strip().lower()
        self._matches = [
            index
            for index, line in enumerate(self._lines)
            if self._needle and self._needle in line.plain.lower()
        ]
        self._match = 0 if self._matches else -1

        self.replace_content(
            [_with_highlight(line, self._needle) if self._needle else line for line in self._lines]
        )
        self._scroll_to_match()
        return len(self._matches)

    def clear_search(self) -> None:
        had_search = bool(self._needle)
        self._needle = ""
        self._matches = []
        self._match = -1
        if had_search:
            self.replace_content(list(self._lines))

    def step_match(self, delta: int) -> None:
        """Move to the next or previous match, wrapping around."""
        if not self._matches:
            return
        self._match = (self._match + delta) % len(self._matches)
        self._scroll_to_match()

    def _scroll_to_match(self) -> None:
        if not self._matches or self._match < 0:
            return
        row = self.row_of(self._matches[self._match])
        if row is not None:
            self.scroll_to(y=max(0, row - 2), animate=False)


def _with_highlight(line: Text, needle: str) -> Text:
    """Return ``line`` with every occurrence of ``needle`` marked.

    The original is copied rather than mutated: it is the source of truth that
    a later search, or a resize, re-renders from.
    """
    if not needle:
        return line
    haystack = line.plain.lower()
    if needle not in haystack:
        return line

    marked = line.copy()
    start = haystack.find(needle)
    while start != -1:
        marked.stylize(_MATCH_STYLE, start, start + len(needle))
        start = haystack.find(needle, start + len(needle))
    return marked
