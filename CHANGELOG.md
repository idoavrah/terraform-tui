# Changelog

## 0.14.0

A full rewrite. Same application, same keys, same flags — new internals.

Still a 0.x release: the internals are new enough to want real-world mileage
before anything is called 1.0.

### Fixed

- **Tainted resources are shown again.** Terraform writes the taint marker after
  the colon (`# address: (tainted)`); it is now parsed there.
- **`R` refreshes the state.** The binding pointed at a method that was not an
  action handler, so the key did nothing.
- **Typing in the search box no longer moves the tree cursor.** `j` and `k` were
  handled application-wide, so searching for `jupiter` scrolled the tree. Vim
  keys are now bindings on the tree widget, active only when it has focus.
- **Plan and resource output re-wraps when the terminal is resized.** Each line
  was wrapped once, at the width in effect when it was written, and never
  re-wrapped afterwards. Output written before its pane had been laid out fell
  back to an 80-column default, which mangled long resource addresses.
- **Terraform's root outputs are no longer discarded** when parsing state.
- **`terraform init` actually runs** on startup unless `-n` is passed. The flag
  was read but never acted on.
- **Sensitive values are matched to attributes by name.** Substitution used to be
  positional, which could not distinguish one redacted attribute from another.
- **Only genuinely sensitive attributes are treated as secrets.** Attributes that
  Terraform lists with a `false` sensitivity flag were previously included.
- **Selections survive a search or a refresh.** They were held as tree-node
  objects, which are discarded whenever the tree is rebuilt; they are now held
  as resource addresses.
- **Listing workspaces no longer crashes** when `terraform workspace list` fails.
- **A crash on startup at certain terminal sizes is gone** ([#92]). The old
  resize handler touched a widget before it was assigned; layout is now CSS.
- **File content that looks like a block header no longer breaks parsing**
  ([#91], thanks to @RafaelWO for finding and diagnosing it). A header must now
  match `# <address>:` anchored at both ends, so a binary blob in a
  `data.local_file` cannot be mistaken for one.
- **Runs on current Textual.** The application used APIs removed in Textual 1.0.

### Security

- Terraform is never invoked through a shell, and arguments are never re-split
  on whitespace. Resource addresses containing spaces, quotes or `$` are passed
  through verbatim.
- The `--executable` value is validated against a conservative pattern and
  resolved with `shutil.which`, so it cannot smuggle in shell syntax.
- **Plan files are written to a private temporary directory** (mode `0700`) and
  removed when superseded, applied, or on exit. Previously `tftui.plan` was
  written into the working directory, where a plan — which embeds resource
  attributes, including sensitive ones — could be committed by accident.
- A plan is discarded once applied, so a stale plan cannot be reapplied against
  a state that has moved on.
- Usage tracking runs on a background thread, cannot block the UI, and cannot
  propagate an exception into the application.
- Terraform runs with `TF_INPUT=0` and closed stdin, so it can never prompt for
  input behind the UI.

### Changed

- Destructive confirmations now default to **No**.
- Data sources are dimmed and cannot be selected — taint, untaint and remove do
  not apply to them.
- Resources are rendered with HCL syntax highlighting.
- The help screen is grouped by task.
- The plan pane clears Terraform's refresh preamble once the plan proper begins.
- The state tree root shows resource, data-source and tainted counts.
- The layout is expressed in CSS rather than recomputed on every resize event.

### Added

- **Space on a module selects every resource under it** ([#82]). Expanding and
  collapsing moved to Enter, the arrow keys and the digit keys. The selection
  count now appears on the pane border.
- **`/` searches the plan and the resource view** ([#89]), highlighting matches
  in place rather than filtering, since a diff or a definition is meaningless
  without its context. `n` and `N` step through matches, and the title shows the
  position. The tree keeps filtering, as before.
- **`-f` / `--var-file` may be repeated** ([#62], [#85]), applied in order. The
  files are passed to `init` as well as to `plan`, which is what OpenTofu 1.8+
  needs to evaluate variables used in a `backend` block. `TFTUI_VAR_FILE` takes
  a list separated by the platform path separator.
- Every flag can now be set through a `TFTUI_*` environment variable.
- `-C` / `--chdir` to run against another directory.
- `Ctrl+A` clears the current selection.
- Search is case-insensitive.

### Release process

Pushing to `main` now publishes, but only when the version in `pyproject.toml`
is absent from PyPI *and* newer than everything published there. The workflow
runs the full suite, publishes to TestPyPI then PyPI through trusted
publishing, and creates the tag and GitHub release with notes taken from this
file. Any other state - an unchanged version, a revert, a downgrade, or PyPI
being unreachable - skips the pipeline. `scripts/should_release.py` makes that
call and is unit tested.

### Internals

- `src/` layout, PEP 621 metadata, hatchling build backend, uv lockfile.
- Python 3.10+ (3.9 is end of life). Textual 8, and `requests` is no longer a
  dependency — the update check uses the standard library.
- Terraform integration is separated from the UI: parsing and plan colouring are
  pure functions with no Textual import, and widgets never build argv.
- 369 tests: unit, end-to-end through Textual's `Pilot`, and an integration suite
  driving a real Terraform binary against a bundled example project.
- CI across Linux, macOS and Windows on Python 3.10–3.13, plus integration runs
  against both Terraform and OpenTofu.
- `mypy --strict` and `ruff` clean.

### Compatibility

Every keybinding and command-line flag from 0.13 is preserved. The two-word
handle used for usage tracking is derived exactly as before, so returning users
keep their identity.

[#62]: https://github.com/idoavrah/terraform-tui/issues/62
[#82]: https://github.com/idoavrah/terraform-tui/issues/82
[#85]: https://github.com/idoavrah/terraform-tui/issues/85
[#89]: https://github.com/idoavrah/terraform-tui/issues/89
[#91]: https://github.com/idoavrah/terraform-tui/pull/91
[#92]: https://github.com/idoavrah/terraform-tui/issues/92

---

## 0.13

- Added support for workspace switching
- Added plan summary in the screen title
- Empty tree is now shown when no state exists instead of the program shutting down
- Added `-o` flag for offline mode (no outbound API calls)
- Removed the default outbound call to PostHog when tracking is disabled
- Added sensitive values extraction in resource details
- Added support for vim-like navigation

## 0.12

- Enabled targeting specific resources for plan creation
- Introduced cli argument: tfvars file
- Added destroy functionality
- Added a help screen
- Added dynamic value for "targets" checkbox
- Added a short summary of the suggested plan before applying it
- Added a redacted error tracker on unhandled exceptions
- Added a fullscreen mode to allow easier copying of resource / plan parts
- Fixed: search through full module names
- Fixed: copy to clipboard crashes on some systems

## 0.11

- Added support for creating plans (in vivid colors!) and applying them
- Changed the confirmation dialog to a modal screen
- Added coloring to tainted resources
- Improved loading screen mechanism
