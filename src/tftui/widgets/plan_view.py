"""The pane that streams and colours ``terraform plan`` and ``terraform apply``."""

from __future__ import annotations

from typing import Any

from rich.text import Text
from textual.message import Message

from tftui.terraform.plan import PlanStyler, is_banner
from tftui.widgets.searchable_log import SearchableLog


class PlanView(SearchableLog):
    """Streams plan and apply output, colourised line by line.

    All the colouring logic lives in :mod:`tftui.terraform.plan`; this widget
    only decides what to clear and when. Searching comes from
    :class:`SearchableLog`.
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
        self._seen_banner = False

    # ------------------------------------------------------------- streaming

    def begin(self, *, follow: bool) -> None:
        """Prepare for a new run. ``follow`` scrolls to the tail, as apply wants."""
        self.styler.reset()
        self._seen_banner = False
        self.auto_scroll = follow
        self.clear_lines()

    def feed(self, line: str) -> None:
        """Append one line of output."""
        # Terraform prints refresh chatter before the plan proper; once the real
        # plan starts, drop what came before so the pane opens on the diff.
        if not self._seen_banner and is_banner(line):
            self._seen_banner = True
            self.clear_lines()

        self.add_line(self.styler.style(line))

    # ---------------------------------------------------------------- output

    @property
    def summary(self) -> Text:
        """A short digest of the current plan, shown in the apply confirmation."""
        return self.styler.summary_text()

    @property
    def title(self) -> str:
        return self.styler.title()
