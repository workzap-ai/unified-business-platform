/**
 * Fictional sample data for the Integrations console (demo data mode only). Provider
 * names describe what an adapter would talk to; every connection, endpoint, event and
 * key below is invented and never reaches a provider. Hosts use reserved example domains.
 */
import { demoCollection, type DemoProfile } from "@/demo/store";
import { rng } from "@/demo/random";
import type {
  ApiKey,
  ConnectionDetail,
  Delivery,
  EventType,
  InboundEvent,
  IntegrationDefinition,
  SyncJob,
  WebhookSubscription,
} from "./types";

type Def = Omit<IntegrationDefinition, "connection_count">;

export const DEMO_DEFINITIONS: Def[] = [
  {
    key: "generic_webhook",
    name: "Generic webhook",
    description:
      "Send signed JSON payloads to any HTTPS endpoint you control. Use it for automation tools and in-house services.",
    category: "automation",
    provider: "Generic",
    availability: "available",
    auth_type: "signature_secret",
    capabilities: ["send_webhook"],
    supported_scopes: [],
    required_scopes: [],
    webhook_support: false,
    sync_support: ["none"],
    supports_sandbox: false,
    documentation_url: null,
    version: "1",
    config_schema: [
      {
        key: "url",
        label: "Endpoint URL",
        type: "url",
        required: true,
        secret: false,
        help: "HTTPS only",
      },
      {
        key: "signing_secret",
        label: "Signing secret",
        type: "password",
        required: true,
        secret: true,
        help: "Used to sign every payload (HMAC-SHA256). Stored encrypted; never shown again.",
      },
    ],
  },
  {
    key: "whatsapp_meta",
    name: "WhatsApp Business (Meta Cloud API)",
    description:
      "Send and receive WhatsApp messages through a Meta Cloud API phone number, with delivery and read receipts.",
    category: "messaging",
    provider: "Meta",
    availability: "available",
    auth_type: "bearer_token",
    capabilities: [
      "send_message",
      "receive_message",
      "message_status",
      "message_templates",
    ],
    supported_scopes: [
      "whatsapp_business_messaging",
      "whatsapp_business_management",
      "business_management",
    ],
    required_scopes: [
      "whatsapp_business_messaging",
      "whatsapp_business_management",
    ],
    webhook_support: true,
    sync_support: ["none"],
    supports_sandbox: true,
    documentation_url:
      "https://developers.facebook.com/docs/whatsapp/cloud-api",
    version: "1",
    config_schema: [
      {
        key: "phone_number_id",
        label: "Phone number ID",
        type: "text",
        required: true,
        secret: false,
        help: "From WhatsApp Manager › Phone numbers",
      },
      {
        key: "business_account_id",
        label: "WhatsApp Business account ID",
        type: "text",
        required: true,
        secret: false,
        help: null,
      },
      {
        key: "access_token",
        label: "System user access token",
        type: "password",
        required: true,
        secret: true,
        help: "A permanent system user token with the scopes listed above.",
      },
      {
        key: "app_secret",
        label: "App secret",
        type: "password",
        required: true,
        secret: true,
        help: "Verifies the signature on inbound webhook events.",
      },
    ],
  },
  {
    key: "smtp",
    name: "SMTP email",
    description:
      "Send transactional email (invoices, quotes, notifications) through your own SMTP server.",
    category: "email",
    provider: "SMTP",
    availability: "available",
    auth_type: "basic_auth",
    capabilities: ["send_email"],
    supported_scopes: [],
    required_scopes: [],
    webhook_support: false,
    sync_support: ["none"],
    supports_sandbox: false,
    documentation_url: null,
    version: "1",
    config_schema: [
      {
        key: "host",
        label: "SMTP host",
        type: "text",
        required: true,
        secret: false,
        help: null,
      },
      {
        key: "port",
        label: "Port",
        type: "number",
        required: true,
        secret: false,
        help: "Usually 587 (STARTTLS) or 465 (TLS)",
      },
      {
        key: "security",
        label: "Security",
        type: "select",
        required: true,
        secret: false,
        help: null,
        options: [
          { value: "starttls", label: "STARTTLS" },
          { value: "tls", label: "TLS" },
        ],
      },
      {
        key: "from_address",
        label: "From address",
        type: "email",
        required: true,
        secret: false,
        help: null,
      },
      {
        key: "username",
        label: "Username",
        type: "text",
        required: true,
        secret: false,
        help: null,
      },
      {
        key: "password",
        label: "Password",
        type: "password",
        required: true,
        secret: true,
        help: null,
      },
    ],
  },
  {
    key: "slack",
    name: "Slack",
    description:
      "Post handoff alerts and order notifications to Slack channels.",
    category: "collaboration",
    provider: "Slack",
    availability: "available",
    auth_type: "oauth2",
    capabilities: ["post_message", "receive_events"],
    supported_scopes: [
      "chat:write",
      "channels:read",
      "users:read",
      "channels:history",
    ],
    required_scopes: ["chat:write", "channels:read"],
    webhook_support: true,
    sync_support: ["none"],
    supports_sandbox: false,
    documentation_url: "https://api.slack.com/docs",
    version: "1",
    config_schema: [
      {
        key: "default_channel",
        label: "Default channel",
        type: "text",
        required: false,
        secret: false,
        help: "e.g. #sales-alerts",
      },
    ],
  },
  {
    key: "s3_storage",
    name: "S3-compatible storage",
    description:
      "Store exported documents and attachments in an S3-compatible bucket you own.",
    category: "storage",
    provider: "S3-compatible",
    availability: "available",
    auth_type: "api_key",
    capabilities: ["store_files"],
    supported_scopes: [],
    required_scopes: [],
    webhook_support: false,
    sync_support: ["none"],
    supports_sandbox: false,
    documentation_url: null,
    version: "1",
    config_schema: [
      {
        key: "endpoint",
        label: "Endpoint URL",
        type: "url",
        required: true,
        secret: false,
        help: "HTTPS only",
      },
      {
        key: "bucket",
        label: "Bucket",
        type: "text",
        required: true,
        secret: false,
        help: null,
      },
      {
        key: "access_key_id",
        label: "Access key ID",
        type: "text",
        required: true,
        secret: false,
        help: null,
      },
      {
        key: "secret_access_key",
        label: "Secret access key",
        type: "password",
        required: true,
        secret: true,
        help: null,
      },
    ],
  },
  {
    key: "openai",
    name: "OpenAI",
    description:
      "Bring your own model provider key for PI drafting and summarisation.",
    category: "ai",
    provider: "OpenAI",
    availability: "beta",
    auth_type: "api_key",
    capabilities: ["text_generation", "embeddings"],
    supported_scopes: [],
    required_scopes: [],
    webhook_support: false,
    sync_support: ["none"],
    supports_sandbox: false,
    documentation_url: "https://platform.openai.com/docs",
    version: "1",
    config_schema: [
      {
        key: "model",
        label: "Default model",
        type: "select",
        required: true,
        secret: false,
        help: null,
        options: [
          { value: "standard", label: "Standard" },
          { value: "fast", label: "Fast" },
        ],
      },
      {
        key: "api_key",
        label: "API key",
        type: "password",
        required: true,
        secret: true,
        help: null,
      },
    ],
  },
  {
    key: "stripe",
    name: "Stripe",
    description:
      "Receive payment events and reconcile card payments against invoices.",
    category: "payments",
    provider: "Stripe",
    availability: "beta",
    auth_type: "api_key",
    capabilities: ["receive_payment_events", "sync_payments"],
    supported_scopes: [],
    required_scopes: [],
    webhook_support: true,
    sync_support: ["pull"],
    supports_sandbox: true,
    documentation_url: "https://docs.stripe.com",
    version: "1",
    config_schema: [
      {
        key: "secret_key",
        label: "Secret key",
        type: "password",
        required: true,
        secret: true,
        help: "Use a restricted key where possible.",
      },
      {
        key: "webhook_signing_secret",
        label: "Webhook signing secret",
        type: "password",
        required: true,
        secret: true,
        help: null,
      },
    ],
  },
  {
    key: "shopify",
    name: "Shopify",
    description:
      "Pull products, orders and customers from a Shopify store and receive order webhooks.",
    category: "commerce",
    provider: "Shopify",
    availability: "beta",
    auth_type: "oauth2",
    capabilities: [
      "sync_products",
      "sync_orders",
      "sync_customers",
      "receive_order_events",
    ],
    supported_scopes: [
      "read_products",
      "read_orders",
      "read_customers",
      "write_products",
    ],
    required_scopes: ["read_products", "read_orders", "read_customers"],
    webhook_support: true,
    sync_support: ["pull"],
    supports_sandbox: true,
    documentation_url: "https://shopify.dev/docs/api",
    version: "1",
    config_schema: [
      {
        key: "shop_domain",
        label: "Shop domain",
        type: "text",
        required: true,
        secret: false,
        help: "e.g. your-store.myshopify.com",
      },
    ],
  },
  {
    key: "google_calendar",
    name: "Google Calendar",
    description: "Sync appointments booked through PI to team calendars.",
    category: "calendar",
    provider: "Google",
    availability: "planned",
    auth_type: "oauth2",
    capabilities: ["sync_events"],
    supported_scopes: ["calendar.events", "calendar.readonly"],
    required_scopes: ["calendar.events"],
    webhook_support: true,
    sync_support: ["bidirectional"],
    supports_sandbox: false,
    documentation_url: null,
    version: "0",
    config_schema: [],
  },
  {
    key: "quickbooks",
    name: "QuickBooks Online",
    description: "Push invoices and payments to your accounting ledger.",
    category: "accounting",
    provider: "Intuit",
    availability: "planned",
    auth_type: "oauth2",
    capabilities: ["sync_invoices", "sync_payments"],
    supported_scopes: ["com.intuit.quickbooks.accounting"],
    required_scopes: ["com.intuit.quickbooks.accounting"],
    webhook_support: true,
    sync_support: ["push"],
    supports_sandbox: true,
    documentation_url: null,
    version: "0",
    config_schema: [],
  },
  {
    key: "oidc_sso",
    name: "OpenID Connect SSO",
    description: "Let members sign in with your identity provider.",
    category: "identity",
    provider: "OpenID Connect",
    availability: "planned",
    auth_type: "oauth2_pkce",
    capabilities: ["single_sign_on"],
    supported_scopes: ["openid", "profile", "email"],
    required_scopes: ["openid", "email"],
    webhook_support: false,
    sync_support: ["none"],
    supports_sandbox: false,
    documentation_url: null,
    version: "0",
    config_schema: [],
  },
];

