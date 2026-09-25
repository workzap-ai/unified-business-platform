"""Explicit model registry for migrations; no schema creation at import time."""

from app.ai.models import AIUsageEvent
from app.modules.access.models import MembershipRole, Role, RolePermission
from app.modules.audit.models import AuditEvent
from app.modules.auth.models import AuthSession, UserCredential
from app.modules.billing.models import Invoice, InvoiceLine, Payment
from app.modules.branches.models import Branch
from app.modules.business_settings.models import BusinessSettings
from app.modules.catalog.models import CatalogCategory, CatalogProduct, CatalogVariant
from app.modules.customers.models import Customer, CustomerActivity, CustomerNote
from app.modules.departments.models import Department
from app.modules.environments.models import Environment
from app.modules.finance.models import Expense
from app.modules.hr.models import Employee
from app.modules.hr.onboarding import EmployeeOnboarding
from app.modules.inventory.models import InventoryLocation, StockLevel, StockMovement
from app.modules.memberships.models import Membership
from app.modules.navigation.models import NavigationPreference
from app.modules.notifications.models import Notification, NotificationRead
from app.modules.orders.models import Order, OrderLine
from app.modules.pi.models import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSource,
    PiAgent,
    PiAgentRun,
    PiAgentTool,
    PiAgentVersion,
    PiConversation,
    PiHandoff,
    PiMemory,
    PiMessage,
    PiPendingAction,
    PiSettings,
    PiToolCall,
    WhatsAppConnection,
    WhatsAppWebhookEvent,
)
from app.modules.products.models import (
    EnvironmentProductInstallation,
    PlatformProduct,
    TenantProductInstallation,
)
from app.modules.quotes.models import Quote, QuoteLine
from app.modules.sales.models import SalesLead
from app.modules.tenants.models import Tenant
from app.modules.users.models import PlatformUser
from app.shared.sequences import DocumentSequence
from app.workflows.models import WorkflowRun

__all__ = [
    "WorkflowRun",
    "AIUsageEvent",
    "AuditEvent",
    "AuthSession",
    "Branch",
    "BusinessSettings",
    "CatalogCategory",
    "CatalogProduct",
    "CatalogVariant",
    "Customer",
    "CustomerActivity",
    "CustomerNote",
    "Department",
    "DocumentSequence",
    "Employee",
    "EmployeeOnboarding",
    "Environment",
    "EnvironmentProductInstallation",
    "Expense",
    "InventoryLocation",
    "Invoice",
    "InvoiceLine",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "KnowledgeSource",
    "Membership",
    "MembershipRole",
    "NavigationPreference",
    "Notification",
    "NotificationRead",
    "Order",
    "OrderLine",
    "Payment",
    "PiAgent",
    "PiAgentRun",
    "PiAgentTool",
    "PiAgentVersion",
    "PiConversation",
    "PiHandoff",
    "PiMemory",
    "PiMessage",
    "PiPendingAction",
    "PiSettings",
    "PiToolCall",
    "PlatformProduct",
    "PlatformUser",
    "Quote",
    "QuoteLine",
    "Role",
    "RolePermission",
    "SalesLead",
    "StockLevel",
    "StockMovement",
    "Tenant",
    "TenantProductInstallation",
    "UserCredential",
    "WhatsAppConnection",
    "WhatsAppWebhookEvent",
]
