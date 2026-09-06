"""The Terraform state model and the parser that builds it.

``terraform show`` output is parsed rather than ``terraform show -json`` because
the human-readable rendering is exactly what users want to look at. The JSON
form is fetched separately, and only to recover values that the text form
redacts as ``(sensitive value)``.

Parsing is anchored on column 0: a block header is ``# <address>:`` and a block
ends with a lone ``}``. Heredoc bodies are always indented by Terraform, so this
stays correct even for values that themselves contain ``#`` or ``}``.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

from tftui.terraform.address import ResourceAddress, parse_address

logger = logging.getLogger(__name__)

# Terraform writes the taint marker *after* the colon: `# addr: (tainted)`.
_HEADER = re.compile(r"^# (?P<address>.+?):(?P<tainted> \(tainted\))?$")
_OUTPUTS_HEADER = "Outputs:"
_SENSITIVE_PLACEHOLDER = "(sensitive value)"
_ATTRIBUTE = re.compile(r"^\s+(?P<key>[A-Za-z0-9_\-.]+)\s+= \(sensitive value\)$")


@dataclass(slots=True)
class Resource:
    """A single resource or data source block from the state."""

    address: ResourceAddress
    body: str
    tainted: bool = False

    #: Lowercased ``address + body``, precomputed once so that filtering the
    #: tree on every keystroke stays cheap even for very large states.
    haystack: str = field(default="", repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.haystack:
            self.haystack = f"{self.address.full}\n{self.body}".lower()

    @property
    def full_address(self) -> str:
        return self.address.full

    @property
    def name(self) -> str:
        return self.address.name

    @property
    def module(self) -> str:
        return self.address.module

    @property
    def is_data(self) -> bool:
        return self.address.is_data

    @property
    def is_actionable(self) -> bool:
        """Whether taint/untaint/delete/target make sense for this resource."""
        return not self.address.is_data

    def matches(self, needle: str) -> bool:
        """Case-insensitive substring match across the address and the body."""
        return not needle or needle.lower() in self.haystack

    def reveal(self, secrets: Mapping[str, str]) -> str:
        """Return the body with ``(sensitive value)`` replaced by real values.

        Substitution is keyed on the attribute *name* rather than on position,
        so a resource with several redacted attributes can never show one
        attribute's secret under another attribute's name.
        """
        if not secrets:
            return self.body

        lines = []
        for line in self.body.splitlines():
            match = _ATTRIBUTE.match(line)
            if match is None:
                lines.append(line)
                continue
            value = secrets.get(match["key"])
            if value is None:
                lines.append(line)
            else:
                lines.append(line.replace(_SENSITIVE_PLACEHOLDER, _render(value)))
        return "\n".join(lines) + ("\n" if self.body.endswith("\n") else "")


@dataclass(slots=True)
class State:
    """A parsed Terraform state: its resources, plus any root outputs."""

    resources: dict[str, Resource] = field(default_factory=dict)
    outputs: str = ""

    def __len__(self) -> int:
        return len(self.resources)

    def __iter__(self) -> Iterator[Resource]:
        return iter(self.resources.values())

    def __contains__(self, address: str) -> bool:
        return address in self.resources

    def get(self, address: str) -> Resource | None:
        return self.resources.get(address)

    @property
    def is_empty(self) -> bool:
        return not self.resources

    def filter(self, needle: str) -> list[Resource]:
        """Resources matching ``needle``, in state order."""
        if not needle:
            return list(self.resources.values())
        return [resource for resource in self.resources.values() if resource.matches(needle)]

    def modules(self, resources: Iterable[Resource] | None = None) -> set[str]:
        """Every module path (including intermediate ones) covering ``resources``."""
        pool = self.resources.values() if resources is None else resources
        return {prefix for resource in pool for prefix in resource.address.module_parts}

    def counts(self) -> dict[str, int]:
        managed = sum(1 for resource in self.resources.values() if not resource.is_data)
        return {
            "resources": managed,
            "data": len(self.resources) - managed,
            "tainted": sum(1 for resource in self.resources.values() if resource.tainted),
        }


def parse_state(output: str) -> State:
    """Parse the output of ``terraform show -no-color`` into a :class:`State`."""
    state = State()

    address: ResourceAddress | None = None
    tainted = False
    body: list[str] = []
    outputs: list[str] = []
    in_outputs = False

    def flush() -> None:
        nonlocal address
        if address is not None:
            state.resources[address.full] = Resource(
                address=address,
                body="\n".join(body) + "\n",
                tainted=tainted,
            )
        address = None

    for line in output.splitlines():
        if in_outputs:
            outputs.append(line)
            continue

        header = _HEADER.match(line)
        if header is not None:
            flush()
            address = parse_address(header["address"])
            tainted = header["tainted"] is not None
            body = []
            continue

        if line == _OUTPUTS_HEADER:
            flush()
            in_outputs = True
            continue

        if address is None:
            continue

        body.append(line.rstrip())
        if line == "}":
            flush()

    flush()
    state.outputs = "\n".join(outputs).strip()

    logger.debug(
        "parsed state: %d resources, %d outputs lines",
        len(state.resources),
        len(outputs),
    )
    return state


def extract_sensitive_values(document: Any) -> dict[str, dict[str, str]]:
    """Collect real values for sensitive attributes from ``terraform show -json``.

    Returns a mapping of resource address to ``{attribute: value}``. Only
    attributes that Terraform actually marks sensitive are included.
    """
    found: dict[str, dict[str, str]] = {}
    _walk_sensitive(document, found)
    return found


def _walk_sensitive(node: Any, found: dict[str, dict[str, str]]) -> None:
    if isinstance(node, dict):
        address = node.get("address")
        sensitive = node.get("sensitive_values")
        values = node.get("values")
        if (
            isinstance(address, str)
            and isinstance(sensitive, dict)
            and isinstance(values, dict)
            and node.get("mode") in ("managed", "data")
        ):
            secrets = {
                key: values[key]
                for key, flag in sensitive.items()
                if flag and key in values and values[key] is not None
            }
            if secrets:
                found.setdefault(address, {}).update(secrets)
        for value in node.values():
            _walk_sensitive(value, found)
    elif isinstance(node, list):
        for item in node:
            _walk_sensitive(item, found)


def _render(value: Any) -> str:
    """Render a JSON value the way the text state output would."""
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)
