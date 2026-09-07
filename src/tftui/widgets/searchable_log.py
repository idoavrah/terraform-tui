"""A log of styled lines that can be searched in place."""

from __future__ import annotations

from typing import Any

from rich.text import Text

from tftui.widgets.reflowing_log import ReflowingLog

#: Reverse video rather than a fixed colour pair, so a match stays visible
#: whatever colour the content already painted the line.
MATCH_STYLE = "reverse bold"


class SearchableLog(ReflowingLog):
    """Keeps its content as a list of styled lines and can search across them.

    Matches are highlighted where they are rather than filtered out. Both things
    this displays - a resource definition and a plan diff - are structured
    documents whose surrounding lines are the point, so hiding the non-matching
    ones would destroy what is being searched.

    The unhighlighted lines stay the source of truth, so a new search, a theme
    change or a resize all re-render from clean text.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._lines: list[Text] = []
        self._needle = ""
        #: Indices into ``_lines`` that match the current search.
        self._matches: list[int] = []
        self._match = -1

    @property
    def title(self) -> str:
        """What the pane calls itself; subclasses override. Used in search titles."""
        return ""

    # ---------------------------------------------------------------- content

    def set_lines(self, lines: list[Text]) -> None:
        """Replace everything, keeping any active search applied."""
        self._lines = list(lines)
        self._reindex()
        self.replace_content(list(self._displayed()))

    def add_line(self, line: Text) -> None:
        """Append one line, as streamed output arrives."""
        self._lines.append(line)
        self.append(self._display(line))
        if self._needle and self._needle in line.plain.lower():
            self._matches.append(len(self._lines) - 1)

    def clear_lines(self) -> None:
        self._lines = []
        self._needle = ""
        self._matches = []
        self._match = -1
        self.reset_content()

    @property
    def fulltext(self) -> Text:
        """Everything held, joined - for the full-screen view and for copying."""
        joined = Text("")
        for line in self._lines:
            joined.append_text(line)
            joined.append("\n")
        return joined

    # ----------------------------------------------------------------- search

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
        """Highlight every line containing ``needle`` and jump to the first."""
        self._needle = needle.strip().lower()
        self._reindex()
        self.replace_content(list(self._displayed()))
        self._scroll_to_match()
        return len(self._matches)

    def clear_search(self) -> None:
        if not self._needle:
            return
        self._needle = ""
        self._matches = []
        self._match = -1
        self.replace_content(list(self._lines))

    def step_match(self, delta: int) -> None:
        """Move to the next or previous match, wrapping around."""
        if not self._matches:
            return
        self._match = (self._match + delta) % len(self._matches)
        self._scroll_to_match()

    # ----------------------------------------------------------------- detail

    def _reindex(self) -> None:
        self._matches = [
            index
            for index, line in enumerate(self._lines)
            if self._needle and self._needle in line.plain.lower()
        ]
        self._match = 0 if self._matches else -1

    def _displayed(self) -> list[Text]:
        if not self._needle:
            return list(self._lines)
        return [self._display(line) for line in self._lines]

    def _display(self, line: Text) -> Text:
        """``line`` with every occurrence of the needle marked.

        The original is copied rather than mutated: it is what the next search
        and every re-render start from.
        """
        needle = self._needle
        if not needle:
            return line
        haystack = line.plain.lower()
        if needle not in haystack:
            return line

        marked = line.copy()
        start = haystack.find(needle)
        while start != -1:
            marked.stylize(MATCH_STYLE, start, start + len(needle))
            start = haystack.find(needle, start + len(needle))
        return marked

    def _scroll_to_match(self) -> None:
        if not self._matches or self._match < 0:
            return
        row = self.row_of(self._matches[self._match])
        if row is not None:
            # Leave a couple of lines of lead-in so the match has context.
            self.scroll_to(y=max(0, row - 2), animate=False)
