"""Address parsing - the part most likely to be quietly wrong."""

from __future__ import annotations

import pytest

from tftui.terraform.address import parse_address, split_address


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        ("random_integer.n", ["random_integer", "n"]),
        ("module.a.random_integer.n", ["module", "a", "random_integer", "n"]),
        # Dots inside an index key must not split the address.
        (
            'module.dots["a.b.c"].random_integer.n',
            ["module", 'dots["a.b.c"]', "random_integer", "n"],
        ),
        # Nor must brackets, colons or hashes.
        (
            'module.m["a:b"].local_file.foo["#1"]',
            ["module", 'm["a:b"]', "local_file", 'foo["#1"]'],
        ),
        # A quoted bracket is part of the key, not a nesting level.
        ('r.n["a]b"]', ["r", 'n["a]b"]']),
        # An escaped quote does not end the key.
        (r'r.n["a\"b.c"]', ["r", r'n["a\"b.c"]']),
        ("", [""]),
    ],
)
def test_split_address(address: str, expected: list[str]) -> None:
    assert split_address(address) == expected


@pytest.mark.parametrize(
    ("address", "module", "name", "is_data"),
    [
        ("random_integer.n", "", "random_integer.n", False),
        ("data.local_file.f", "", "data.local_file.f", True),
        ("module.a.random_integer.n", "module.a", "random_integer.n", False),
        ("module.a.data.local_file.f[0]", "module.a", "data.local_file.f[0]", True),
        (
            'module.dots["a.b"].module.venus[0].random_integer.mars["e.f"]',
            'module.dots["a.b"].module.venus[0]',
            'random_integer.mars["e.f"]',
            False,
        ),
        # A resource whose *type* begins with "module" is not a module path.
        ("module_thing.n", "", "module_thing.n", False),
    ],
)
def test_parse_address(address: str, module: str, name: str, is_data: bool) -> None:
    parsed = parse_address(address)
    assert parsed.full == address
    assert parsed.module == module
    assert parsed.name == name
    assert parsed.is_data is is_data


def test_module_parts_are_progressive_prefixes() -> None:
    parsed = parse_address('module.a["x.y"].module.b[0].module.c.random_integer.n')
    assert parsed.module_parts == (
        'module.a["x.y"]',
        'module.a["x.y"].module.b[0]',
        'module.a["x.y"].module.b[0].module.c',
    )
    assert parsed.depth == 3


def test_root_resource_has_no_module_parts() -> None:
    parsed = parse_address("random_integer.n")
    assert parsed.module_parts == ()
    assert parsed.depth == 0
