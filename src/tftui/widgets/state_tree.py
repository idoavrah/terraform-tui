"""The state tree: modules as branches, resources as leaves."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, ClassVar

from rich.text import Text
from textual.binding import Binding, BindingType
from textual.message import Message
from textual.widgets import Tree
from textual.widgets.tree import TreeNode

from tftui.terraform.client import LoadedState
from tftui.terraform.state import Resource, State

#: Node payloads: modules carry their dotted path, resources carry themselves.
NodeData = Resource | str | None

_STYLE_TAINTED = "gold3 strike"
_STYLE_SELECTED = "red bold italic reverse"
_STYLE_DATA = "dim"


class StateTree(Tree[NodeData]):
    """A filterable tree of the current Terraform state.

    Selection is tracked by resource *address* rather than by node object, so a
    user's selection survives a search, a collapse and a full state refresh.
    """

    # Tree itself binds only up/down and the shift+arrow variants, so left and
    # right have to be bound here alongside their vim aliases.
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("space", "toggle_selection", "Select", show=False),
        Binding("down,j", "cursor_down", "Down", show=False),
        Binding("up,k", "cursor_up", "Up", show=False),
        Binding("left,h", "go_left", "Left", show=False),
        Binding("right,l", "go_right", "Right", show=False),
    ]

    class SelectionChanged(Message):
        """Posted when the set of selected resources changes."""

        def __init__(self, count: int) -> None:
            super().__init__()
            self.count = count

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.guide_depth = 3
        self.show_root = True
        self.loaded = LoadedState(state=State(), secrets={})
        self.selected: set[str] = set()
        self.search = ""

    # ------------------------------------------------------------------ data

    @property
    def state(self) -> State:
        return self.loaded.state

    def load(self, loaded: LoadedState) -> None:
        """Adopt a freshly read state, dropping selections that no longer exist."""
        self.loaded = loaded
        self.selected &= set(loaded.state.resources)
        self.rebuild(self.search)
        self.post_message(self.SelectionChanged(len(self.selected)))

    def rebuild(self, search: str = "") -> None:
        """Rebuild the tree, showing only resources matching ``search``."""
        self.search = search
        self.clear()
        self.root.data = None
        self.root.label = self._root_label()

        matches = self.state.filter(search)
        module_nodes = self._build_modules(matches)

        for resource in matches:
            parent = module_nodes.get(resource.module, self.root)
            leaf = parent.add_leaf(self._leaf_label(resource), data=resource)
            self._restyle(leaf)

        self.root.expand_all()

    def _build_modules(self, matches: Iterable[Resource]) -> dict[str, TreeNode[NodeData]]:
        """Create a branch for every module path covering ``matches``."""
        needed = self.state.modules(matches)
        nodes: dict[str, TreeNode[NodeData]] = {}

        for path in sorted(needed):
            parts = path.rsplit(".module.", 1)
            if len(parts) == 2:
                parent_path, short = parts[0], f"module.{parts[1]}"
            else:
                parent_path, short = "", path
            parent = nodes.get(parent_path, self.root)
            nodes[path] = parent.add(Text(short, style="bold"), data=path)

        return nodes

    def _root_label(self) -> Text:
        counts = self.state.counts()
        if self.state.is_empty:
            return Text("State (empty)", style="bold")
        label = Text("State ", style="bold")
        label.append(f"({counts['resources']} resources, {counts['data']} data)", style="dim")
        if counts["tainted"]:
            label.append(f" {counts['tainted']} tainted", style=_STYLE_TAINTED.split()[0])
        return label

    # ---------------------------------------------------------------- labels

    def _leaf_label(self, resource: Resource) -> Text:
        return Text(resource.name)

    def _restyle(self, node: TreeNode[NodeData]) -> None:
        """Recompute a leaf's label style from scratch.

        Styles are rebuilt rather than layered on, so toggling a selection off
        can never leave a stale style behind.
        """
        resource = node.data
        if not isinstance(resource, Resource):
            return
        label = Text(resource.name)
        if resource.full_address in self.selected:
            label.stylize(_STYLE_SELECTED)
        elif resource.tainted:
            label.stylize(_STYLE_TAINTED)
        elif resource.is_data:
            label.stylize(_STYLE_DATA)
        node.set_label(label)

    # ------------------------------------------------------------- selection

    @property
    def highlighted(self) -> Resource | None:
        """The resource under the cursor, if the cursor is on a resource."""
        node = self.cursor_node
        return node.data if node is not None and isinstance(node.data, Resource) else None

    @property
    def selected_resources(self) -> list[Resource]:
        """Selected resources, in state order."""
        return [
            resource
            for address, resource in self.state.resources.items()
            if address in self.selected
        ]

    def targets(self) -> list[Resource]:
        """The resources an action applies to: the selection, else the cursor."""
        if self.selected:
            return self.selected_resources
        current = self.highlighted
        return [current] if current is not None and current.is_actionable else []

    def action_toggle_selection(self) -> None:
        """Select or deselect whatever the cursor is on.

        On a resource that is one resource. On a module it is every actionable
        resource beneath it, however deeply nested: selecting a whole module by
        hand is the tedious case this exists to avoid. Expanding and collapsing
        moved to Enter, the arrow keys and the digit keys.
        """
        node = self.cursor_node
        if node is None:
            return

        data = node.data
        if isinstance(data, Resource):
            self._toggle_resources([data], [node])
        elif isinstance(data, str):
            self._toggle_module(node)

    def _toggle_module(self, node: TreeNode[NodeData]) -> None:
        """Select every actionable resource under ``node``, or clear them all."""
        pairs = [
            (child.data, child)
            for child in self._walk(node)
            if isinstance(child.data, Resource) and child.data.is_actionable
        ]
        if not pairs:
            self.app.bell()
            return
        self._toggle_resources([data for data, _ in pairs], [n for _, n in pairs])

    def _toggle_resources(
        self,
        resources: list[Resource],
        nodes: list[TreeNode[NodeData]],
    ) -> None:
        """Add all of ``resources`` to the selection, or remove them all.

        Mixed selections resolve to "select the rest", which is what someone
        pressing Space on a partly-selected module almost always wants.
        """
        actionable = [resource for resource in resources if resource.is_actionable]
        if not actionable:
            self.app.bell()
            return

        addresses = [resource.full_address for resource in actionable]
        if all(address in self.selected for address in addresses):
            self.selected.difference_update(addresses)
        else:
            self.selected.update(addresses)

        for node in nodes:
            self._restyle(node)
        self.post_message(self.SelectionChanged(len(self.selected)))

    def clear_selection(self) -> None:
        if not self.selected:
            return
        self.selected.clear()
        for node in self._walk(self.root):
            self._restyle(node)
        self.post_message(self.SelectionChanged(0))

    def _walk(self, node: TreeNode[NodeData]) -> Iterable[TreeNode[NodeData]]:
        for child in node.children:
            yield child
            yield from self._walk(child)

    # ------------------------------------------------------------ navigation

    def action_go_left(self) -> None:
        """Collapse the current node, or move to its parent if already collapsed."""
        node = self.cursor_node
        if node is None:
            return
        if node.allow_expand and node.is_expanded:
            node.collapse()
        elif node.parent is not None:
            self.cursor_line = node.parent.line
            self.scroll_to_line(self.cursor_line)

    def action_go_right(self) -> None:
        """Expand the current node, or descend to the next line if already open."""
        node = self.cursor_node
        if node is None:
            return
        if node.allow_expand and not node.is_expanded:
            node.expand()
        elif self.cursor_line + 1 <= self.last_line:
            self.cursor_line += 1
            self.scroll_to_line(self.cursor_line)

    def collapse_to(self, level: int) -> None:
        """Show the tree down to ``level`` modules deep. Level 0 expands everything."""
        if level == 0:
            self.root.expand_all()
            return
        self.root.collapse_all()
        for node in self.root.children:
            self._expand_to(node, level)
        self.root.expand()

    def _expand_to(self, node: TreeNode[NodeData], level: int) -> None:
        if not isinstance(node.data, str):
            return
        depth = node.data.count(".module.") + 1
        if depth >= level:
            return
        for child in node.children:
            self._expand_to(child, level)
        node.expand()
