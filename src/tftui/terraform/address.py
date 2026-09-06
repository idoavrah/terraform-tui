"""Parsing of Terraform resource addresses.

A Terraform address looks like::

    module.dots["string.with.dots"].module.venus[0].data.local_file.pluto[1]

Splitting it is fiddly because index keys may themselves contain dots, quotes
and brackets. :func:`split_address` is a single-pass tokenizer that tracks
bracket depth and quoting, which is both faster and more correct than a regex
lookahead.
"""

from __future__ import annotations

from dataclasses import dataclass

_MODULE = "module"
_DATA = "data"


def split_address(address: str) -> list[str]:
    """Split ``address`` on dots that sit outside brackets and quotes.

    >>> split_address('module.dots["a.b"].random_integer.mars["e.f"]')
    ['module', 'dots["a.b"]', 'random_integer', 'mars["e.f"]']
    """
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    quote: str | None = None
    escaped = False

    for char in address:
        if quote is not None:
            current.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue

        if char in "\"'":
            quote = char
            current.append(char)
        elif char == "[":
            depth += 1
            current.append(char)
        elif char == "]":
            depth = max(0, depth - 1)
            current.append(char)
        elif char == "." and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)

    parts.append("".join(current))
    return parts


@dataclass(frozen=True, slots=True)
class ResourceAddress:
    """A parsed Terraform address, split into its module path and resource name."""

    full: str
    """The original, complete address."""

    module: str
    """Dotted module path, e.g. ``module.a.module.b``. Empty for root resources."""

    name: str
    """The resource portion, e.g. ``data.local_file.pluto[1]`` or ``random_integer.n``."""

    is_data: bool
    """True for data sources, which cannot be tainted, deleted or planned against."""

    @property
    def module_parts(self) -> tuple[str, ...]:
        """Progressive module prefixes, outermost first.

        ``module.a.module.b`` yields ``('module.a', 'module.a.module.b')``.
        """
        if not self.module:
            return ()
        pieces = split_address(self.module)
        out: list[str] = []
        for index in range(0, len(pieces), 2):
            segment = ".".join(pieces[index : index + 2])
            out.append(f"{out[-1]}.{segment}" if out else segment)
        return tuple(out)

    @property
    def depth(self) -> int:
        """How many modules deep this resource sits. Root resources are 0."""
        return len(self.module_parts)


def parse_address(address: str) -> ResourceAddress:
    """Parse ``address`` into its module path and resource name."""
    parts = split_address(address)

    index = 0
    while index + 1 < len(parts) and _strip_index(parts[index]) == _MODULE:
        index += 2

    module = ".".join(parts[:index])
    remainder = parts[index:]
    is_data = bool(remainder) and _strip_index(remainder[0]) == _DATA
    name = ".".join(remainder)

    return ResourceAddress(full=address, module=module, name=name, is_data=is_data)


def _strip_index(part: str) -> str:
    """Return ``part`` without any trailing ``[...]`` index."""
    bracket = part.find("[")
    return part if bracket == -1 else part[:bracket]
