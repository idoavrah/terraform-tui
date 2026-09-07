# TFTUI — the Terraform textual UI

[![PyPI version](https://badge.fury.io/py/tftui.svg?random=stuff)](https://badge.fury.io/py/tftui?)
[![CI](https://github.com/idoavrah/terraform-tui/actions/workflows/ci.yaml/badge.svg)](https://github.com/idoavrah/terraform-tui/actions/workflows/ci.yaml)
![GitHub](https://img.shields.io/github/license/idoavrah/terraform-tui?random=stuff)
![PyPI - Downloads](https://img.shields.io/pypi/dm/tftui?random=stuff)

`TFTUI` is a terminal UI for viewing and working with your Terraform state.

Browse the full state tree, search it, read individual resources, reveal
sensitive values, taint or remove resources, and create and apply plans —
without leaving the terminal.

![The state tree](docs/screenshots/01-state-tree.svg)

More screenshots: [docs/screenshots.md](docs/screenshots.md). The animated
[demo](demo/tftui.gif) still shows the 0.13 interface and is due a re-record.

## Features

- Full state tree, with modules nested as they are in your configuration
- Search across resource names *and* their definitions
- Read a single resource with HCL syntax highlighting
- Reveal sensitive values on demand
- Select one resource, or a whole module at a time, and taint, untaint or remove from state
- Create plans — including targeted and destroy plans — in full colour, search them, and apply them
- Switch workspaces without restarting
- Works with Terraform, OpenTofu and wrappers such as Terragrunt

## Installation

| Tool     | Install                                | Upgrade                       | Run                                      |
| -------- | -------------------------------------- | ----------------------------- | ---------------------------------------- |
| Homebrew | `brew install idoavrah/homebrew/tftui` | `brew upgrade tftui`          | `cd /path/to/terraform/project && tftui` |
| pipx     | `pipx install tftui`                   | `pipx upgrade tftui`          | `cd /path/to/terraform/project && tftui` |
| uv       | `uv tool install tftui`                | `uv tool upgrade tftui`       | `cd /path/to/terraform/project && tftui` |
| pip      | `pip install tftui`                    | `pip install --upgrade tftui` | `cd /path/to/terraform/project && tftui` |

Requires Python 3.10 or newer and a `terraform` (or compatible) binary on `PATH`.

## Keys

Press `?` in the application for the full list.

| Key         | Action                                                       |
| ----------- | ------------------------------------------------------------ |
| `↑ ↓ / j k` | Move up and down                                             |
| `← → / h l` | Collapse and expand, or step in and out                      |
| `Enter`     | View the resource, or expand the module                       |
| `Esc`       | Back to the state tree                                       |
| `/`         | Filter the tree, or search within a plan                      |
| `n` `N`     | Next / previous match when searching a plan                   |
| `0`–`9`     | Collapse the tree to a module depth (`0` expands everything) |
| `Space`     | Select the resource — or, on a module, everything under it    |
| `Ctrl+A`    | Clear the selection                                          |
| `T` `U` `D` | Taint, untaint, or remove from state                         |
| `P`         | Create a plan                                                |
| `Ctrl+D`    | Create a destruction plan                                    |
| `A`         | Apply the current plan                                       |
| `X`         | Reveal sensitive values                                      |
| `F`         | Full screen (hold Shift or Option to select text)            |
| `C`         | Copy to clipboard                                            |
| `R`         | Refresh state                                                |
| `W`         | Switch workspace                                             |
| `M`         | Toggle light and dark mode                                   |
| `Q`         | Quit                                                         |

## Configuration

Every option can be set with a flag or an environment variable. Flags win.

| Flag                             | Environment variable           | Meaning                                       |
| -------------------------------- | ------------------------------ | --------------------------------------------- |
| `-e`, `--executable`             | `TFTUI_EXECUTABLE`             | Binary to drive (default `terraform`)         |
| `-f`, `--var-file`               | `TFTUI_VAR_FILE`               | tfvars file; repeat the flag for several      |
| `-C`, `--chdir`                  | `TFTUI_WORKING_DIR`            | Directory to run in (default current)         |
| `-n`, `--no-init`                | `TFTUI_NO_INIT`                | Skip `terraform init` on startup              |
| `-o`, `--offline`                | `TFTUI_OFFLINE`                | No outbound calls at all                      |
| `-d`, `--disable-usage-tracking` | `TFTUI_DISABLE_USAGE_TRACKING` | Turn off usage tracking                       |
| `-l`, `--light-mode`             | `TFTUI_LIGHT_MODE`             | Start in the light theme                      |
| `-g`, `--generate-debug-log`     | `TFTUI_DEBUG_LOG`              | Write `tftui.log` in the working directory    |
| `-v`, `--version`                | —                              | Print the version and exit                    |

### Several var-files

Repeat `-f` as often as you need; the files are applied in order, so a later
one overrides an earlier one. They are passed to `init` as well as to `plan`,
which is what OpenTofu 1.8+ needs to evaluate variables used in a `backend`
block.

```bash
tftui -f common.tfvars -f prod.tfvars
```

The environment variable takes a list separated by your platform's path
separator (`:` on Linux and macOS, `;` on Windows):

```bash
export TFTUI_VAR_FILE="common.tfvars:prod.tfvars"
```

### Using OpenTofu or Terragrunt

```bash
tftui --executable tofu
tftui --executable terragrunt
```

## Handling of sensitive data

Terraform state routinely contains secrets, so tftui is deliberate about them:

- Sensitive attributes stay redacted as `(sensitive value)` until you press `X`.
- When revealed, values are matched to attributes **by name**, so one secret can
  never be displayed under another attribute's label.
- Plan files are written to a private temporary directory (mode `0700`) and
  deleted when the plan is superseded, applied, or the program exits. They are
  never written into your Terraform directory, where they could be committed by
  accident.
- A plan is discarded once applied, so a stale plan cannot be applied twice.
- tftui never invokes a shell. Terraform is executed directly with an argument
  list, so resource addresses containing quotes, spaces or `$` are safe.

## Usage tracking

- tftui uses [PostHog](https://posthog.com) to understand how the tool is used.
- No personal data is sent. Returning users are identified by a two-word handle
  derived from a one-way hash of the machine name.
- Crash reports have directory names stripped out before they are sent.
- Tracking never blocks the UI and never takes the application down.
- Opt out with `-d`, or turn off every outbound call — tracking and the update
  check alike — with `-o`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). In short:

```bash
make setup     # install dependencies and git hooks
make check     # lint, type-check and test
make run       # run against the bundled example project
```

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## Star history

[![Star History Chart](https://api.star-history.com/svg?repos=idoavrah/terraform-tui&type=Date)](https://star-history.com/#idoavrah/terraform-tui&Date)
