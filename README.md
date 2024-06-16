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
- [x] Operate on resources: taint, untaint, delete, destroy
- [x] Support for Terraform wrappers (e.g. terragrunt)

## Changelog (latest versions)

### Version 0.13

- [x] Added support for workspace switching
- [x] Added plan summary in the screen title
- [x] Empty tree is now shown when no state exists instead of program shutting down, allowing for plan creation
- [x] Added `-o` flag for offline mode (no outbound API calls)
- [x] Removed the default outbound call to PostHog when tracking is disabled
- [x] Added sensitive values extraction in resource details
- [x] Added support for vim-like navigation

### Version 0.12

- [x] Enabled targeting specific resources for plan creation
- [x] Introducing cli argument: tfvars file
- [x] Added destroy functionality
- [x] Added a help screen
- [x] Added dynamic value for "targets" checkbox (checkbox is marked when resources are selected)
- [x] Added a short summary of the suggested plan before applying it
- [x] Added a redacted error tracker on unhandeled exceptions (only when usage reporting is enabled)
- [x] Added a fullscreen mode to allow easier copying of resource / plan parts
- [x] Fixed: search through full module names
- [x] Fixed: Copy to clipboard crashes on some systems

### Version 0.11

- [x] Added support for creating plans (in vivid colors!) and applying them
- [x] Changed the confirmation dialog to a modal screen
- [x] Added coloring to tainted resources considering some terminals can't display strikethrough correctly
- [x] Improved loading screen mechanism

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
