"""Syntax highlighting choices."""

from __future__ import annotations

from tftui.widgets.resource_view import highlight_lines, syntax_theme

CODE = 'resource "a" "b" {\n    id = "1"\n    name = "x"\n}\n'


def test_syntax_theme_follows_light_and_dark() -> None:
    assert syntax_theme(dark=True) == "ansi_dark"
    assert syntax_theme(dark=False) == "ansi_light"
    assert syntax_theme(dark=True) != syntax_theme(dark=False)


def test_highlight_returns_one_entry_per_source_line() -> None:
    """Line-by-line output is what makes the pane searchable and scrollable."""
    lines = highlight_lines(CODE, dark=True)
    assert [line.plain for line in lines] == CODE.rstrip("\n").split("\n")


def test_highlighted_code_carries_no_background() -> None:
    """A background here would override the pane's own, mismatching whitespace."""
    for dark in (True, False):
        backgrounds = {
            span.style.bgcolor
            for line in highlight_lines(CODE, dark=dark)
            for span in line.spans
            if getattr(span.style, "bgcolor", None) is not None
        }
        assert backgrounds == set(), f"dark={dark} painted {backgrounds}"


def test_highlighting_actually_colours_the_code() -> None:
    colours = {str(span.style) for line in highlight_lines(CODE, dark=True) for span in line.spans}
    assert len(colours) > 1


def test_no_trailing_blank_line() -> None:
    assert highlight_lines(CODE, dark=True)[-1].plain == "}"
