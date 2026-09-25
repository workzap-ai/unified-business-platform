from pathlib import Path

import pytest

from app.modules.access.permissions import ALL, SYSTEM_ROLES
from app.modules.navigation.definitions import REGISTRY, build_registry
from app.modules.navigation.export import ACCESS_TARGET, TARGET, render, render_access
from app.modules.navigation.registry import (
    NavContext,
    NavDefinition,
    merge_order,
    validate_custom_order,
)

DEFAULT_MAIN = [
    "Overview",
    "Customers / CRM",
    "Catalog",
    "PI",
    "Inventory",
    "Sales",
    "Quotes",
    "Orders",
    "Billing",
    "Finance",
    "HR",
    "Reports",
]


def context(
    permissions: frozenset[str] = ALL, products: dict[str, set[str]] | None = None
) -> NavContext:
    installed = {"pi": {"text", "voice", "vision", "knowledge", "orders", "quotes", "handoff"}}
    return NavContext(
        permissions=permissions,
        roles=frozenset({"owner"}),
        products=installed if products is None else products,
        environment_kind="production",
    )


def labels(section: list) -> list[str]:  # type: ignore[type-arg]
    return [item.definition.label for item in section]


def test_default_main_order_is_the_product_contract():
    resolved = REGISTRY.resolve(context())
    assert labels(resolved["main"]) == DEFAULT_MAIN
    assert [i.definition.key for i in resolved["admin"]] == [
        "settings",
        "members",
        "roles",
        "branches",
        "departments",
        "environments",
        "integrations",
        "audit",
        "products",
        "notifications",
    ]


def test_pi_is_a_top_level_product_with_its_own_subnavigation():
    pi = next(i for i in REGISTRY.resolve(context())["main"] if i.definition.key == "pi")
    assert pi.definition.parent is None and pi.definition.type == "product"
    assert [c.definition.label for c in pi.children] == [
        "PI Overview",
        "Inbox",
        "Agents",
        "WhatsApp",
        "Knowledge",
        "Handoffs",
        "Analytics",
        "Settings",
    ]


def test_pi_hidden_without_installation_or_permission():
    no_product = REGISTRY.resolve(context(products={}))["main"]
    assert "PI" not in labels(no_product)
    no_permission = REGISTRY.resolve(context(permissions=ALL - {"pi.read"}))["main"]
    assert "PI" not in labels(no_permission)
    # Hidden modules leave no gaps: the rest keeps default relative order.
    assert labels(no_permission) == [x for x in DEFAULT_MAIN if x != "PI"]


def test_feature_gated_children_follow_enabled_features():
    ctx = context(products={"pi": {"text"}})
    pi = next(i for i in REGISTRY.resolve(ctx)["main"] if i.definition.key == "pi")
    child_keys = {c.definition.key for c in pi.children}
    assert "pi-knowledge" not in child_keys and "pi-handoffs" not in child_keys
    assert "pi-inbox" in child_keys


def test_role_permissions_shape_the_sidebar():
    support = SYSTEM_ROLES["support"][2]
    visible = labels(REGISTRY.resolve(context(permissions=support))["main"])
    assert visible == ["Overview", "Customers / CRM", "Catalog", "PI", "Inventory", "Orders"]


def test_custom_order_is_applied_and_new_modules_use_default_sort_order():
    registry = build_registry()
    visible = [i for i in registry.top_level("main")]
    custom = [
        "pi",
        "overview",
        "customers",
        "catalog",
        "inventory",
        "sales",
        "quotes",
        "orders",
        "billing",
        "finance",
        "hr",
        "reports",
    ]
    resolved = registry.resolve(context(), {"main": custom})
    assert [i.definition.key for i in resolved["main"]] == custom

    # A future module registers once; the sidebar picks it up with no component change.
    registry.register(
        NavDefinition(
            "subscriptions",
            "Subscriptions",
            "/subscriptions",
            "repeat",
            "main",
            130,
            required_permissions=("billing.read",),
        )
    )
    after = [i.definition.key for i in registry.resolve(context(), {"main": custom})["main"]]
    assert after == [*custom, "subscriptions"]  # after Reports (120), the saved order intact
    default = [i.definition.label for i in registry.resolve(context())["main"]]
    assert default == [*DEFAULT_MAIN, "Subscriptions"]
    # Permission gate still applies to the new module.
    denied = registry.resolve(context(permissions=ALL - {"billing.read"}), {"main": custom})
    assert "subscriptions" not in [i.definition.key for i in denied["main"]]
    assert len(visible) == 12


def test_new_module_inserted_between_neighbours_in_custom_order():
    items = [
        NavDefinition(k, k, f"/{k}", "x", "main", o)
        for k, o in [("a", 10), ("b", 20), ("new", 25), ("c", 30)]
    ]
    assert [i.key for i in merge_order(items, ["c", "b", "a"])] == ["c", "b", "new", "a"]
    assert [i.key for i in merge_order(items, ["gone", "a"])] == ["a", "b", "new", "c"]
    assert [i.key for i in merge_order(items, [])] == ["a", "b", "new", "c"]


def test_saved_order_cannot_reveal_inaccessible_or_duplicate_items():
    visible = [NavDefinition(k, k, f"/{k}", "x", "main", o) for k, o in [("a", 10), ("b", 20)]]
    assert validate_custom_order(visible, ["b", "a"]) == ["b", "a"]
    with pytest.raises(ValueError):
        validate_custom_order(visible, ["a", "hidden"])
    with pytest.raises(ValueError):
        validate_custom_order(visible, ["a", "a"])


def test_registry_rejects_duplicate_keys_and_sort_orders():
    registry = build_registry()
    with pytest.raises(ValueError):
        registry.register(NavDefinition("pi", "PI 2", "/pi2", "bot", "main", 999))
    with pytest.raises(ValueError):
        registry.register(NavDefinition("dup", "Dup", "/dup", "x", "main", 40))


def test_every_route_is_unique_and_absolute():
    routes = [d.route for d in REGISTRY.definitions() if d.parent is None]
    assert len(routes) == len(set(routes))
    assert all(d.route.startswith("/") for d in REGISTRY.definitions())


def test_frontend_snapshots_are_in_sync_with_the_registry():
    # Regenerate with: python -m app.modules.navigation.export
    assert Path(TARGET).read_text(encoding="utf-8") == render()
    assert Path(ACCESS_TARGET).read_text(encoding="utf-8") == render_access()
