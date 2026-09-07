"""Multiple var-files: issues #85 (OpenTofu backend variables) and #62."""

from __future__ import annotations

import os

import pytest

from tftui.cli import parse_args
from tftui.config import Settings, split_var_files
from tftui.terraform.client import TerraformClient
from tftui.terraform.executor import var_file_args


def test_var_file_args_preserve_order() -> None:
    """Terraform lets a later file override an earlier one, so order matters."""
    files = ["common.tfvars", "prod.tfvars"]
    assert var_file_args(files) == ["-var-file=common.tfvars", "-var-file=prod.tfvars"]


def test_var_file_args_are_separate_argv_entries() -> None:
    args = var_file_args(["a file.tfvars", 'quo"te.tfvars'])
    assert len(args) == 2
    assert args[0] == "-var-file=a file.tfvars"


def test_no_var_files_adds_nothing() -> None:
    assert var_file_args([]) == []


# --------------------------------------------------------------------- CLI


def test_repeated_flag_collects_every_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TFTUI_VAR_FILE", raising=False)
    settings, _ = parse_args(["-f", "common.tfvars", "-f", "prod.tfvars"])
    assert settings.var_files == ("common.tfvars", "prod.tfvars")


def test_single_flag_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TFTUI_VAR_FILE", raising=False)
    settings, _ = parse_args(["--var-file", "prod.tfvars"])
    assert settings.var_files == ("prod.tfvars",)


def test_no_flag_means_no_var_files(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TFTUI_VAR_FILE", raising=False)
    settings, _ = parse_args([])
    assert settings.var_files == ()


# --------------------------------------------------------------------- env


def test_env_accepts_a_list() -> None:
    value = os.pathsep.join(["a.tfvars", "b.tfvars"])
    assert Settings.from_env({"TFTUI_VAR_FILE": value}).var_files == ("a.tfvars", "b.tfvars")


@pytest.mark.parametrize("value", ["", None, os.pathsep, f" {os.pathsep} "])
def test_env_ignores_empty_entries(value: str | None) -> None:
    assert split_var_files(value) == ()


def test_flags_beat_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TFTUI_VAR_FILE", "from-env.tfvars")
    settings, _ = parse_args(["-f", "from-flag.tfvars"])
    assert settings.var_files == ("from-flag.tfvars",)


# ------------------------------------------------------------------ client


async def test_plan_passes_every_var_file(client: TerraformClient, stub) -> None:
    _ = [line async for line in client.plan(var_files=["common.tfvars", "prod.tfvars"])]
    call = stub.calls[-1]
    assert "-var-file=common.tfvars" in call
    assert "-var-file=prod.tfvars" in call


async def test_init_receives_var_files(client: TerraformClient, stub) -> None:
    """OpenTofu needs them at init time to evaluate a backend block (#85)."""
    await client.init(var_files=["backend.tfvars"])
    call = stub.calls[-1]
    assert call[0] == "init"
    assert "-var-file=backend.tfvars" in call


async def test_init_without_var_files_passes_none(client: TerraformClient, stub) -> None:
    await client.init()
    assert not [arg for arg in stub.calls[-1] if arg.startswith("-var-file")]