export const DEMO_EVENT_TYPES: EventType[] = [
  { key: "customer.created", description: "A customer record was created" },
  { key: "customer.updated", description: "A customer record changed" },
  { key: "order.confirmed", description: "An order was confirmed" },
  { key: "order.fulfilled", description: "An order was fulfilled" },
  { key: "order.cancelled", description: "An order was cancelled" },
  { key: "invoice.issued", description: "An invoice was issued" },
  { key: "invoice.paid", description: "An invoice was paid in full" },
  { key: "quote.approved", description: "A quote was approved" },
  {
    key: "handoff.created",
    description: "PI handed a conversation to a person",
  },
];

/** Internal demo-only fields are stripped by the contract schemas on the way out. */
export type DemoConnection = ConnectionDetail & {
  /** How the fictional provider behaves when tested. */
  behavior: "ok" | "rate_limited" | "auth_failed";
};

export type DemoIntegrationsState = {
  connections: DemoConnection[];
  webhooks: WebhookSubscription[];
  deliveries: Delivery[];
  events: InboundEvent[];
  jobs: SyncJob[];
  apiKeys: ApiKey[];
};

const MIN = 60_000;
const ago = (minutes: number) =>
  new Date(Date.now() - minutes * MIN).toISOString();
const ahead = (minutes: number) =>
  new Date(Date.now() + minutes * MIN).toISOString();

