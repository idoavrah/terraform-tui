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
- Do not commit `examples/terraform/.terraform.lock.hcl`. Provider versions are
  already pinned exactly in the configuration, and a lock file only carries
  checksums for the platforms and provider source it was generated against — a
  committed one breaks `terraform init` for everyone else.

## Releasing

Releases are driven by the version in `pyproject.toml`. There is no tagging
step to remember and no release to create by hand.

1. Bump `version` in `pyproject.toml` and add the matching `## <version>`
   section to `CHANGELOG.md`. `cz bump` does both.
2. Merge to `main`.

Every push to `main` runs the release workflow, which starts by asking
`scripts/should_release.py` whether this version should ship. It ships only if
the version is **not already on PyPI** *and* is **newer than everything
published**. Any other answer — an unchanged version, a revert, a downgrade, or
PyPI being unreachable — skips the whole pipeline after one cheap job.

When it does ship, the workflow:

1. runs lint, types and the full test suite, including the Terraform integration tests;
2. builds, checks the metadata, and confirms the installed wheel reports the expected version;
3. publishes to TestPyPI, then to PyPI, via trusted publishing (no stored tokens);
4. creates the `v<version>` tag and a GitHub release, with notes taken from that
   version's `CHANGELOG.md` section, attaching the wheel and sdist.

A filename on PyPI and TestPyPI is spent for good — it cannot be replaced, and
deleting the release does not free it. The TestPyPI upload therefore uses
`skip-existing`, so re-running a release for the same commit does not fail on
files already there. Because that flag cannot tell an identical file from a
*rebuilt* one claiming the same name, `scripts/check_testpypi.py` compares
digests first: identical is fine, different stops the release and tells you to
bump the version. So if you rework a version after it has reached TestPyPI,
bump it rather than re-pushing — otherwise TestPyPI keeps serving the older
build.

The steps are ordered so nothing is tagged that was not published, and nothing
is published that did not pass its tests.

**The human gate is a repository setting, not part of this file.** The PyPI
publish targets the `production` GitHub environment; if that environment has
*Required reviewers* configured (Settings → Environments → production), the run
pauses there until someone approves, and the tag and GitHub release — which come
after it — wait too. Without that rule, merging publishes straight through.
Check the setting rather than assuming either way.

Run the workflow manually with **dry run** ticked to see what it would decide
and build without publishing anything.

`major_version_zero` is set for commitizen, so a breaking change bumps the
minor version. Going to 1.0 is a deliberate act, not something a `feat!:`
commit does on its own.

## Debugging the UI

Textual's devtools are in the dev dependency group:

```bash
uv run textual console          # in one terminal
# in another, with TEXTUAL=devtools set:
cd examples/terraform && TEXTUAL=devtools uv run --project ../.. tftui -o -n
```

`tftui -g` writes a verbose `tftui.log` next to your Terraform files, which
records every command executed and its exit code.
