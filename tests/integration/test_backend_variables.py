"""A `backend` block that refers to a variable, against a real binary (issue #85).

OpenTofu 1.8 added early variable evaluation, which allows variables inside a
``backend`` block. Getting tftui to read such a state turned out to need more
than passing ``-var-file`` to ``init``, and these tests pin down exactly what:

* ``init`` does need the variables, and ``-var-file`` is enough for it;
* ``show`` and ``state list`` need them too, and **reject** ``-var-file``, so
  after a perfectly successful ``init`` they still fail;
* an exported ``TF_VAR_*`` reaches every command, which is what makes it work.

Confirmed by hand against OpenTofu 1.8.5 and 1.11.0 before being written down
here. Terraform itself does not support variables in a backend block, so these
skip unless the binary under test is OpenTofu 1.8 or newer - which is what the
``Integration (opentofu)`` CI job provides.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from tftui.errors import ExecutableNotFoundError, TftuiError
from tftui.terraform.client import TerraformClient
from tftui.terraform.executor import TerraformExecutor

pytestmark = pytest.mark.integration

#: A configuration whose backend path comes from a variable. `terraform_data` is
#: built in, so no provider has to be downloaded for this to work.
CONFIG = """
variable "state_path" {
  type = string
}

terraform {
  backend "local" {
    path = var.state_path
  }
}

resource "terraform_data" "thing" {
  input = "hello"
}
"""

VARS = 'state_path = "custom.tfstate"\n'


def _opentofu_version() -> tuple[int, int] | None:
    """The OpenTofu version of the binary on PATH, or ``None`` if it is not one.

    The CI job that installs OpenTofu aliases it as ``terraform``, so the name
    says nothing; the version banner is what distinguishes them.
    """
    try:
        executor = TerraformExecutor("terraform")
    except ExecutableNotFoundError:
        return None
    try:
        banner = subprocess.run(
            [executor.path, "version"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - environmental
        return None

    match = re.search(r"OpenTofu v(\d+)\.(\d+)", banner)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


_VERSION = _opentofu_version()

requires_early_eval = pytest.mark.skipif(
    _VERSION is None or _VERSION < (1, 8),
    reason="needs OpenTofu 1.8+, which evaluates variables early enough for a backend block",
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    directory = tmp_path / "backend-vars"
    directory.mkdir()
    (directory / "main.tf").write_text(CONFIG, encoding="utf-8")
    (directory / "vars.tfvars").write_text(VARS, encoding="utf-8")
    return directory


def _executor(directory: Path, **variables: str) -> TerraformExecutor:
    return TerraformExecutor("terraform", cwd=directory, variables=variables)


async def _apply(executor: TerraformExecutor) -> None:
    """Create the state the read tests need, through tftui's own async executor."""
    result = await executor.run("apply", "-auto-approve", "-no-color", "-var-file=vars.tfvars")
    assert result.ok, result.output


@requires_early_eval
async def test_init_needs_the_variables_and_var_file_supplies_them(project: Path) -> None:
    """The failure @sarg3nt reported, and the half of it that -var-file does fix."""
    bare = TerraformClient(_executor(project))
    without = await bare.init()
    assert not without.ok, "init should fail when the backend's variable is unset"

    with_file = await bare.init(var_files=["vars.tfvars"])
    assert with_file.ok, with_file.output


@requires_early_eval
async def test_reading_state_fails_after_init_without_variables(project: Path) -> None:
    """The part that -var-file cannot reach.

    `show` and `state list` do not accept -var-file, so a successful init is not
    enough: the backend block is re-evaluated and the variable is missing again.
    This is why issue #85 was not closed by forwarding var-files to init.
    """
    executor = _executor(project)
    client = TerraformClient(executor)
    assert (await client.init(var_files=["vars.tfvars"])).ok
    await _apply(executor)

    with pytest.raises(TftuiError):
        await client.load_state()


@requires_early_eval
async def test_tf_var_makes_the_state_readable(project: Path) -> None:
    """What actually fixes it: a variable exported for every command."""
    plain = _executor(project)
    assert (await TerraformClient(plain).init(var_files=["vars.tfvars"])).ok
    await _apply(plain)

    # The same directory, read by a client carrying --var.
    client = TerraformClient(_executor(project, state_path="custom.tfstate"))
    loaded = await client.load_state()

    assert "terraform_data.thing" in loaded.state.resources
    assert (project / "custom.tfstate").is_file(), "the variable chose this path"


@requires_early_eval
async def test_init_also_works_from_var_alone(project: Path) -> None:
    """--var is enough on its own: no var-file needed anywhere."""
    client = TerraformClient(_executor(project, state_path="custom.tfstate"))
    result = await client.init()
    assert result.ok, result.output
