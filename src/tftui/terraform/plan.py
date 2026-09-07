"""Colourising and summarising ``terraform plan`` output.

Kept free of Textual and of any I/O so that the colouring rules can be unit
tested line by line, and so the plan view widget is reduced to plumbing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from rich.text import Text

#: Terraform's own exit codes under ``-detailed-exitcode``.
EXIT_NO_CHANGES = 0
EXIT_ERROR = 1
EXIT_CHANGES_PRESENT = 2

_PLAN_SUMMARY = re.compile(r"^Plan: \d+ to add, \d+ to change, \d+ to destroy\.$")
_NO_CHANGES = "No changes."
_ACTIONS_BANNER = "Terraform will perform the following actions:"
_RESOURCE_HEADER = re.compile(r"^\s{2}# (?P<address>.+?) (?P<verb>will be .+|must be .+)$")


class Change(str, Enum):
    """The kind of change Terraform intends to make to a resource."""

    CREATE = "create"
    UPDATE = "update"
    DESTROY = "destroy"
    REPLACE = "replace"
    READ = "read"
    UNKNOWN = "unknown"

    @property
    def style(self) -> str:
        return _CHANGE_STYLES[self]


_CHANGE_STYLES = {
    Change.CREATE: "green3",
    Change.UPDATE: "yellow3",
    Change.DESTROY: "red",
    Change.REPLACE: "red",
    Change.READ: "cyan",
    Change.UNKNOWN: "",
}

_VERB_TO_CHANGE = (
    ("will be created", Change.CREATE),
    ("will be destroyed", Change.DESTROY),
    ("must be replaced", Change.REPLACE),
    ("will be replaced", Change.REPLACE),
    ("will be updated in-place", Change.UPDATE),
    ("will be read during apply", Change.READ),
)


def classify(verb: str) -> Change:
    """Map a Terraform resource-header verb onto a :class:`Change`."""
    for needle, change in _VERB_TO_CHANGE:
        if verb.startswith(needle):
            return change
    return Change.UNKNOWN


@dataclass(slots=True)
class PlanStyler:
    """Stateful, line-at-a-time colouriser for plan output.

    Terraform indents a resource's diff under a ``# address will be ...``
    header, so the styler remembers the current block's colour and applies it to
    the body until a blank line closes the block.
    """

    block: Change = Change.UNKNOWN
    #: Resource headers seen so far, in order, as ``(address, change)``.
    headers: list[tuple[str, Change]] = field(default_factory=list)
    #: The ``Plan: N to add, ...`` line, once seen.
    summary: str = ""
    #: True once Terraform reports there is nothing to do.
    no_changes: bool = False

    def reset(self) -> None:
        self.block = Change.UNKNOWN
        self.headers.clear()
        self.summary = ""
        self.no_changes = False

    def style(self, line: str) -> Text:
        """Return ``line`` as styled rich text, updating the styler's state."""
        stripped = line.rstrip()

        if stripped == "":
            self.block = Change.UNKNOWN
            return Text("")

        if stripped.startswith(_NO_CHANGES):
            self.no_changes = True
            return Text(stripped, style="bold")

        if _PLAN_SUMMARY.match(stripped):
            self.summary = stripped
            return Text(stripped, style="bold")

        header = _RESOURCE_HEADER.match(stripped)
        if header is not None:
            self.block = classify(header["verb"])
            self.headers.append((header["address"], self.block))
            return Text(stripped, style=f"bold {self.block.style}".strip())

        return self._style_body(stripped)

    def _style_body(self, line: str) -> Text:
        body = line.lstrip()

        # An in-place change renders as `~ attr = "old" -> "new"`; colour the
        # old value red and the new value green, leaving the key neutral.
        if body.startswith("~") and "->" in line:
            split = _split_change(line)
            if split is not None:
                key, old, new = split
                return Text.assemble(
                    (key, self.block.style),
                    (old, Change.DESTROY.style),
                    (new, Change.CREATE.style),
                )

        # A replace renders as `-/+ resource ...`; check it before the bare
        # `-` and `+` cases, which would otherwise claim it.
        if body.startswith(("-/+", "+/-")):
            return Text(line, style=Change.REPLACE.style)
        if body.startswith("+"):
            return Text(line, style=Change.CREATE.style)
        if body.startswith("-"):
            return Text(line, style=Change.DESTROY.style)

        return Text(line, style=self.block.style)

    def summary_text(self) -> Text:
        """A compact, styled digest of the plan: the summary line then each header."""
        if self.no_changes:
            return Text("No changes. Your infrastructure matches the configuration.", "bold")

        parts: list[Text] = []
        if self.summary:
            parts.append(Text(self.summary, "bold"))
            parts.append(Text("\n\n"))
        for address, change in self.headers:
            parts.append(Text(f"  {_SIGILS[change]} {address}", f"bold {change.style}".strip()))
            parts.append(Text("\n"))
        return Text.assemble(*parts) if parts else Text("")

    def title(self) -> str:
        """One-line title for the plan pane."""
        if self.no_changes:
            return "No changes"
        return self.summary or "Plan"


_SIGILS = {
    Change.CREATE: "+",
    Change.UPDATE: "~",
    Change.DESTROY: "-",
    Change.REPLACE: "±",
    Change.READ: "<",
    Change.UNKNOWN: "•",
}


def _split_change(line: str) -> tuple[str, str, str] | None:
    """Split ``~ key = old -> new`` into its three coloured spans."""
    equals = line.find("=")
    arrow = line.find("->")
    if equals == -1 or arrow == -1 or arrow < equals:
        return None
    return line[: equals + 1], line[equals + 1 : arrow], line[arrow:]


def is_banner(line: str) -> bool:
    """True for the line that marks the start of the real plan body.

    Everything Terraform prints before it (refresh chatter, provider notices) is
    noise that the UI clears away once the plan proper begins.
    """
    return line.rstrip() == _ACTIONS_BANNER or line.startswith(_NO_CHANGES)
