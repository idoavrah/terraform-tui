import asyncio
import re


async def execute_async(*command: str) -> tuple[str, str]:
    command = [word for phrase in command for word in phrase.split()]

    proc = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    stdout, strerr = await proc.communicate()
    response = stdout.decode("utf-8")

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
    contents = None
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
        for line in stdout.splitlines():
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


if __name__ == "__main__":
    state = State()
    try:
        asyncio.run(state.refresh_state())
        for block in state.state_tree.values():
            print(block.submodule, block.name, block.type, block.is_tainted)
    except Exception as e:
        print(e)
