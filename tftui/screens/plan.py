import asyncio
from tftui.debug_log import setup_logging
from textual.widgets import RichLog
from textual.app import App, ComposeResult
from rich.text import Text

logger = setup_logging()


class PlanScreen(RichLog):
    executable = None

    BINDINGS = []

    def __init__(self, id, executable, *args, **kwargs):
        self.executable = executable
        super().__init__(id=id, *args, **kwargs)

    async def execute_plan(self) -> None:
        command = [self.executable, "plan", "-no-color", "-out=tftui.plan"]

        proc = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        stdout, strerr = await proc.communicate()
        response = stdout.decode("utf-8")
        output = ""
        block_color = ""

        for line in response.splitlines():
            if not output:
                if line.strip() == "Terraform will perform the following actions:":
                    output += line + "\n"
            else:
                output += line + "\n"

        for line in output.splitlines():
            stripped_line = line.strip()
            stylzed_line = Text(line)
            if line.startswith("  #"):
                if stripped_line.endswith(
                    "will be destroyed"
                ) or stripped_line.endswith("must be replaced"):
                    block_color = "red"
                elif stripped_line.endswith("will be created"):
                    block_color = "green3"
                elif stripped_line.endswith("will be updated in-place"):
                    block_color = "yellow"
                stylzed_line.stylize("bold")
            elif stripped_line.startswith("Plan:"):
                block_color = "white"
                stylzed_line.stylize(block_color)
                self.write(stylzed_line)
                break
            if line.startswith("      ~"):
                stylzed_line = Text.assemble(
                    (line[: line.find("=") + 1], block_color),
                    (line[line.find("=") + 1 : line.find("->")], "red"),
                    (line[line.find("->") :], "green3"),
                )
            else:
                stylzed_line.stylize(block_color)

            self.write(stylzed_line)


if __name__ == "__main__":

    class PlanApp(App):
        def compose(self) -> ComposeResult:
            yield PlanScreen("plan", executable="terraform")

        async def on_ready(self) -> None:
            await self.get_child_by_id("plan").execute_plan()

    app = PlanApp()
    app.run()