function hex(r: ReturnType<typeof rng>, length: number) {
  let out = "";
  for (let i = 0; i < length; i += 1) out += r.int(0, 15).toString(16);
  return out;
}

function base(
  profile: DemoProfile,
  id: string,
  partial: Partial<DemoConnection> &
    Pick<DemoConnection, "integration_key" | "display_name" | "status">,
): DemoConnection {
  return {
    id,
    mode: "production",
    environment_id: profile.environmentId,
    health: "healthy",
    circuit_state: "closed",
    last_success_at: null,
    last_failure_at: null,
    last_error: null,
    last_health_check_at: null,
    connected_at: null,
    expires_at: null,
    created_at: ago(60 * 24 * 40),
    updated_at: ago(60 * 24 * 2),
    config: {},
    credentials: [],
    scopes: [],
    sync_direction: "none",
    health_detail: {
      latency_ms: null,
      consecutive_failures: 0,
      rate_limited_until: null,
    },
    recent_activity: [],
    behavior: "ok",
    ...partial,
  };
}

function seed(profile: DemoProfile): DemoIntegrationsState {
  const empty: DemoIntegrationsState = {
    connections: [],
    webhooks: [],
    deliveries: [],
    events: [],
    jobs: [],
    apiKeys: [],
  };
  if (profile.kind === "empty") return empty;
  const commerce = profile.kind === "commerce";
  const r = rng(commerce ? 4101 : 5202);
  const p = commerce ? "nw" : "bl";
  const hookId = `con-${p}-hook`;
  const waId = `con-${p}-wa`;
  const smtpId = `con-${p}-smtp`;

  const connections: DemoConnection[] = [
    base(profile, hookId, {
      integration_key: "generic_webhook",
      display_name: commerce
        ? "Fulfilment partner hook"
        : "Project tracker hook",
      status: "connected",
      last_success_at: ago(18),
      last_health_check_at: ago(18),
      connected_at: ago(60 * 24 * 38),
      config: {
        url: commerce
          ? "https://hooks.fulfilment-partner.example/northwind"
          : "https://tracker.example.org/hooks/brightline",
      },
      credentials: [{ key: "signing_secret", set: true, hint: "…9f2c" }],
      health_detail: {
        latency_ms: 182,
        consecutive_failures: 0,
        rate_limited_until: null,
      },
      recent_activity: [
        {
          at: ago(18),
          kind: "delivery",
          outcome: "success",
          message: "Payload delivered (HTTP 200)",
        },
        {
          at: ago(60 * 24 * 3),
          kind: "test",
          outcome: "success",
          message: "Connection verified",
        },
        {
          at: ago(60 * 24 * 38),
          kind: "created",
          outcome: "success",
          message: "Connection created by Amina Rahman",
        },
      ],
    }),
    base(profile, waId, {
      integration_key: "whatsapp_meta",
      display_name: commerce ? "Northwind WhatsApp line" : "Studio WhatsApp",
      status: "degraded",
      health: "degraded",
      circuit_state: "half_open",
      last_success_at: ago(52),
      last_failure_at: ago(9),
      last_error:
        "Meta is rate limiting this number (HTTP 429). Outbound sends are being retried with backoff.",
      last_health_check_at: ago(9),
      connected_at: ago(60 * 24 * 60),
      config: {
        phone_number_id: commerce ? "100200300400500" : "200300400500600",
        business_account_id: commerce ? "900800700600" : "800700600500",
      },
      credentials: [
        { key: "access_token", set: true, hint: "…Zx41" },
        { key: "app_secret", set: true, hint: "…07ab" },
      ],
      scopes: ["whatsapp_business_messaging", "whatsapp_business_management"],
      health_detail: {
        latency_ms: 940,
        consecutive_failures: 3,
        rate_limited_until: ahead(22),
      },
      behavior: "rate_limited",
      recent_activity: [
        {
          at: ago(9),
          kind: "send",
          outcome: "failure",
          message: "Send throttled by provider (HTTP 429)",
        },
        {
          at: ago(21),
          kind: "circuit",
          outcome: "warning",
          message: "Circuit half-open after 3 consecutive failures",
        },
        {
          at: ago(52),
          kind: "send",
          outcome: "success",
          message: "Message accepted by provider",
        },
        {
          at: ago(60 * 24 * 60),
          kind: "created",
          outcome: "success",
          message: "Connection created by Amina Rahman",
        },
      ],
    }),
    base(profile, smtpId, {
      integration_key: "smtp",
      display_name: commerce ? "Transactional email" : "Studio mailer",
      status: "disabled",
      health: "unknown",
      last_success_at: ago(60 * 24 * 12),
      last_health_check_at: ago(60 * 24 * 12),
      connected_at: ago(60 * 24 * 90),
      config: {
        host: "smtp.mail.example.net",
        port: 587,
        security: "starttls",
        from_address: commerce
          ? "billing@northwind.example"
          : "hello@brightline.example",
        username: commerce ? "northwind-billing" : "brightline",
      },
      credentials: [{ key: "password", set: true, hint: "…k2Lp" }],
      recent_activity: [
        {
          at: ago(60 * 24 * 11),
          kind: "disabled",
          outcome: "info",
          message: "Disabled by Amina Rahman",
        },
        {
          at: ago(60 * 24 * 90),
          kind: "created",
          outcome: "success",
          message: "Connection created by Amina Rahman",
        },
      ],
    }),
  ];

  if (commerce) {
    connections.push(
      base(profile, "con-nw-shop", {
        integration_key: "shopify",
        display_name: "Storefront (development store)",
        status: "connected",
        mode: "sandbox",
        last_success_at: ago(3),
        last_health_check_at: ago(40),
        connected_at: ago(60 * 24 * 14),
        config: { shop_domain: "northwind-dev.myshopify.com" },
        scopes: ["read_products", "read_orders", "read_customers"],
        sync_direction: "pull",
        health_detail: {
          latency_ms: 310,
          consecutive_failures: 0,
          rate_limited_until: null,
        },
        recent_activity: [
          {
            at: ago(3),
            kind: "sync",
            outcome: "info",
            message: "Orders sync started",
          },
          {
            at: ago(60 * 5),
            kind: "sync",
            outcome: "failure",
            message: "Customers sync failed: 4 records rejected",
          },
          {
            at: ago(60 * 24 * 14),
            kind: "oauth",
            outcome: "success",
            message: "Authorized by Amina Rahman",
          },
        ],
      }),
      base(profile, "con-nw-oldhook", {
        integration_key: "generic_webhook",
        display_name: "Legacy automation hook",
        status: "revoked",
        health: "unknown",
        last_success_at: ago(60 * 24 * 70),
        connected_at: ago(60 * 24 * 200),
        config: { url: "https://legacy-automation.example.com/hook" },
        credentials: [{ key: "signing_secret", set: false, hint: null }],
        recent_activity: [
          {
            at: ago(60 * 24 * 65),
            kind: "disconnected",
            outcome: "info",
            message: "Disconnected; credentials revoked",
          },
        ],
      }),
    );
  }

  const events: InboundEvent[] = [];
  const waTypes = [
    "message.received",
    "message.status.delivered",
    "message.status.read",
    "message.status.sent",
  ];
  for (let i = 0; i < (commerce ? 16 : 7); i += 1) {
    events.push({
      id: `evt-${p}-${i}`,
      connection_id: waId,
      integration_key: "whatsapp_meta",
      provider_event_id: `wamid.${hex(r, 16)}`,
      event_type: r.pick(waTypes),
      status: "processed",
      signature_verified: true,
      attempt_count: 1,
      received_at: ago(15 + i * 37),
      processed_at: ago(15 + i * 37 - 0.05),
      error_code: null,
      correlation_id: `corr-${hex(r, 12)}`,
    });
  }
  events.unshift(
    {
      id: `evt-${p}-queued`,
      connection_id: waId,
      integration_key: "whatsapp_meta",
      provider_event_id: `wamid.${hex(r, 16)}`,
      event_type: "message.received",
      status: "queued",
      signature_verified: true,
      attempt_count: 0,
      received_at: ago(1),
      processed_at: null,
      error_code: null,
      correlation_id: `corr-${hex(r, 12)}`,
    },
    {
      id: `evt-${p}-failed`,
      connection_id: waId,
      integration_key: "whatsapp_meta",
      provider_event_id: `wamid.${hex(r, 16)}`,
      event_type: "message.received",
      status: "failed",
      signature_verified: true,
      attempt_count: 2,
      received_at: ago(11),
      processed_at: null,
      error_code: "CUSTOMER_MATCH_FAILED",
      correlation_id: `corr-${hex(r, 12)}`,
    },
    {
      id: `evt-${p}-dead`,
      connection_id: waId,
      integration_key: "whatsapp_meta",
      provider_event_id: `wamid.${hex(r, 16)}`,
      event_type: "message.status.failed",
      status: "dead_letter",
      signature_verified: true,
      attempt_count: 5,
      received_at: ago(95),
      processed_at: null,
      error_code: "HANDLER_TIMEOUT",
      correlation_id: `corr-${hex(r, 12)}`,
    },
    {
      id: `evt-${p}-unsigned`,
      connection_id: waId,
      integration_key: "whatsapp_meta",
      provider_event_id: null,
      event_type: "message.received",
      status: "ignored",
      signature_verified: false,
      attempt_count: 1,
      received_at: ago(140),
      processed_at: ago(140),
      error_code: "SIGNATURE_INVALID",
      correlation_id: null,
    },
  );
  if (commerce) {
    for (let i = 0; i < 6; i += 1) {
      events.push({
        id: `evt-nw-shop-${i}`,
        connection_id: "con-nw-shop",
        integration_key: "shopify",
        provider_event_id: `${r.int(100000, 999999)}`,
        event_type: r.pick([
          "orders/create",
          "orders/updated",
          "products/update",
        ]),
        status: "processed",
        signature_verified: true,
        attempt_count: 1,
        received_at: ago(30 + i * 90),
        processed_at: ago(30 + i * 90 - 0.1),
        error_code: null,
        correlation_id: `corr-${hex(r, 12)}`,
      });
    }
  }
  events.sort((a, b) => b.received_at.localeCompare(a.received_at));

  const webhooks: WebhookSubscription[] = [
    {
      id: `whk-${p}-ops`,
      name: commerce ? "Fulfilment sync" : "Project board updates",
      url: commerce
        ? "https://ops.fulfilment-partner.example/webhooks/northwind"
        : "https://board.example.org/incoming/brightline",
      event_types: commerce
        ? ["order.confirmed", "order.cancelled"]
        : ["quote.approved", "customer.created"],
      enabled: true,
      secret_hint: "…c7d1",
      last_delivery_at: ago(26),
      last_delivery_status: "succeeded",
      failure_count: 0,
      created_at: ago(60 * 24 * 30),
      updated_at: ago(60 * 24 * 30),
    },
  ];
  const deliveries: Delivery[] = [];
  for (let i = 0; i < 6; i += 1) {
    deliveries.push({
      id: `dlv-${p}-ops-${i}`,
      subscription_id: `whk-${p}-ops`,
      event_type: webhooks[0]!.event_types[i % 2]!,
      event_id: `evt_${hex(r, 10)}`,
      status: "succeeded",
      attempt_count: i === 2 ? 2 : 1,
      response_status: 200,
      last_error: null,
      next_attempt_at: null,
      created_at: ago(26 + i * 180),
      delivered_at: ago(26 + i * 180 - 0.02),
    });
  }
  if (commerce) {
    webhooks.push({
      id: "whk-nw-ledger",
      name: "Accounting export",
      url: "https://books.example.net/hooks/northwind",
      event_types: ["invoice.issued", "invoice.paid"],
      enabled: true,
      secret_hint: "…41e0",
      last_delivery_at: ago(7),
      last_delivery_status: "failed",
      failure_count: 2,
      created_at: ago(60 * 24 * 21),
      updated_at: ago(60 * 24 * 21),
    });
    deliveries.push(
      {
        id: "dlv-nw-ledger-fail",
        subscription_id: "whk-nw-ledger",
        event_type: "invoice.paid",
        event_id: `evt_${hex(r, 10)}`,
        status: "failed",
        attempt_count: 3,
        response_status: 503,
        last_error: "Endpoint returned HTTP 503 Service Unavailable",
        next_attempt_at: ahead(12),
        created_at: ago(7),
        delivered_at: null,
      },
      {
        id: "dlv-nw-ledger-dead",
        subscription_id: "whk-nw-ledger",
        event_type: "invoice.issued",
        event_id: `evt_${hex(r, 10)}`,
        status: "dead_letter",
        attempt_count: 8,
        response_status: null,
        last_error: "Connection timed out after 10 s",
        next_attempt_at: null,
        created_at: ago(60 * 26),
        delivered_at: null,
      },
      {
        id: "dlv-nw-ledger-ok",
        subscription_id: "whk-nw-ledger",
        event_type: "invoice.issued",
        event_id: `evt_${hex(r, 10)}`,
        status: "succeeded",
        attempt_count: 1,
        response_status: 204,
        last_error: null,
        next_attempt_at: null,
        created_at: ago(60 * 30),
        delivered_at: ago(60 * 30 - 0.02),
      },
    );
  }
  deliveries.sort((a, b) => b.created_at.localeCompare(a.created_at));

  const stats = (
    discovered: number,
    created: number,
    updated: number,
    failed = 0,
  ) => ({
    discovered,
    created,
    updated,
    skipped: discovered - created - updated - failed,
    failed,
    conflicts: 0,
  });
  const jobs: SyncJob[] = commerce
    ? [
        {
          id: "job-nw-orders-run",
          connection_id: "con-nw-shop",
          integration_key: "shopify",
          entity: "orders",
          direction: "pull",
          mode: "incremental",
          status: "running",
          cursor: "page_info=eyJsYXN0X2lkIjo0MTA",
          stats: stats(64, 12, 30),
          started_at: ago(3),
          finished_at: null,
          last_error: null,
          created_at: ago(3),
        },
        {
          id: "job-nw-customers-fail",
          connection_id: "con-nw-shop",
          integration_key: "shopify",
          entity: "customers",
          direction: "pull",
          mode: "incremental",
          status: "failed",
          cursor: null,
          stats: stats(120, 18, 90, 4),
          started_at: ago(60 * 5),
          finished_at: ago(60 * 5 - 2),
          last_error:
            "4 customers were rejected: phone numbers are not in international format.",
          created_at: ago(60 * 5),
        },
        {
          id: "job-nw-products-paused",
          connection_id: "con-nw-shop",
          integration_key: "shopify",
          entity: "products",
          direction: "pull",
          mode: "incremental",
          status: "paused",
          cursor: "updated_at_min=2026-09-20",
          stats: stats(40, 0, 11),
          started_at: ago(60 * 20),
          finished_at: null,
          last_error: null,
          created_at: ago(60 * 20),
        },
        {
          id: "job-nw-products-full",
          connection_id: "con-nw-shop",
          integration_key: "shopify",
          entity: "products",
          direction: "pull",
          mode: "full",
          status: "succeeded",
          cursor: null,
          stats: stats(212, 180, 20),
          started_at: ago(60 * 24 * 2),
          finished_at: ago(60 * 24 * 2 - 6),
          last_error: null,
          created_at: ago(60 * 24 * 2),
        },
        {
          id: "job-nw-orders-queued",
          connection_id: "con-nw-shop",
          integration_key: "shopify",
          entity: "orders",
          direction: "pull",
          mode: "full",
          status: "pending",
          cursor: null,
          stats: stats(0, 0, 0),
          started_at: null,
          finished_at: null,
          last_error: null,
          created_at: ago(1),
        },
      ]
    : [];

  const apiKeys: ApiKey[] = commerce
    ? [
        {
          id: "key-nw-scanner",
          name: "Warehouse scanner app",
          prefix: "pk_live_7c21ab",
          scopes: ["catalog.read", "inventory.read", "inventory.adjust"],
          created_at: ago(60 * 24 * 45),
          expires_at: null,
          last_used_at: ago(120),
          revoked_at: null,
          created_by_name: "Amina Rahman",
        },
        {
          id: "key-nw-dash",
          name: "Reporting dashboard",
          prefix: "pk_live_19fe04",
          scopes: ["reports.read"],
          created_at: ago(60 * 24 * 70),
          expires_at: ahead(60 * 24 * 20),
          last_used_at: ago(60 * 24),
          revoked_at: null,
          created_by_name: "Amina Rahman",
        },
        {
          id: "key-nw-old",
          name: "Old BI export",
          prefix: "pk_live_03aa9d",
          scopes: ["orders.read", "customers.read"],
          created_at: ago(60 * 24 * 200),
          expires_at: null,
          last_used_at: ago(60 * 24 * 95),
          revoked_at: ago(60 * 24 * 90),
          created_by_name: "Amina Rahman",
        },
      ]
    : [
        {
          id: "key-bl-site",
          name: "Website contact form",
          prefix: "pk_live_5b8e10",
          scopes: ["customers.write"],
          created_at: ago(60 * 24 * 20),
          expires_at: null,
          last_used_at: ago(300),
          revoked_at: null,
          created_by_name: "Amina Rahman",
        },
      ];

  return { connections, webhooks, deliveries, events, jobs, apiKeys };
}

export const demoIntegrations = demoCollection("integrations", seed);
