"""Syntax highlighting choices."""

from __future__ import annotations

from rich.console import Console

from tftui.widgets.resource_view import highlight, syntax_theme

CODE = 'resource "a" "b" {\n    id = "1"\n}\n'


def test_syntax_theme_follows_light_and_dark() -> None:
    assert syntax_theme(dark=True) == "ansi_dark"
    assert syntax_theme(dark=False) == "ansi_light"
    assert syntax_theme(dark=True) != syntax_theme(dark=False)


def _segments(dark: bool):
    console = Console(width=60, force_terminal=True)
    rendered = highlight(CODE, dark=dark)
    return list(console.render(rendered, console.options.update_width(60)))


def test_highlighted_code_carries_no_background() -> None:
    """A background here would override the pane's own, mismatching whitespace."""
    for dark in (True, False):
        backgrounds = {
            segment.style.bgcolor
            for segment in _segments(dark)
            if segment.style is not None and segment.style.bgcolor is not None
        }
        assert backgrounds == set(), f"dark={dark} painted {backgrounds}"


def test_highlighting_actually_colours_the_code() -> None:
    colours = {
        segment.style.color
        for segment in _segments(dark=True)
        if segment.style is not None and segment.style.color is not None
    }
    assert len(colours) > 1
