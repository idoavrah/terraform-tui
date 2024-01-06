import asyncio
from tftui.debug_log import setup_logging
from textual import work
from textual.widgets import RichLog
from textual.worker import Worker
from rich.text import Text

logger = setup_logging()


class PlanScreen(RichLog):
    executable = None
    active_plan = ""

    BINDINGS = []

    def __init__(self, id, executable, *args, **kwargs):
        super().__init__(id=id, *args, **kwargs)
        self.executable = executable
        self.active_plan = ""
        self.wrap = True

    @work(exclusive=True)
    async def create_plan(self, varfile, targets, destroy="") -> None:
        self.active_plan = ""
        self.auto_scroll = False
        self.parent.loading = True
        self.clear()
        command = [
            self.executable,
            "plan",
            "-no-color",
            "-input=false",
            "-out=tftui.plan",
            "-detailed-exitcode",
        ]
        if varfile:
            command.append(f"-var-file={varfile}")
        if destroy:
            command.append("-destroy")
        if targets:
            for target in targets:
                command.append(f"-target={target}")

        logger.debug(f"Executing command: {command}")
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        block_color = ""

        try:
            while True:
                data = await proc.stdout.readline()
                if not data:
                    break
                self.parent.loading = False
                stripped_line = data.decode("utf-8").rstrip()
                stylzed_line = Text(stripped_line)

                if (
                    stripped_line.startswith("No changes.")
                    or stripped_line == "Terraform will perform the following actions:"
                ):
                    self.clear()
                    self.auto_scroll = False

                if stripped_line == "":
                    block_color = ""
                elif stripped_line.startswith("Plan:"):
                    self.active_plan = stripped_line
                    stylzed_line.stylize("bold")
                elif stripped_line.startswith("  #"):
                    if stripped_line.endswith(
                        "will be destroyed"
                    ) or stripped_line.endswith("must be replaced"):
                        block_color = "red"
                    elif stripped_line.endswith("will be created"):
                        block_color = "green3"
                    elif stripped_line.endswith("will be updated in-place"):
                        block_color = "yellow3"
                    stylzed_line.stylize(f"bold {block_color}")
                elif stripped_line.strip().startswith("-"):
                    stylzed_line.stylize("red")
                elif stripped_line.strip().startswith("+"):
                    stylzed_line.stylize("green3")
                elif stripped_line.strip().startswith("~") and "->" in stripped_line:
                    stylzed_line = Text.assemble(
                        (stripped_line[: stripped_line.find("=") + 1], block_color),
                        (
                            stripped_line[
                                stripped_line.find("=") + 1 : stripped_line.find("->")
                            ],
                            "red",
                        ),
                        (stripped_line[stripped_line.find("->") :], "green3"),
                    )
                else:
                    stylzed_line.stylize(block_color)

                self.write(stylzed_line)
        finally:
            await proc.wait()
            if proc.returncode != 2:
                self.active_plan = ""

        self.focus()

    @work(exclusive=True)
    async def execute_apply(self) -> None:
        self.parent.loading = True
        self.auto_scroll = True
        command = [self.executable, "apply", "-no-color", "tftui.plan"]

        logger.debug(f"Executing command: {command}")
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        self.clear()

        try:
            while True:
                data = await proc.stdout.readline()
                if not data:
                    break
                self.parent.loading = False
                text = Text(data.decode("utf-8").rstrip())
                if text.plain.startswith("Apply complete!"):
                    text.stylize("bold white")
                self.write(text)
        finally:
            await proc.wait()
            self.active_plan = ""

    def on_hide(self) -> None:
        self.active_plan = ""
        self.clear()

    async def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if (
            event.worker.name == "execute_apply"
            and event.worker.state.name == "SUCCESS"
        ):
            self.app.tree.refresh_state(focus=False)
