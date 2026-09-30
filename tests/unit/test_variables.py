"""``--var`` assignments, and the TF_VAR_* environment they become.

Why this exists rather than reusing ``-var-file``: ``terraform show`` and
``terraform state list`` reject ``-var-file`` outright, so a configuration whose
``backend`` block refers to a variable cannot be read that way at all. An
exported ``TF_VAR_*`` reaches every command, which is what makes it work.
Verified against real OpenTofu 1.8.5 and 1.11.0; see tests/integration.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tftui.config import Settings, parse_variables
from tftui.errors import InvalidVariableError
from tftui.terraform.executor import TerraformExecutor

# ------------------------------------------------------------------- parsing


def test_parses_simple_assignments() -> None:
    assert parse_variables(["a=1", "b=two"]) == {"a": "1", "b": "two"}


def test_value_may_contain_equals_signs() -> None:
    """Only the first ``=`` separates; the rest belongs to the value.

    Matters for the case this feature exists for: a backend variable is often an
    object, and JSON is full of characters that a naive split would mangle.
    """
    assert parse_variables(['obj={"token":"a=b=c"}']) == {"obj": '{"token":"a=b=c"}'}


def test_an_empty_value_is_allowed() -> None:
    """``-var 'x='`` is how Terraform spells an empty string, so keep it."""
    assert parse_variables(["x="]) == {"x": ""}


def test_later_assignment_wins() -> None:
    """Matches how Terraform treats a repeated ``-var``."""
    assert parse_variables(["a=1", "a=2"]) == {"a": "2"}


def test_surrounding_space_in_the_name_is_ignored() -> None:
    assert parse_variables([" a =1"]) == {"a": "1"}


def test_missing_equals_is_rejected() -> None:
    """Silently dropping it would surface much later as Terraform complaining."""
    with pytest.raises(InvalidVariableError, match="not name=value"):
        parse_variables(["justaname"])


@pytest.mark.parametrize("name", ["9leading", "has space", "has.dot", "", "a$b", "-lead"])
def test_invalid_names_are_rejected(name: str) -> None:
    """The name becomes an environment variable name, so it has to be usable."""
    with pytest.raises(InvalidVariableError):
        parse_variables([f"{name}=value"])


@pytest.mark.parametrize("name", ["a", "_a", "A1", "with_underscore", "with-hyphen"])
def test_valid_names_are_accepted(name: str) -> None:
    assert parse_variables([f"{name}=v"]) == {name: "v"}


# ------------------------------------------------------------------ settings


def test_settings_expose_a_mapping() -> None:
    settings = Settings(variables=("a=1", "b=2"))
    assert settings.variable_map == {"a": "1", "b": "2"}


def test_no_variables_is_an_empty_mapping() -> None:
    assert Settings().variable_map == {}


# ------------------------------------------------------------------ the environment


def _env(**kwargs: str) -> dict[str, str]:
    executor = TerraformExecutor("terraform", resolve=False, cwd=Path("/tmp"), variables=kwargs)
    return executor._env()


def test_variables_become_tf_var_entries() -> None:
    env = _env(state_path="custom.tfstate")
    assert env["TF_VAR_state_path"] == "custom.tfstate"


def test_no_variables_adds_no_tf_var_entries() -> None:
    executor = TerraformExecutor("terraform", resolve=False, cwd=Path("/tmp"))
    assert not [key for key in executor._env() if key.startswith("TF_VAR_")]


def test_an_explicit_variable_outranks_the_inherited_environment(monkeypatch) -> None:
    """A flag the user typed should win over something left in their shell."""
    monkeypatch.setenv("TF_VAR_region", "from-shell")
    assert _env(region="from-flag")["TF_VAR_region"] == "from-flag"


def test_inherited_tf_vars_still_reach_terraform(monkeypatch) -> None:
    """Exporting TF_VAR_* by hand already worked; it must keep working."""
    monkeypatch.setenv("TF_VAR_untouched", "kept")
    assert _env(other="x")["TF_VAR_untouched"] == "kept"


def test_the_automation_variables_are_still_set() -> None:
    env = _env(a="1")
    assert env["TF_IN_AUTOMATION"] == "1"
    assert env["TF_INPUT"] == "0"
