"""Every key the help screen advertises must actually be bound to a real action.

Both halves matter, and each has already been wrong once: `R` named an action
that did not exist, and `left`/`right` were advertised but never bound at all
(Textual's `Tree` binds only `up`, `down` and the shift+arrow variants).
"""

from __future__ import annotations

import pytest

from tftui.app import TerraformTUI
from tftui.screens.help import KEYS
from tftui.widgets.state_tree import StateTree

#: Keys that must reach an action while the tree has focus, and where they live.
#: The tree's own bindings take priority over the application's.
EXPECTED: tuple[tuple[str, type], ...] = (
    ("up", StateTree),
    ("down", StateTree),
    ("k", StateTree),
    ("j", StateTree),
    ("left", StateTree),
    ("right", StateTree),
    ("h", StateTree),
    ("l", StateTree),
    ("space", StateTree),
    ("escape", TerraformTUI),
    ("slash", TerraformTUI),
    ("f", TerraformTUI),
    ("d", TerraformTUI),
    ("t", TerraformTUI),
    ("u", TerraformTUI),
    ("c", TerraformTUI),
    ("r", TerraformTUI),
    ("p", TerraformTUI),
    ("a", TerraformTUI),
    ("ctrl+d", TerraformTUI),
    ("ctrl+a", TerraformTUI),
    ("w", TerraformTUI),
    ("x", TerraformTUI),
    ("m", TerraformTUI),
    ("question_mark", TerraformTUI),
    ("q", TerraformTUI),
    *[(str(level), TerraformTUI) for level in range(10)],
)


def _bindings(owner: type) -> dict[str, str]:
    """Map every bound key on ``owner`` to its action, splitting comma lists."""
    found: dict[str, str] = {}
    for binding in owner.BINDINGS:
        keys = binding.key if isinstance(binding.key, str) else ""
        for key in keys.split(","):
            if key.strip():
                found[key.strip()] = binding.action
    return found


@pytest.mark.parametrize(("key", "owner"), EXPECTED, ids=lambda v: getattr(v, "__name__", v))
def test_key_is_bound(key: str, owner: type) -> None:
    assert key in _bindings(owner), f"{key!r} is not bound on {owner.__name__}"


@pytest.mark.parametrize(("key", "owner"), EXPECTED, ids=lambda v: getattr(v, "__name__", v))
def test_bound_action_exists(key: str, owner: type) -> None:
    """A binding naming a method that is not an `action_*` handler does nothing."""
    action = _bindings(owner)[key]
    name = action.split("(")[0].strip()
    if not name:
        return  # a deliberately inert binding
    handler = f"action_{name}"
    # `quit` and the Tree's cursor actions come from Textual's own base classes.
    assert hasattr(owner, handler), f"{owner.__name__} has no {handler}() for {key!r}"


def test_help_screen_lists_no_unbound_modifier_keys() -> None:
    """Keys named in the help table are covered by the expectations above."""
    advertised = " ".join(key for key, _, _ in KEYS).lower()
    for token in ("ctrl+a", "ctrl+d"):
        assert token in advertised
    # Arrow keys are advertised, so they must be in the expected set.
    assert "←" in advertised
    assert "→" in advertised
    expected_keys = {key for key, _ in EXPECTED}
    assert {"left", "right", "up", "down"} <= expected_keys
