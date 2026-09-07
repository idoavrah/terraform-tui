#!/usr/bin/env -S uv run python
"""Regenerate the SVG screenshots in docs/screenshots.

Drives the real application headlessly against ``examples/terraform``, which
must already be applied (``make example-apply``). Each screenshot is a real
render, not a mock-up, so the docs cannot drift from the UI.

    make screenshots
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from tftui.app import TerraformTUI
from tftui.config import Settings
from tftui.terraform.client import TerraformClient
from tftui.terraform.executor import TerraformExecutor

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "examples" / "terraform"
OUT = ROOT / "docs" / "screenshots"
SIZE = (140, 40)

#: Each entry is (filename, caption, keys). "wait:N" pauses for N seconds.
SHOTS: list[tuple[str, str, list[str]]] = [
    ("01-state-tree", "The state tree", ["1", "2"]),
    (
        "02-resource-view",
        "A single resource",
        ["1", *["j"] * 10, "enter"],
    ),
    (
        "03-sensitive-revealed",
        "Sensitive values revealed with X",
        ["1", *["j"] * 10, "enter", "x"],
    ),
    ("04-search", "Filtering the tree", ["slash", "m", "a", "r", "s"]),
    ("05-help", "The help screen", ["question_mark"]),
    (
        "06-selection-and-confirm",
        "Confirming a taint",
        ["1", *["j"] * 8, "space", "j", "space", "t"],
    ),
    ("07-plan-dialog", "Plan options", ["p", "wait:1"]),
    ("08-plan", "A colourised plan", ["p", "wait:1", "enter", "wait:45"]),
    ("09-workspaces", "Switching workspace", ["w", "wait:2"]),
]


async def _wait_loaded(app: TerraformTUI, pilot: object) -> None:
    for _ in range(300):
        if len(app.state_tree.state) and not app.state_tree.loading:
            await pilot.pause(0.3)  # type: ignore[attr-defined]
            return
        await pilot.pause(0.1)  # type: ignore[attr-defined]
    raise SystemExit("state never loaded - run 'make example-apply' first")


async def _shoot(name: str, caption: str, keys: list[str]) -> None:
    client = TerraformClient(TerraformExecutor("terraform", cwd=PROJECT))
    app = TerraformTUI(client, Settings(run_init=False, offline=True, usage_tracking=False))
    try:
        async with app.run_test(size=SIZE) as pilot:
            await _wait_loaded(app, pilot)
            for key in keys:
                if key.startswith("wait:"):
                    await pilot.pause(float(key[5:]))
                    continue
                await pilot.press(key)
                await pilot.pause(0.25)
            await pilot.pause(0.4)
            (OUT / f"{name}.svg").write_text(app.export_screenshot(title=caption))
            print(f"  {name}.svg  -  {caption}")
    finally:
        client.cleanup()


async def main() -> None:
    if not (PROJECT / "terraform.tfstate").exists():
        raise SystemExit("no state in examples/terraform - run 'make example-apply' first")

    OUT.mkdir(parents=True, exist_ok=True)

    # Remove one generated file so the plan screenshot shows a real diff, then
    # put the project back exactly as it was.
    generated = sorted((PROJECT / "generated").iterdir())
    if not generated:
        raise SystemExit("no generated files - run 'make example-apply' first")
    victim = generated[0]
    backup = victim.read_bytes()
    victim.unlink()

    try:
        print("Writing screenshots to docs/screenshots:")
        for name, caption, keys in SHOTS:
            await _shoot(name, caption, keys)
    finally:
        victim.write_bytes(backup)

    print("\nDone. The example project was left unchanged.")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))  # type: ignore[func-returns-value]
