"""Permission catalog. The backend is the only authority for these checks."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PermissionDef:
    key: str
    label: str
    group: str


_DEFS: list[tuple[str, str, str]] = [
    ("overview.read", "View overview dashboard", "Overview"),
    ("customers.read", "View customers", "Customers"),
    ("customers.write", "Create and edit customers", "Customers"),
    ("catalog.read", "View catalog", "Catalog"),
    ("catalog.write", "Manage catalog", "Catalog"),
    ("inventory.read", "View inventory", "Inventory"),
    ("inventory.adjust", "Adjust stock", "Inventory"),
    ("sales.read", "View sales pipeline", "Sales"),
    ("sales.write", "Manage leads and opportunities", "Sales"),
    ("quotes.read", "View quotes", "Quotes"),
    ("quotes.write", "Create and edit quotes", "Quotes"),
    ("quotes.approve", "Approve quotes", "Quotes"),
    ("orders.read", "View orders", "Orders"),
    ("orders.write", "Create and progress orders", "Orders"),
    ("orders.cancel", "Cancel orders", "Orders"),
    ("billing.read", "View invoices and payments", "Billing"),
    ("billing.write", "Issue invoices and record payments", "Billing"),
    ("finance.read", "View finance", "Finance"),
    ("finance.write", "Record expenses", "Finance"),
    ("hr.read", "View employees", "HR"),
    ("hr.write", "Manage employees", "HR"),
    ("hr.sensitive", "View compensation and sensitive HR data", "HR"),
    ("reports.read", "View reports", "Reports"),
    ("pi.read", "Use PI workspace", "PI"),
    ("pi.inbox.reply", "Reply to and take over conversations", "PI"),
    ("pi.handoffs.manage", "Manage handoffs", "PI"),
    ("pi.agents.manage", "Configure PI agents", "PI"),
    ("pi.knowledge.manage", "Manage PI knowledge", "PI"),
    ("pi.whatsapp.manage", "Manage WhatsApp connection", "PI"),
    ("pi.settings.manage", "Manage PI settings", "PI"),
    ("pi.analytics.read", "View PI analytics", "PI"),
    ("pi.memory.read", "View customer memory", "PI"),
    ("admin.members.read", "View members", "Administration"),
    ("admin.members.manage", "Manage members", "Administration"),
    ("admin.roles.manage", "Manage roles", "Administration"),
    ("admin.organization.manage", "Manage branches and departments", "Administration"),
    ("admin.environments.manage", "Manage environments", "Administration"),
    ("admin.products.manage", "Install and configure products", "Administration"),
    ("settings.manage", "Manage workspace settings", "Administration"),
    ("audit.read", "View audit log", "Administration"),
    ("notifications.read", "Receive notifications", "Administration"),
]

PERMISSIONS: dict[str, PermissionDef] = {k: PermissionDef(k, label, g) for k, label, g in _DEFS}
ALL = frozenset(PERMISSIONS)


def _pick(*prefixes: str, exclude: tuple[str, ...] = ()) -> frozenset[str]:
    return frozenset(p for p in ALL if any(p.startswith(x) for x in prefixes) and p not in exclude)


READ_ONLY = frozenset(p for p in ALL if p.endswith(".read")) - {"audit.read"}

SYSTEM_ROLES: dict[str, tuple[str, str, frozenset[str]]] = {
    "owner": ("Owner", "Full access, including ownership", ALL),
    "admin": ("Administrator", "Full workspace administration", ALL),
    "manager": (
        "Manager",
        "Runs day-to-day business operations",
        READ_ONLY
        | _pick("customers.", "catalog.", "inventory.", "sales.", "quotes.", "orders.")
        | {"billing.write", "pi.inbox.reply", "pi.handoffs.manage", "notifications.read"},
    ),
    "sales": (
        "Sales",
        "Customers, quotes, and orders",
        _pick("customers.", "sales.", "orders.", exclude=("orders.cancel",))
        | {"quotes.read", "quotes.write", "catalog.read", "inventory.read", "overview.read"}
        | {"notifications.read"},
    ),
    "support": (
        "Support",
        "Customer conversations and handoffs",
        frozenset(
            {"customers.read", "customers.write", "catalog.read", "inventory.read", "orders.read"}
            | {"pi.read", "pi.inbox.reply", "pi.handoffs.manage", "pi.memory.read"}
            | {"overview.read", "notifications.read"}
        ),
    ),
    "accountant": (
        "Accountant",
        "Billing, finance, and reports",
        _pick("billing.", "finance.")
        | {"customers.read", "orders.read", "reports.read", "overview.read"}
        | {"notifications.read"},
    ),
    "hr": ("HR", "Employee records", _pick("hr.") | {"overview.read", "notifications.read"}),
    "viewer": ("Viewer", "Read-only access", READ_ONLY - {"hr.read", "pi.memory.read"}),
}

# Permissions granted to PI's system actor. Tools additionally check their own rules.
PI_SYSTEM_PERMISSIONS = frozenset(
    {
        "customers.read",
        "customers.write",
        "catalog.read",
        "inventory.read",
        "orders.read",
        "orders.write",
        "quotes.read",
        "quotes.write",
        "billing.read",
        "billing.write",
        "sales.write",
        "pi.read",
    }
)


def validate(permissions: set[str] | frozenset[str]) -> frozenset[str]:
    unknown = set(permissions) - ALL
    if unknown:
        raise ValueError("Unknown permissions")
    return frozenset(permissions)
