"""Config files, and the precedence order they sit at the bottom of.

The ordering is the whole point of the feature and the easiest thing to break,
so it is tested from both ends: a file must not override a flag, and a flag's
*absence* must not override a file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tftui import config_file
from tftui.cli import resolve
from tftui.config import Settings


# An environment with none of the TFTUI_* variables set, so tests are not at the
# mercy of the shell they run under. XDG_CONFIG_HOME points somewhere empty by
# default, which keeps the developer's own config file out of the results.
def _env(tmp_path: Path, **extra: str) -> dict[str, str]:
    return {"XDG_CONFIG_HOME": str(tmp_path / "xdg"), **extra}


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


# ------------------------------------------------------------------ locations


def test_user_config_honours_xdg_config_home() -> None:
    path = config_file.user_config_path({"XDG_CONFIG_HOME": "/somewhere"})
    assert path == Path("/somewhere/tftui/config.toml")


def test_user_config_falls_back_to_dot_config() -> None:
    path = config_file.user_config_path({})
    assert path == Path.home() / ".config" / "tftui" / "config.toml"


def test_project_config_sits_beside_the_terraform_files() -> None:
    assert config_file.project_config_path(Path("/work")) == Path("/work/.tftui.toml")


# --------------------------------------------------------------------- values


def test_missing_files_are_not_an_error(tmp_path: Path) -> None:
    """Neither file is required, and absence must be silent."""
    loaded = config_file.load(working_dir=tmp_path, env=_env(tmp_path))
    assert loaded.values == {}
    assert loaded.warnings == ()
    assert loaded.sources == ()


def test_reads_every_setting(tmp_path: Path) -> None:
    _write(
        tmp_path / ".tftui.toml",
        """
        executable = "tofu"
        var-file = ["common.tfvars", "prod.tfvars"]
        no-init = true
        offline = true
        disable-usage-tracking = true
        light-mode = true
        generate-debug-log = true
        """,
    )
    loaded = config_file.load(working_dir=tmp_path, env=_env(tmp_path))

    assert loaded.values == {
        "executable": "tofu",
        "var_files": ("common.tfvars", "prod.tfvars"),
        "run_init": False,
        "offline": True,
        "usage_tracking": False,
        "light_mode": True,
        "debug_log": True,
    }
    assert loaded.warnings == ()


def test_snake_case_keys_are_accepted(tmp_path: Path) -> None:
    """TOML users reach for underscores; both spellings mean the same thing."""
    _write(tmp_path / ".tftui.toml", 'var_file = "x.tfvars"\nno_init = true\n')
    loaded = config_file.load(working_dir=tmp_path, env=_env(tmp_path))

    assert loaded.values == {"var_files": ("x.tfvars",), "run_init": False}
    assert loaded.warnings == ()


def test_a_single_var_file_may_be_a_bare_string(tmp_path: Path) -> None:
    _write(tmp_path / ".tftui.toml", 'var-file = "only.tfvars"')
    loaded = config_file.load(working_dir=tmp_path, env=_env(tmp_path))
    assert loaded.values["var_files"] == ("only.tfvars",)


def test_project_file_overrides_user_file(tmp_path: Path) -> None:
    _write(tmp_path / "xdg" / "tftui" / "config.toml", 'executable = "tofu"\nlight-mode = true\n')
    _write(tmp_path / ".tftui.toml", 'executable = "terragrunt"')
    loaded = config_file.load(working_dir=tmp_path, env=_env(tmp_path))

    assert loaded.values["executable"] == "terragrunt"
    assert loaded.values["light_mode"] is True  # untouched by the project file
    assert len(loaded.sources) == 2


# ------------------------------------------------------------------- warnings


def test_unknown_key_is_reported(tmp_path: Path) -> None:
    """A typo would otherwise do nothing at all, with nothing to say why."""
    _write(tmp_path / ".tftui.toml", 'excutable = "tofu"')
    loaded = config_file.load(working_dir=tmp_path, env=_env(tmp_path))

    assert loaded.values == {}
    assert len(loaded.warnings) == 1
    assert "excutable" in loaded.warnings[0]


def test_broken_toml_is_reported_and_does_not_raise(tmp_path: Path) -> None:
    """A broken config file must not make tftui unusable."""
    _write(tmp_path / ".tftui.toml", "executable = tofu")  # unquoted
    loaded = config_file.load(working_dir=tmp_path, env=_env(tmp_path))

    assert loaded.values == {}
    assert "not valid TOML" in loaded.warnings[0]


@pytest.mark.parametrize(
    ("body", "fragment"),
    [
        ("no-init = 1", "true or false"),
        ('offline = "yes"', "true or false"),
        ("var-file = 3", "list of strings"),
        ("var-file = [1, 2]", "list of strings"),
        ('executable = ""', "non-empty string"),
        ("executable = true", "non-empty string"),
    ],
)
def test_wrong_types_are_reported(tmp_path: Path, body: str, fragment: str) -> None:
    _write(tmp_path / ".tftui.toml", body)
    loaded = config_file.load(working_dir=tmp_path, env=_env(tmp_path))

    assert loaded.values == {}
    assert fragment in loaded.warnings[0]


def test_chdir_is_rejected_in_a_project_file(tmp_path: Path) -> None:
    """It would be circular: the file is found because the directory is known."""
    _write(tmp_path / ".tftui.toml", 'chdir = "/elsewhere"')
    loaded = config_file.load(working_dir=tmp_path, env=_env(tmp_path))

    assert loaded.values == {}
    assert "user config file" in loaded.warnings[0]


def test_chdir_is_accepted_in_the_user_file(tmp_path: Path) -> None:
    _write(tmp_path / "xdg" / "tftui" / "config.toml", 'chdir = "/work"')
    loaded = config_file.load(working_dir=tmp_path, env=_env(tmp_path))
    assert loaded.values == {"working_dir": Path("/work")}


# ----------------------------------------------------------------- precedence


def test_config_file_beats_the_defaults(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write(tmp_path / ".tftui.toml", 'executable = "tofu"\nno-init = true\n')

    settings, _, warnings = resolve([], env=_env(tmp_path))

    assert settings.executable == "tofu"
    assert settings.run_init is False
    assert warnings == ()


def test_environment_beats_the_config_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write(tmp_path / ".tftui.toml", 'executable = "tofu"')

    settings, _, _ = resolve([], env=_env(tmp_path, TFTUI_EXECUTABLE="terragrunt"))

    assert settings.executable == "terragrunt"


def test_a_flag_beats_both(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write(tmp_path / ".tftui.toml", 'executable = "tofu"')

    settings, _, _ = resolve(["-e", "flagged"], env=_env(tmp_path, TFTUI_EXECUTABLE="terragrunt"))

    assert settings.executable == "flagged"


def test_an_unpassed_flag_does_not_override_the_file(tmp_path: Path, monkeypatch) -> None:
    """The regression this whole layering exists to prevent.

    Boolean flags default to None rather than False so that "not passed" can be
    told from "passed"; were they False, every run would silently reset the
    file's `no-init`, `offline` and `light-mode` back to their defaults.
    """
    monkeypatch.chdir(tmp_path)
    _write(
        tmp_path / ".tftui.toml",
        "no-init = true\noffline = true\nlight-mode = true\ndisable-usage-tracking = true\n",
    )

    settings, _, _ = resolve([], env=_env(tmp_path))

    assert settings.run_init is False
    assert settings.offline is True
    assert settings.light_mode is True
    assert settings.usage_tracking is False


def test_the_project_file_is_read_from_the_chdir_target(tmp_path: Path, monkeypatch) -> None:
    """`-C` decides where the project file is looked for, not the shell's cwd."""
    elsewhere = tmp_path / "project"
    _write(elsewhere / ".tftui.toml", 'executable = "tofu"')
    _write(tmp_path / ".tftui.toml", 'executable = "should-not-win"')
    monkeypatch.chdir(tmp_path)

    settings, _, _ = resolve(["-C", str(elsewhere)], env=_env(tmp_path))

    assert settings.executable == "tofu"
    assert settings.working_dir == elsewhere


def test_no_config_file_leaves_defaults_intact(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    settings, _, warnings = resolve([], env=_env(tmp_path))

    assert settings == Settings()
    assert warnings == ()
