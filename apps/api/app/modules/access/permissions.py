"""Permission catalog. The backend is the only authority for these checks."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PermissionDef:
    key: str
    label: str
    group: str


_DEFS: list[tuple[str, str, str]] = [
    ("overview.read", "View overview dashboard", "Overview"),
    ("tasks.read", "View own workspace tasks", "Workspace tasks"),
    ("tasks.write", "Create and update own workspace tasks", "Workspace tasks"),
    ("tasks.manage", "Manage and assign all workspace tasks", "Workspace tasks"),
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
    ("pi.inbox.all", "See every conversation (otherwise only assigned ones)", "PI"),
    ("pi.inbox.assign", "Assign conversations to team members", "PI"),
    ("pi.inbox.notes", "Read and write internal conversation notes", "PI"),
    ("pi.customers.export", "Export customer records and memory", "PI"),
    ("pi.knowledge.publish", "Publish knowledge that customers can see", "PI"),
    ("pi.billing.read", "View the Pi plan, usage and invoices", "PI"),
    ("pi.billing.manage", "Change the Pi plan, spend limit or cancel", "PI"),
    ("pi.support.grant", "Approve and revoke operator support access", "PI"),
    ("pi.bookings.read", "View bookings and bookable services", "PI"),
    ("pi.bookings.manage", "Create, change and cancel bookings", "PI"),
    ("pi.work.read", "View tasks and support tickets", "PI"),
    ("pi.work.manage", "Create and update tasks and support tickets", "PI"),
    ("pi.campaigns.read", "View WhatsApp campaigns and their results", "PI"),
    ("pi.campaigns.manage", "Create, schedule and cancel WhatsApp campaigns", "PI"),
    ("admin.members.read", "View members", "Administration"),
    ("admin.members.manage", "Manage members", "Administration"),
    ("admin.roles.manage", "Manage roles", "Administration"),
    ("admin.organization.manage", "Manage branches and departments", "Administration"),
    ("admin.environments.manage", "Manage environments", "Administration"),
    ("admin.products.manage", "Install and configure products", "Administration"),
    ("integrations.read", "View integrations and their health", "Integrations"),
    ("integrations.manage", "Connect, configure and disconnect integrations", "Integrations"),
    ("integrations.operate", "Retry, replay and resync integration work", "Integrations"),
    ("api_keys.manage", "Create and revoke API keys", "Integrations"),
    ("settings.manage", "Manage workspace settings", "Administration"),
    ("audit.read", "View audit log", "Administration"),
    ("notifications.read", "Receive notifications", "Administration"),
]

PERMISSIONS: dict[str, PermissionDef] = {k: PermissionDef(k, label, g) for k, label, g in _DEFS}
ALL = frozenset(PERMISSIONS)


def _pick(*prefixes: str, exclude: tuple[str, ...] = ()) -> frozenset[str]:
    return frozenset(p for p in ALL if any(p.startswith(x) for x in prefixes) and p not in exclude)


READ_ONLY = frozenset(p for p in ALL if p.endswith(".read")) - {"audit.read", "integrations.read"}

SYSTEM_ROLES: dict[str, tuple[str, str, frozenset[str]]] = {
    "owner": ("Owner", "Full access, including ownership", ALL),
    "admin": ("Administrator", "Full workspace administration", ALL),
    "manager": (
        "Manager",
        "Runs day-to-day business operations",
        READ_ONLY
        | _pick("customers.", "catalog.", "inventory.", "sales.", "quotes.", "orders.")
        | {"billing.write", "pi.inbox.reply", "pi.handoffs.manage", "notifications.read"}
        | {"pi.inbox.all", "pi.inbox.assign", "pi.inbox.notes"}
        | {"pi.bookings.manage", "pi.work.manage", "pi.campaigns.manage"},
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
            | {"pi.inbox.all", "pi.inbox.notes", "overview.read", "notifications.read"}
            | {"pi.bookings.read", "pi.bookings.manage", "pi.work.read", "pi.work.manage"}
        ),
    ),
    "member": (
        "Sales/Support member",
        "Handles conversations assigned to them",
        frozenset(
            {"customers.read", "customers.write", "catalog.read", "orders.read"}
            | {"pi.read", "pi.inbox.reply", "pi.handoffs.manage", "pi.memory.read"}
            | {"pi.inbox.notes", "notifications.read"}
            | {"pi.bookings.read", "pi.bookings.manage", "pi.work.read", "pi.work.manage"}
        ),
    ),
    "billing": (
        "Billing",
        "Pi plan, usage and invoices",
        frozenset({"pi.billing.read", "pi.billing.manage", "overview.read", "notifications.read"}),
    ),
    "accountant": (
        "Accountant",
        "Billing, finance, and reports",
        _pick("billing.", "finance.")
        | {"customers.read", "orders.read", "reports.read", "overview.read"}
        | {"notifications.read"},
    ),
    "hr": ("HR", "Employee records", _pick("hr.") | {"overview.read", "notifications.read"}),
    "viewer": (
        "Viewer",
        "Read-only access",
        (READ_ONLY - {"hr.read", "pi.memory.read", "pi.billing.read"}) | {"pi.inbox.all"},
    ),
}

# Permissions granted to PI's system actor. Tools additionally check their own rules.
# Owner OS tasks are independent of customer-facing PI work items.
for _role_key, (_name, _description, _permissions) in list(SYSTEM_ROLES.items()):
    _task_permissions = {"tasks.read"}
    if _role_key != "viewer":
        _task_permissions.add("tasks.write")
    if _role_key in {"owner", "admin", "manager"}:
        _task_permissions.add("tasks.manage")
    SYSTEM_ROLES[_role_key] = (_name, _description, _permissions | _task_permissions)

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
        # Native bookings, tasks and tickets created from customer conversations.
        "pi.bookings.read",
        "pi.bookings.manage",
        "pi.work.read",
        "pi.work.manage",
    }
)


def validate(permissions: set[str] | frozenset[str]) -> frozenset[str]:
    unknown = set(permissions) - ALL
    if unknown:
        raise ValueError("Unknown permissions")
    return frozenset(permissions)
