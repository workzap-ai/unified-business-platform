"""Navigation registry: the single source of truth for what the shell can show.

The product registry answers "what is installed and configured?". This registry answers
"what should this user see, and where?". Sidebar, mobile drawer, PI sub-navigation and
the command menu are all rendered from `resolve()`; none keeps its own route list.

Adding a first-class module = one `register(NavDefinition(...))` call with a route,
permissions, optional product/feature dependency and a default sort order.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

Section = Literal["main", "admin"]
ItemType = Literal["module", "product", "page"]


@dataclass(frozen=True, slots=True)
class NavDefinition:
    key: str
    label: str
    route: str
    icon: str
    section: Section
    sort_order: int
    type: ItemType = "module"
    parent: str | None = None
    enabled: bool = True
    visible: bool = True
    # All of required_permissions, or at least one of any_permissions (when given).
    required_permissions: tuple[str, ...] = ()
    any_permissions: tuple[str, ...] = ()
    required_roles: tuple[str, ...] = ()
    required_product: str | None = None
    required_feature: str | None = None
    environment_scope: tuple[str, ...] | None = None  # allowed environment kinds
    badge: str | None = None
    analytics_id: str = ""
    keywords: tuple[str, ...] = ()
    description: str = ""


@dataclass(frozen=True, slots=True)
class NavContext:
    permissions: frozenset[str]
    roles: frozenset[str]
    products: Mapping[str, set[str]]  # product key -> enabled features
    environment_kind: str


@dataclass(slots=True)
class ResolvedItem:
    definition: NavDefinition
    children: list["ResolvedItem"] = field(default_factory=list)
    badge_value: int | None = None


class NavigationRegistry:
    def __init__(self) -> None:
        self._items: dict[str, NavDefinition] = {}

    def register(self, item: NavDefinition) -> NavDefinition:
        if item.key in self._items:
            raise ValueError(f"Navigation key {item.key} is already registered")
        if item.parent is not None and item.parent not in self._items:
            raise ValueError(f"Parent {item.parent} must be registered first")
        clash = [
            i
            for i in self._items.values()
            if i.section == item.section
            and i.parent == item.parent
            and i.sort_order == item.sort_order
        ]
        if clash:
            raise ValueError(f"Sort order {item.sort_order} is already used by {clash[0].key}")
        self._items[item.key] = item
        return item

    def unregister(self, key: str) -> None:
        for child in [i.key for i in self._items.values() if i.parent == key]:
            self.unregister(child)
        self._items.pop(key, None)

    def definitions(self) -> list[NavDefinition]:
        return list(self._items.values())

    def get(self, key: str) -> NavDefinition | None:
        return self._items.get(key)

    def top_level(self, section: Section) -> list[NavDefinition]:
        return sorted(
            (i for i in self._items.values() if i.section == section and i.parent is None),
            key=lambda i: (i.sort_order, i.key),
        )

    def children(self, parent: str) -> list[NavDefinition]:
        return sorted(
            (i for i in self._items.values() if i.parent == parent),
            key=lambda i: (i.sort_order, i.key),
        )

    @staticmethod
    def allowed(item: NavDefinition, context: NavContext) -> bool:
        if not (item.enabled and item.visible):
            return False
        if not all(p in context.permissions for p in item.required_permissions):
            return False
        if item.any_permissions and not any(p in context.permissions for p in item.any_permissions):
            return False
        if item.required_roles and not (set(item.required_roles) & context.roles):
            return False
        if item.required_product is not None:
            features = context.products.get(item.required_product)
            if features is None:
                return False
            if item.required_feature is not None and item.required_feature not in features:
                return False
        if (
            item.environment_scope is not None
            and context.environment_kind not in item.environment_scope
        ):
            return False
        return True

    def resolve(
        self, context: NavContext, custom_orders: Mapping[str, Sequence[str]] | None = None
    ) -> dict[Section, list[ResolvedItem]]:
        custom_orders = custom_orders or {}
        result: dict[Section, list[ResolvedItem]] = {}
        for section in ("main", "admin"):
            visible = [i for i in self.top_level(section) if self.allowed(i, context)]
            ordered = merge_order(visible, custom_orders.get(section, ()))
            result[section] = [
                ResolvedItem(
                    definition=item,
                    children=[
                        ResolvedItem(child)
                        for child in self.children(item.key)
                        if self.allowed(child, context)
                    ],
                )
                for item in ordered
            ]
        return result


def merge_order(defaults: Sequence[NavDefinition], custom: Iterable[str]) -> list[NavDefinition]:
    """Apply a saved custom order to the currently visible items.

    - Unknown or now-hidden keys in the saved order are skipped (no gaps).
    - Visible items missing from the saved order (e.g. newly registered modules) are
      inserted right after their nearest preceding item in default sort order, so a new
      module lands where its registered sort_order puts it relative to its neighbours.
    """
    by_key = {item.key: item for item in defaults}
    seen: set[str] = set()
    ordered: list[NavDefinition] = []
    for key in custom:
        if key in by_key and key not in seen:
            ordered.append(by_key[key])
            seen.add(key)
    if not ordered:
        return list(defaults)
    for index, item in enumerate(defaults):
        if item.key in seen:
            continue
        position = 0
        for previous in reversed(defaults[:index]):
            if previous.key in seen:
                position = ordered.index(previous) + 1
                break
        ordered.insert(position, item)
        seen.add(item.key)
    return ordered


def validate_custom_order(visible: Sequence[NavDefinition], order: Sequence[str]) -> list[str]:
    """A saved order may only contain currently visible top-level keys, once each."""
    keys = {i.key for i in visible}
    if len(set(order)) != len(order):
        raise ValueError("Duplicate navigation keys")
    if not set(order) <= keys:
        raise ValueError("Navigation order contains unavailable items")
    return list(order)
