"""Plan colourising and summarising."""

from __future__ import annotations

import pytest

from tftui.terraform.plan import Change, PlanStyler, classify, is_banner


@pytest.mark.parametrize(
    ("verb", "expected"),
    [
        ("will be created", Change.CREATE),
        ("will be destroyed", Change.DESTROY),
        ("must be replaced", Change.REPLACE),
        ("will be replaced, as requested", Change.REPLACE),
        ("will be updated in-place", Change.UPDATE),
        ("will be read during apply", Change.READ),
        ("will do something new terraform invented", Change.UNKNOWN),
    ],
)
def test_classify(verb: str, expected: Change) -> None:
    assert classify(verb) == expected


def test_header_sets_block_colour_for_following_lines() -> None:
    styler = PlanStyler()
    styler.style("  # random_integer.n will be destroyed")
    assert styler.block is Change.DESTROY
    # A body line with no sigil inherits the block's colour.
    assert styler.style("      id = 1").style == "red"


def test_blank_line_closes_the_block() -> None:
    styler = PlanStyler()
    styler.style("  # random_integer.n will be created")
    assert styler.block is Change.CREATE
    styler.style("")
    assert styler.block is Change.UNKNOWN


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("      + id = 1", "green3"),
        ("      - id = 1", "red"),
        ('    -/+ resource "local_file" "foo" {', "red"),
        ('    +/- resource "local_file" "foo" {', "red"),
    ],
)
def test_sigil_lines_get_their_own_colour(line: str, expected: str) -> None:
    assert PlanStyler().style(line).style == expected


def test_in_place_change_splits_old_and_new() -> None:
    styled = PlanStyler().style('      ~ name = "old" -> "new"')
    spans = [(styled.plain[span.start : span.end], span.style) for span in styled.spans]
    old = next(text for text, style in spans if style == "red")
    new = next(text for text, style in spans if style == "green3")
    assert '"old"' in old
    assert '"new"' in new
    # The attribute name belongs to neither side.
    assert "name" not in old
    assert "name" not in new


def test_tilde_without_arrow_is_not_split() -> None:
    styled = PlanStyler().style("      ~ tags = {")
    assert len(styled.spans) <= 1


def test_summary_line_is_recorded() -> None:
    styler = PlanStyler()
    styler.style("Plan: 3 to add, 1 to change, 2 to destroy.")
    assert styler.summary == "Plan: 3 to add, 1 to change, 2 to destroy."
    assert styler.title() == "Plan: 3 to add, 1 to change, 2 to destroy."


def test_no_changes_is_recorded() -> None:
    styler = PlanStyler()
    styler.style("No changes. Your infrastructure matches the configuration.")
    assert styler.no_changes
    assert styler.title() == "No changes"


def test_title_without_a_plan() -> None:
    assert PlanStyler().title() == "Plan"


def test_reset_clears_everything() -> None:
    styler = PlanStyler()
    styler.style("  # a.b will be created")
    styler.style("Plan: 1 to add, 0 to change, 0 to destroy.")
    styler.reset()
    assert styler.headers == []
    assert styler.summary == ""
    assert styler.block is Change.UNKNOWN


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("Terraform will perform the following actions:", True),
        ("No changes. Your infrastructure matches the configuration.", True),
        ("random_integer.n: Refreshing state... [id=5]", False),
        ("", False),
    ],
)
def test_is_banner(line: str, expected: bool) -> None:
    assert is_banner(line) is expected


# ----------------------------------------------------- against real plan output


def test_real_create_plan(plan_text: str) -> None:
    styler = PlanStyler()
    for line in plan_text.splitlines():
        styler.style(line)

    assert styler.summary == "Plan: 30 to add, 0 to change, 0 to destroy."
    assert len(styler.headers) == 30
    assert all(change is Change.CREATE for _, change in styler.headers)
    assert not styler.no_changes


def test_real_replace_plan() -> None:
    from pathlib import Path

    text = (Path(__file__).parents[1] / "fixtures" / "plan_replace.txt").read_text()
    styler = PlanStyler()
    for line in text.splitlines():
        styler.style(line)

    assert styler.headers
    assert any(change is Change.REPLACE for _, change in styler.headers)
    # Addresses survive parsing intact, index keys and all.
    assert any('local_file.foo["#3"]' in address for address, _ in styler.headers)


def test_summary_text_lists_each_resource(plan_text: str) -> None:
    styler = PlanStyler()
    for line in plan_text.splitlines():
        styler.style(line)

    summary = styler.summary_text().plain
    assert summary.startswith("Plan: 30 to add")
    assert summary.count("\n  + ") == 30
