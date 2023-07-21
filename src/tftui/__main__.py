from textual.app import App, ComposeResult, Binding
from textual.widgets import Header, Footer, Tree, TextLog, LoadingIndicator, ContentSwitcher, Static
import subprocess, time

class TerraformTUI(App):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.state = {}
        self.currentNode = None

    TITLE = "Terraform TUI"
    SUB_TITLE = "The textual UI for Terraform"
    CSS_PATH = "ui.css"

    BINDINGS = [
        ("Enter", "", "View state"),
        Binding("escape", "back", "Back"),
        # ("d", "destroy", "Destroy"),
        # ("t", "taint", "Taint"),
        # ("u", "untaint", "Untaint"),
        # ("r", "refresh", "Refresh"),
        ("m", "toggle_dark", "Toggle dark mode"),
        ("q", "quit", "Quit")
    ]

    def compose(self) -> ComposeResult:
        yield Header(classes="header")
        with ContentSwitcher(id="switcher", initial="loading"):
            yield LoadingIndicator(id="loading")
            yield Tree("State", id="tree", classes="tree")
            yield TextLog(id="pretty", highlight=True, markup=True, wrap=True, classes="pretty", auto_scroll=False)
        yield Static(id="status", classes="status")
        yield Footer()

    def on_mount(self) -> None:
        tree = self.get_widget_by_id("tree")
        tree.guide_depth = 3
        data = ""

        status = self.get_widget_by_id("status")
        result = subprocess.run(["terraform", "init", "-no-color"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        if result.returncode != 0:
            status.update(f"{result.stderr} {result.stdout}")
            return
        
        status.update("Loading state...")
        result = subprocess.run(["terraform", "show", "-no-color"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)

        if result.returncode != 0:
            status.update(f"{result.stderr} {result.stdout}")
            return
        elif not result.stdout.startswith('#'):
            status.update(f"{result.stderr} {result.stdout}")
            return
        status.update("")
        
        for line in result.stdout.splitlines():

            # regular resource
            if line.startswith('#') and not line.startswith('# module'):
                leaf = tree.root.add_leaf(line[2:-1])
            
            # module                
            elif line.startswith('# module'):
                node = tree.root
                items = []
                leaf = ""
                parts = line[2:-1].split('.')
                for part in parts:
                    if part == "module":
                        isModule = True
                        continue
                    elif isModule:
                        isModule = False
                        items.append(f"module.{part}")
                        continue
                    leaf = f"{leaf}.{part}"
                items.append(leaf[1:])

                key = ""
                for item in items:
                    isModule = False
                    key = f"{key}.{item}"
                    if item.startswith("module"):
                        isModule = True
                    if self.state.get(key) is None:
                        if isModule:
                            node = node.add(item)
                        else:
                            leaf = node.add_leaf(item)
                        self.state[key] = node
                    else:
                        node = self.state[key]

            # data portion of resource
            else:
                data += line + "\n"

            if len(line) == 1:
                leaf.data = data.strip()
                data = ""

        tree.root.expand_all()
        self.get_widget_by_id("switcher").current = "tree"        
    
    def on_tree_node_highlighted(self, node) -> None:
        self.currentNode = node.node
        pretty = self.get_widget_by_id("pretty")
        if self.currentNode.data is not None:
            pretty = self.get_widget_by_id("pretty")
            pretty.clear()
            pretty.write(self.currentNode.data)
        else:
            self.currentNode = None

    def on_tree_node_selected(self) -> None:
        if (self.currentNode is None):
            return
        self.get_widget_by_id("switcher").current = "pretty"

    def action_back(self) -> None:
        switcher = self.get_widget_by_id("switcher")
        if not switcher.current == "pretty":
            return
        switcher.current = "tree"

    def action_destroy(self) -> None:
        if not self.get_widget_by_id("switcher").current == "tree":
            return

    def action_taint(self) -> None:
        if not self.get_widget_by_id("switcher").current == "tree":
            return

    def action_untaint(self) -> None:
        if not self.get_widget_by_id("switcher").current == "tree":
            return

    def action_refresh(self) -> None:
        if not self.get_widget_by_id("switcher").current == "tree":
            return
        
    def action_toggle_dark(self) -> None:
        self.dark = not self.dark

def main() -> None:
    app = TerraformTUI()
    app.run()

