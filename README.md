# TFTUI - The Terraform textual UI

[![PyPI version](https://badge.fury.io/py/tftui.svg?random=stuff)](https://badge.fury.io/py/tftui?)
![GitHub](https://img.shields.io/github/license/idoavrah/terraform-tui?random=stuff)
![PyPI - Downloads](https://img.shields.io/pypi/dm/tftui?random=stuff)

`TFTUI` is a powerful textual UI that empowers users to effortlessly view and interact with their Terraform state.

With its latest version you can easily visualize the complete state tree, gaining deeper insights into your infrastructure's current configuration. Additionally, the ability to search the tree and inspect individual resource states allows you to focus on specific details for better analysis and management. It's also possible to select specific resources and perform actions such as tainting, untainting and deleting them. Finally, you are now able to create and apply plans directly from the UI.

## Key Features

- [x] Comprehensive display of the entire Terraform state tree
- [x] Effortlessly view and navigate through a single resource state
- [x] Search the state tree and resource definitions
- [x] Create plans, present them in full colors and apply them directly from the TUI
- [x] Single/multiple resource selection
- [x] Operate on resources: taint, untaint, delete
- [x] Support for Terraform wrappers (e.g. terragrunt)

## Changelog (last two versions)

### Version 0.11

- [x] Added support for creating plans (in vivid colors!) and applying them
- [x] Changed the confirmation dialog to a modal screen
- [x] Added coloring to tainted resources considering some terminals can't display strikethrough correctly
- [x] Improved loading screen mechanism

### Version 0.10

- [x] Perform actions on a single highlighted resource without pre-selecting it
- [x] User interface overhaul: added logo, fixed coloring and loading indicator
- [x] Added resource selection via the space key and tree traversal via the arrow keys
- [x] Added a lightmode command-line argument
- [x] Added a debug log command-line argument
- [x] Copy to clipboard now copies the resource name in the tree view
- [x] Fixed a bug in the remove resource functionality
- [x] Fixed a bug in the parsing mechanism (colons, dots)
- [x] Refactor: globals

## Demo

![](demo/tftui.gif "demo")

## Installation

| Tool     | Install                                | Upgrade                       | Run                                      |
| -------- | -------------------------------------- | ----------------------------- | ---------------------------------------- |
| Homebrew | `brew install idoavrah/homebrew/tftui` | `brew upgrade tftui`          | `cd /path/to/terraform/project && tftui` |
| PIP      | `pip install tftui`                    | `pip install --upgrade tftui` | `cd /path/to/terraform/project && tftui` |
| PIPX     | `pipx install tftui`                   | `pipx upgrade tftui`          | `cd /path/to/terraform/project && tftui` |

## Usage Tracking

- TFTUI utilizes [PostHog](https://posthog.com) to track usage of the application.
- This is done to help us understand how the tool is being used and to improve it.
- No personal data is being sent to the tracking service. Returning users are being uniquely identified by a generated fingerprint.
- You can opt-out of usage tracking completely by setting the `-d` flag when running the tool.

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=idoavrah/terraform-tui&type=Date)](https://star-history.com/#idoavrah/terraform-tui&Date)
