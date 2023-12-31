import asyncio
import re
import logging
import json
from collections import Counter
from tftui.debug_log import setup_logging

logger = setup_logging()


async def execute_async(*command: str) -> tuple[str, str]:
    command = [word for phrase in command for word in phrase.split()]

    proc = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    stdout, strerr = await proc.communicate()
    response = stdout.decode("utf-8")
    logger.debug(
        "Executed command: %s",
        json.dumps({"command": command, "return_code": proc.returncode}, indent=2),
    )
    return (proc.returncode, response)


def split_resource_name(fullname: str) -> list[str]:
    # Thanks Chatgpt, couldn't do this without you; please don't become sentient and kill us all
    pattern = r"\.(?=(?:[^\[\]]*\[[^\[\]]*\])*[^\[\]]*$)"
    return re.split(pattern, fullname)


class Block:
    TYPE_RESOURCE = "resource"
    TYPE_DATASOURCE = "data"

    type = None
    name = None
    submodule = None
    contents = ""
    is_tainted = False

    def __init__(self, submodule: str, name: str, type: str, is_tainted: bool):
        self.type = type
        self.name = name
        self.submodule = submodule
        self.is_tainted = is_tainted


class State:
    state_tree = {}
    executable = ""
    no_init = False

    def __init__(self, executable="terraform", no_init=False):
        self.executable = executable
        self.no_init = no_init

    def parse_block(line: str) -> tuple[str, str, str]:
        fullname = line[2 : line.rindex(":")]
        is_tainted = line.endswith("(tainted)")
        parts = split_resource_name(fullname)
        if fullname.startswith("data") or ".data." in fullname:
            name = ".".join(parts[-3:])
            submodule = ".".join(parts[:-3])
            type = Block.TYPE_DATASOURCE
        else:
            name = ".".join(parts[-2:])
            submodule = ".".join(parts[:-2])
            type = Block.TYPE_RESOURCE

        return (fullname, name, submodule, type, is_tainted)

    async def refresh_state(self) -> None:
        returncode, stdout = await execute_async(self.executable, "show -no-color")
        if returncode != 0 or stdout.startswith("No state"):
            raise Exception(stdout)

        self.state_tree = {}
        state_output = stdout.splitlines()
        logger.debug(f"state show line count: {len(state_output)}")

        if stdout.startswith("The state file is empty."):
            return

        contents = ""
        for line in state_output:
            if line.startswith("#"):
                (fullname, name, submodule, type, is_tainted) = State.parse_block(line)
                contents = ""
            elif line.startswith("}"):
                contents += line.rstrip() + "\n"
                block = Block(submodule, name, type, is_tainted)
                block.contents = contents
                self.state_tree[fullname] = block
            else:
                contents += line.rstrip() + "\n"

        if logger.isEnabledFor(logging.DEBUG):
            for key, block in self.state_tree.items():
                logger.debug(
                    "Parsed block: %s",
                    json.dumps(
                        {
                            "fullname": key,
                            "module": block.submodule,
                            "name": block.name,
                            "lines": block.contents.count("\n"),
                            "tainted": block.is_tainted,
                        },
                        indent=2,
                    ),
                )
            logger.debug(
                "Total blocks: %s",
                json.dumps(
                    Counter(block.type for block in self.state_tree.values()), indent=2
                ),
            )


if __name__ == "__main__":
    state = State()
    try:
        asyncio.run(state.refresh_state())
        for block in state.state_tree.values():
            print(block.submodule, block.name, block.type, block.is_tainted)
    except Exception as e:
        print(e)
