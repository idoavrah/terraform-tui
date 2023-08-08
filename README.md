# TFTUI - The Terraform textual UI

[![PyPI version](https://badge.fury.io/py/tftui.svg)](https://badge.fury.io/py/tftui)
![GitHub](https://img.shields.io/github/license/idoavrah/terraform-tui)
![PyPI - Downloads](https://img.shields.io/pypi/dm/tftui)

`TFTUI` is a powerful textual GUI that empowers users to effortlessly view and interact with their Terraform state.

With its latest version you can easily visualize the complete state tree, gaining deeper insights into your infrastructure's current configuration. Additionally, the ability to inspect individual resource states allows you to focus on specific details for better analysis and management. Lastly, it's now possible to select resources and perform actions such as tainting and untainting.

## Key Features

### version 0.4
- [x] Fixed the erroneous flattening of submodules
- [x] Added collapse levels for the state tree

### version 0.3
- [x] Added loading screen and status bar
- [x] Added selection of resources
- [x] Added refresh state functionality
- [x] Added taint/untaint functionality
- [x] Refactoring

### version 0.2
- [x] Comprehensive display of the entire Terraform state tree.
- [x] Effortlessly view and navigate through a single resource state.

## Demo

![](https://github.com/idoavrah/terraform-tui/raw/main/demo/demo.gif "demo")

## Installation

| Tool            | Install             | Upgrade                       | Run                                      |
|-----------------| ------------------- | ----------------------------- | ---------------------------------------- |
| PIP             | `pip install tftui` | `pip install --upgrade tftui` | `cd /path/to/terraform/project && tftui` |
| PIPX            | `pipx install tftui`| `pipx upgrade tftui`          | `cd /path/to/terraform/project && tftui` |

## Stargazers over time
[![Stargazers over time](https://starchart.cc/idoavrah/terraform-tui.svg)](https://starchart.cc/idoavrah/terraform-tui)
