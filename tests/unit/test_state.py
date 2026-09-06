"""State parsing, filtering and sensitive-value handling."""

from __future__ import annotations

import json

import pytest

from tftui.terraform.address import parse_address
from tftui.terraform.state import (
    Resource,
    State,
    extract_sensitive_values,
    parse_state,
)


def test_parses_every_block_from_real_output(state: State) -> None:
    counts = state.counts()
    assert len(state) == 96
    assert counts == {"resources": 83, "data": 13, "tainted": 0}


def test_captures_root_outputs(state: State) -> None:
    # The previous parser dropped everything after the `Outputs:` header.
    assert state.outputs == 'greeting = "hello nothing"'


def test_bodies_are_complete_blocks(state: State) -> None:
    body = state.resources["random_integer.random_number"].body
    assert body.startswith('resource "random_integer" "random_number" {')
    assert body.rstrip().endswith("}")
    assert "max    = 100" in body


def test_heredoc_content_stays_inside_its_resource(state: State) -> None:
    """A heredoc body containing `#1` must not be mistaken for a block header."""
    address = 'module.mercury.module.venus[0].local_file.foo["#1"]'
    resource = state.resources[address]
    assert "<<-EOT" in resource.body
    assert "        #1" in resource.body
    assert "EOT" in resource.body


def test_addresses_with_awkward_keys_round_trip(state: State) -> None:
    address = (
        'module.dots["another.string.with.dots"].module.venus[0]'
        '.module.uranus.random_integer.mars["e.f"]'
    )
    resource = state.resources[address]
    assert resource.name == 'random_integer.mars["e.f"]'
    assert resource.address.depth == 3


def test_tainted_resources_are_flagged() -> None:
    output = "\n".join(
        [
            "# random_integer.n: (tainted)",
            'resource "random_integer" "n" {',
            '    id = "1"',
            "}",
            "",
            "# random_integer.m:",
            'resource "random_integer" "m" {',
            '    id = "2"',
            "}",
        ]
    )
    parsed = parse_state(output)
    assert parsed.resources["random_integer.n"].tainted is True
    assert parsed.resources["random_integer.m"].tainted is False


def test_empty_output_yields_empty_state() -> None:
    parsed = parse_state("")
    assert parsed.is_empty
    assert parsed.outputs == ""


def test_no_state_message_yields_empty_state() -> None:
    parsed = parse_state("The state file is empty. No resources are represented.\n")
    assert parsed.is_empty


# ------------------------------------------------------------------ filtering


def test_filter_is_case_insensitive(state: State) -> None:
    assert state.filter("MARS") == state.filter("mars")
    # 5 module instances x 2 venus copies x 2 mars keys.
    assert len(state.filter("mars")) == 20


def test_filter_matches_resource_bodies(state: State) -> None:
    # `bcrypt_hash` appears only inside bodies, never in an address.
    matches = state.filter("bcrypt_hash")
    assert matches
    assert all("bcrypt_hash" in resource.body for resource in matches)


def test_filter_matches_module_names(state: State) -> None:
    matches = state.filter("colons")
    assert matches
    assert all("colons" in resource.full_address for resource in matches)


def test_empty_filter_returns_everything(state: State) -> None:
    assert len(state.filter("")) == len(state)


def test_modules_covers_intermediate_levels(state: State) -> None:
    matches = state.filter("mars")
    modules = state.modules(matches)
    # Every ancestor module of a match must be present, or the tree cannot be built.
    assert 'module.dots["string.with.dots"]' in modules
    assert 'module.dots["string.with.dots"].module.venus[0]' in modules
    assert 'module.dots["string.with.dots"].module.venus[0].module.uranus' in modules


# ------------------------------------------------------------------ sensitive


def test_extract_sensitive_values_finds_secrets(state_json: str) -> None:
    secrets = extract_sensitive_values(json.loads(state_json))
    assert "random_password.password" in secrets
    assert set(secrets["random_password.password"]) == {"bcrypt_hash", "result"}


def test_extract_ignores_attributes_flagged_false() -> None:
    """Only attributes Terraform actually marks sensitive are collected.

    Several providers list every attribute in `sensitive_values` with a
    `false` flag; keying on presence rather than on the flag would treat
    ordinary attributes as secrets.
    """
    document = {
        "values": {
            "root_module": {
                "resources": [
                    {
                        "address": "a.b",
                        "mode": "managed",
                        "values": {"secret": "s3cret", "public": "visible"},
                        "sensitive_values": {"secret": True, "public": False},
                    }
                ]
            }
        }
    }
    assert extract_sensitive_values(document) == {"a.b": {"secret": "s3cret"}}


def test_reveal_substitutes_by_attribute_name() -> None:
    """Substitution is keyed on the attribute, never on the order of redactions."""
    resource = Resource(
        address=parse_address("a.b"),
        body=(
            'resource "a" "b" {\n'
            "    alpha = (sensitive value)\n"
            '    beta  = "plain"\n'
            "    gamma = (sensitive value)\n"
            "}\n"
        ),
    )
    revealed = resource.reveal({"gamma": "GAMMA", "alpha": "ALPHA"})
    assert '    alpha = "ALPHA"' in revealed
    assert '    gamma = "GAMMA"' in revealed
    assert '    beta  = "plain"' in revealed


def test_reveal_leaves_unknown_attributes_redacted() -> None:
    resource = Resource(
        address=parse_address("a.b"),
        body='resource "a" "b" {\n    alpha = (sensitive value)\n}\n',
    )
    assert resource.reveal({"other": "x"}) == resource.body


def test_reveal_without_secrets_is_identity(state: State) -> None:
    resource = state.resources["random_password.password"]
    assert resource.reveal({}) == resource.body


@pytest.mark.parametrize(
    ("value", "rendered"),
    [("text", '"text"'), (True, "true"), (False, "false"), (7, "7")],
)
def test_reveal_renders_json_types_like_terraform(value: object, rendered: str) -> None:
    resource = Resource(
        address=parse_address("a.b"),
        body='resource "a" "b" {\n    alpha = (sensitive value)\n}\n',
    )
    assert f"alpha = {rendered}" in resource.reveal({"alpha": value})


# ---------------------------------------------------------------- properties


def test_data_sources_are_not_actionable(state: State) -> None:
    data = state.resources["data.local_file.saturn[0]"]
    managed = state.resources["random_integer.random_number"]
    assert data.is_actionable is False
    assert managed.is_actionable is True


def test_tainted_flag_from_real_terraform_output() -> None:
    """Terraform writes `# address: (tainted)` - the marker follows the colon."""
    from pathlib import Path

    text = (Path(__file__).parents[1] / "fixtures" / "state_tainted.txt").read_text()
    parsed = parse_state(text)
    assert parsed.resources["random_integer.random_number"].tainted is True
    assert parsed.counts()["tainted"] == 1
    # The tainted resource must still be parsed, not skipped.
    assert len(parsed) == 96
