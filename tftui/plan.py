import asyncio
from tftui.debug_log import setup_logging

logger = setup_logging()


async def execute_plan(executable: str, console) -> tuple[int, str]:
    command = [executable, "plan", "-no-color", "-out=tftui.plan"]

    proc = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        console.write(line.decode("utf-8").strip())

    return_code = await proc.wait()

    return return_code
