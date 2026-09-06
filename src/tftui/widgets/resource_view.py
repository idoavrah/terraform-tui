"""The pane that renders a single resource's state."""

from __future__ import annotations

from typing import Any

from rich.syntax import Syntax

from tftui.terraform.state import Resource
from tftui.widgets.reflowing_log import ReflowingLog


class ResourceView(ReflowingLog):
    """Shows one resource block, with sensitive values hidden until asked for.

    HCL syntax highlighting replaces the previous generic value highlighting,
    which is what makes a 200-line resource readable at a glance.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            highlight=False,
            markup=False,
            wrap=True,
            auto_scroll=False,
            **kwargs,
        )
        self.resource: Resource | None = None
        self.revealed = False
        self._body = ""

    def show(
        self,
        resource: Resource,
        *,
        revealed: bool = False,
        secrets: dict[str, str] | None = None,
    ) -> None:
        """Render ``resource``, optionally substituting its sensitive values."""
        secrets = secrets or {}
        self.resource = resource
        self.revealed = revealed and bool(secrets)
        self._body = resource.reveal(secrets) if self.revealed else resource.body

        self.reset_content()
        self.append(
            Syntax(
                self._body,
                "hcl",
                theme="ansi_dark",
                background_color="default",
                word_wrap=True,
            )
        )
        self.scroll_home(animate=False)

    @property
    def body(self) -> str:
        """Exactly what is on screen - so copy and full-screen agree with the view."""
        return self._body

    @property
    def title(self) -> str:
        return self.resource.full_address if self.resource is not None else ""

    def reset(self) -> None:
        self.resource = None
        self.revealed = False
        self._body = ""
        self.reset_content()
