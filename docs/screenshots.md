# Screenshots

Every image here is a real render of the application, captured headlessly
against the bundled example project by `scripts/capture-screenshots.py`.
Regenerate them with `make screenshots`.

## The state tree

Modules nest as they do in your configuration. Data sources are dimmed, tainted
resources are struck through, and the root shows what the state contains.

![The state tree](screenshots/01-state-tree.svg)

## A single resource

Rendered with HCL syntax highlighting.

![A single resource](screenshots/02-resource-view.svg)

## Revealing sensitive values

Sensitive attributes stay redacted until you press `X`, and are then matched to
their attributes by name.

![Sensitive values revealed](screenshots/03-sensitive-revealed.svg)

## Filtering

`/` filters on text in resource names *and* their definitions. Modules with no
surviving children are pruned. In a resource or a plan the same key highlights
matches in place instead of filtering, since a definition or a diff means little
without its surrounding context; `n` and `N` step through them.

![Filtering the tree](screenshots/04-search.svg)

## Help

![The help screen](screenshots/05-help.svg)

## Acting on resources

Select with `Space`, then taint, untaint or remove from state. The confirmation
defaults to *No*.

![Confirming a taint](screenshots/06-selection-and-confirm.svg)

## Planning

![Plan options](screenshots/07-plan-dialog.svg)

![A colourised plan](screenshots/08-plan.svg)

## Workspaces

![Switching workspace](screenshots/09-workspaces.svg)
