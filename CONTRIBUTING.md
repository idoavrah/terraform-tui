# Contributing

## Getting set up

You need [uv](https://docs.astral.sh/uv/) and a `terraform` binary. If you do
not have Terraform, `scripts/bootstrap-terraform.sh` installs a pinned version
(with checksum verification).

```bash
make setup      # dependencies + pre-commit hooks
make check      # what CI runs on a pull request
```

`make help` lists everything else.

## Running it

The repository ships a self-contained Terraform project under
`examples/terraform`. It uses only the `random`, `local` and `time` providers,
so applying it creates nothing outside that directory.

```bash
make example-apply   # create real state to browse
make run             # launch tftui against it
make example-clean   # tear it back down
```

## Layout

```
src/tftui/
├── __main__.py        entry point: wires settings, logging, telemetry, client
├── cli.py             argument parsing
├── config.py          Settings, resolved from defaults + env + flags
├── errors.py          the exception hierarchy the UI knows how to render
├── logging_setup.py   logging (silent unless -g is passed)
├── telemetry.py       opt-out usage tracking and the update check
├── app.py             the Textual application: bindings and orchestration
├── terraform/         everything that knows what Terraform is
│   ├── executor.py    async subprocess execution (no shell, ever)
│   ├── address.py     resource address parsing
│   ├── state.py       the state model and its parser
│   ├── plan.py        plan colourising and summarising (pure, no Textual)
│   └── client.py      high-level operations the UI calls
├── widgets/           state tree, resource view, plan view, header
└── screens/           modal dialogs
```

The rule that keeps this testable: **`terraform/` never imports Textual, and
`widgets/`/`screens/` never build argv.** Parsing and colouring are pure
functions over strings, so they are unit tested directly; the widgets are thin
enough that driving them with Textual's `Pilot` covers the rest.

## Tests

| Command                 | What it covers                                          |
| ----------------------- | ------------------------------------------------------- |
| `make test`             | Unit + end-to-end. No Terraform binary needed. ~25s      |
| `make test-integration` | Drives a real `terraform` against `examples/terraform`   |
| `make coverage`         | The above with an HTML coverage report                   |

Unit and end-to-end tests run against output captured from a real
`terraform show` in `tests/fixtures/`. They never shell out, so they are fast
and deterministic.

End-to-end tests build the *real* `TerraformClient` over a stub executor, so
they exercise the client, the parsers, the widgets and the keybindings
together — only the subprocess is faked.

### Regenerating fixtures

Needed when you change `examples/terraform`, or when a new Terraform release
changes the shape of `terraform show`:

```bash
make fixtures
```

Review the resulting diff: several tests assert on resource counts taken from
these files, and the script prints a reminder to that effect.

## Conventions

- Commits follow [Conventional Commits](https://www.conventionalcommits.org/);
  `commitizen` enforces this via pre-commit.
- `ruff` handles linting and formatting; `mypy --strict` must pass.
- Never introduce a shell into the Terraform call path. Arguments are passed as
  a list, and resource addresses are passed verbatim.
- Anything that could write a secret to disk belongs in a private temporary
  directory, not the user's working directory.

## Releasing

1. `cz bump` — updates the version in `pyproject.toml` and `CHANGELOG.md`, and tags.
2. Push the tag and create a GitHub release.
3. The release workflow builds, verifies the tag matches the packaged version,
   publishes to TestPyPI, then to PyPI via trusted publishing (no stored tokens).

## Debugging the UI

Textual's devtools are in the dev dependency group:

```bash
uv run textual console          # in one terminal
# in another, with TEXTUAL=devtools set:
cd examples/terraform && TEXTUAL=devtools uv run --project ../.. tftui -o -n
```

`tftui -g` writes a verbose `tftui.log` next to your Terraform files, which
records every command executed and its exit code.
