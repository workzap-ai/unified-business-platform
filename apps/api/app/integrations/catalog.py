"""The integration catalog: every definition, with its adapter when one exists.

`planned` definitions are listed honestly in the directory but cannot be connected.
Zapier/Make/n8n style automation is covered by `generic_webhook` and outbound webhook
subscriptions.
"""

from app.integrations.providers import (
    generic_webhook,
    resend,
    s3,
    sendgrid,
    slack,
    smtp,
    stripe,
    whatsapp_meta,
)
from app.integrations.registry import (
    AuthType,
    Category,
    IntegrationDefinition,
    IntegrationRegistry,
    OAuthSpec,
)

REGISTRY = IntegrationRegistry()

REGISTRY.register(generic_webhook.DEFINITION, generic_webhook.GenericWebhookProvider())
REGISTRY.register(slack.DEFINITION, slack.SlackProvider())
REGISTRY.register(whatsapp_meta.DEFINITION, whatsapp_meta.WhatsAppMetaProvider())
REGISTRY.register(smtp.DEFINITION, smtp.SmtpProvider())
REGISTRY.register(resend.DEFINITION, resend.ResendProvider())
REGISTRY.register(sendgrid.DEFINITION, sendgrid.SendGridProvider())
REGISTRY.register(s3.DEFINITION, s3.S3Provider())
REGISTRY.register(stripe.DEFINITION, stripe.StripeProvider())


def _planned(
    key: str,
    name: str,
    description: str,
    category: Category,
    provider: str,
    auth: AuthType,
    docs: str,
    capabilities: tuple[str, ...],
    scopes: tuple[str, ...] = (),
    oauth: OAuthSpec | None = None,
) -> None:
    REGISTRY.register(
        IntegrationDefinition(
            key=key,
            name=name,
            description=description,
            category=category,
            provider=provider,
            auth_type=auth,
            availability="planned",
            capabilities=capabilities,
            supported_scopes=scopes,
            documentation_url=docs,
            oauth=oauth,
        )
    )


_planned(
    "google_calendar",
    "Google Calendar",
    "Sync bookings and appointments with Google Calendar.",
    "calendar",
    "Google",
    "oauth2_pkce",
    "https://developers.google.com/calendar/api",
    ("calendar_events",),
    ("https://www.googleapis.com/auth/calendar.events",),
    OAuthSpec(
        "https://accounts.google.com/o/oauth2/v2/auth",
        "https://oauth2.googleapis.com/token",
        "https://oauth2.googleapis.com/revoke",
    ),
)
_planned(
    "microsoft_calendar",
    "Microsoft Outlook Calendar",
    "Sync bookings with Outlook calendars through Microsoft Graph.",
    "calendar",
    "Microsoft",
    "oauth2_pkce",
    "https://learn.microsoft.com/graph/api/resources/calendar",
    ("calendar_events",),
    ("Calendars.ReadWrite", "offline_access"),
)
_planned(
    "google_workspace",
    "Google Workspace",
    "Directory and Gmail sending for Google Workspace.",
    "identity",
    "Google",
    "oauth2_pkce",
    "https://developers.google.com/workspace",
    ("directory", "send_email"),
)
_planned(
    "microsoft_graph",
    "Microsoft 365",
    "Directory and Outlook mail through Microsoft Graph.",
    "identity",
    "Microsoft",
    "oauth2_pkce",
    "https://learn.microsoft.com/graph/overview",
    ("directory", "send_email"),
)
_planned(
    "quickbooks",
    "QuickBooks Online",
    "Push invoices and payments to QuickBooks Online.",
    "accounting",
    "Intuit",
    "oauth2",
    "https://developer.intuit.com/app/developer/qbo/docs",
    ("invoices", "payments", "customers"),
)
_planned(
    "xero",
    "Xero",
    "Push invoices and payments to Xero.",
    "accounting",
    "Xero",
    "oauth2_pkce",
    "https://developer.xero.com/documentation/api/accounting/overview",
    ("invoices", "payments", "customers"),
)
_planned(
    "shopify",
    "Shopify",
    "Import orders and products from a Shopify store.",
    "commerce",
    "Shopify",
    "oauth2",
    "https://shopify.dev/docs/api/admin-rest",
    ("orders", "products"),
)
_planned(
    "woocommerce",
    "WooCommerce",
    "Import orders and products from WooCommerce.",
    "commerce",
    "WooCommerce",
    "basic_auth",
    "https://woocommerce.github.io/woocommerce-rest-api-docs/",
    ("orders", "products"),
)
_planned(
    "microsoft_teams",
    "Microsoft Teams",
    "Post notifications to a Microsoft Teams channel.",
    "collaboration",
    "Microsoft",
    "webhook_secret",
    "https://learn.microsoft.com/microsoftteams/platform/webhooks-and-connectors/what-are-webhooks-and-connectors",
    ("send_message",),
)
