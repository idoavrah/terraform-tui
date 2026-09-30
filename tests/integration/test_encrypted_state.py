"""Reading an encrypted state file, against a real binary (issue #90).

@linuxswords asked for support for encrypted state on GCP. It turns out no
support is needed: tftui never reads a state file, it parses the output of
``show``, and the child process inherits the whole environment - so whatever
makes ``tofu show`` work in a shell works under tftui too.

That is a claim worth a test rather than a comment, because it rests on
something easy to break by accident: if the executor ever stopped passing the
environment through, or started building a curated one, encrypted state would
break silently and the failure would look like a parsing bug.

Uses OpenTofu's state encryption, which is configured entirely through
``TF_ENCRYPTION``. Skips unless the binary under test is OpenTofu 1.7+ - the CI
job that installs OpenTofu aliases it as ``terraform``, so the version banner is
what distinguishes them, not the name.
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

#: `terraform_data` is built in, so this needs no provider download - which
#: matters because the point here is the encryption, not the resources.
CONFIG = """
resource "terraform_data" "secret" {
  input = "s3cr3t-value-in-state"
}

resource "terraform_data" "ordinary" {
  input = "plain"
}
"""

PASSPHRASE = "correct-horse-battery-staple-1234"

ENCRYPTION = f"""
key_provider "pbkdf2" "test" {{
  passphrase = "{PASSPHRASE}"
}}
method "aes_gcm" "test" {{
  keys = key_provider.pbkdf2.test
}}
state {{
  method = method.aes_gcm.test
  enforced = true
}}
"""


def _opentofu_version() -> tuple[int, int] | None:
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
    return (int(match.group(1)), int(match.group(2))) if match else None


_VERSION = _opentofu_version()

requires_encryption = pytest.mark.skipif(
    _VERSION is None or _VERSION < (1, 7),
    reason="needs OpenTofu 1.7+, which supports state encryption",
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    directory = tmp_path / "encrypted"
    directory.mkdir()
    (directory / "main.tf").write_text(CONFIG, encoding="utf-8")
    return directory


@pytest.fixture
def encrypted(project: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An applied project whose state on disk is genuinely encrypted."""
    monkeypatch.setenv("TF_ENCRYPTION", ENCRYPTION)
    for args in (
        ("init", "-no-color", "-input=false"),
        ("apply", "-auto-approve", "-no-color"),
    ):
        subprocess.run(
            [TerraformExecutor("terraform").path, *args],
            cwd=project,
            capture_output=True,
            check=True,
            timeout=300,
        )
    return project


@requires_encryption
def test_the_state_on_disk_really_is_encrypted(encrypted: Path) -> None:
    """Guards the rest of this file: without it they could pass on plaintext."""
    raw = (encrypted / "terraform.tfstate").read_text(encoding="utf-8")

    assert "s3cr3t-value-in-state" not in raw
    assert "terraform_data" not in raw
    assert "encrypted_data" in raw or "meta" in raw


@requires_encryption
async def test_tftui_reads_an_encrypted_state(encrypted: Path) -> None:
    """The whole of issue #90: no support needed, the environment carries the key."""
    client = TerraformClient(TerraformExecutor("terraform", cwd=encrypted))
    loaded = await client.load_state()

    assert "terraform_data.secret" in loaded.state.resources
    assert "terraform_data.ordinary" in loaded.state.resources
    assert "s3cr3t-value-in-state" in loaded.state.resources["terraform_data.secret"].body
    client.cleanup()


@requires_encryption
async def test_without_the_key_the_failure_is_reported_not_swallowed(
    encrypted: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The negative half: proves the previous test passes *because* of the key.

    It also pins the behaviour someone hitting this for real would see - a
    reported error, not an empty tree that looks like a missing state.
    """
    monkeypatch.delenv("TF_ENCRYPTION")
    client = TerraformClient(TerraformExecutor("terraform", cwd=encrypted))

    with pytest.raises(TftuiError, match=r"(?i)encrypt"):
        await client.load_state()

    client.cleanup()
