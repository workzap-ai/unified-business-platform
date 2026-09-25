import { z } from "zod";
import { apiRequest, pageSchema, type Page } from "@/services/api-client";
import { select } from "@/lib/data-mode";
import { demoIntegrationsService } from "./demo-adapter";
import {
  apiKeyCreatedSchema,
  apiKeySchema,
  connectionDetailSchema,
  connectionSchema,
  definitionSchema,
  deliverySchema,
  eventTypeSchema,
  failureSchema,
  healthSchema,
  inboundEventSchema,
  syncJobSchema,
  testResultSchema,
  webhookSubscriptionCreatedSchema,
  webhookSubscriptionSchema,
  type ApiKey,
  type ApiKeyCreated,
  type ApiKeyInput,
  type Connection,
  type ConnectionDetail,
  type ConnectionInput,
  type ConnectionPatch,
  type Delivery,
  type EventType,
  type Failure,
  type InboundEvent,
  type IntegrationDefinition,
  type IntegrationHealth,
  type JobAction,
  type ListQuery,
  type SyncJob,
  type TestResult,
  type WebhookInput,
  type WebhookSubscription,
  type WebhookSubscriptionCreated,
} from "./types";

/** One contract, two adapters (docs/contracts/integrations-api.md). */
export interface IntegrationsService {
  definitions(): Promise<IntegrationDefinition[]>;
  connections(
    query: ListQuery & { integration_key?: string; status?: string },
  ): Promise<Page<Connection>>;
  connection(id: string): Promise<ConnectionDetail>;
  createConnection(input: ConnectionInput): Promise<Connection>;
  updateConnection(
    id: string,
    patch: ConnectionPatch,
  ): Promise<ConnectionDetail>;
  rotateCredentials(
    id: string,
    credentials: Record<string, string>,
  ): Promise<ConnectionDetail>;
  testConnection(id: string): Promise<TestResult>;
  enableConnection(id: string): Promise<ConnectionDetail>;
  disableConnection(id: string): Promise<ConnectionDetail>;
  disconnect(id: string): Promise<void>;
  startOAuth(id: string): Promise<{ authorization_url: string }>;
  eventTypes(): Promise<EventType[]>;
  webhooks(query: ListQuery): Promise<Page<WebhookSubscription>>;
  createWebhook(input: WebhookInput): Promise<WebhookSubscriptionCreated>;
  updateWebhook(
    id: string,
    patch: Partial<WebhookInput>,
  ): Promise<WebhookSubscription>;
  rotateWebhookSecret(id: string): Promise<WebhookSubscriptionCreated>;
  deleteWebhook(id: string): Promise<void>;
  deliveries(subscriptionId: string, query: ListQuery): Promise<Page<Delivery>>;
  retryDelivery(id: string): Promise<Delivery>;
  events(
    query: ListQuery & {
      connection_id?: string;
      status?: string;
      event_type?: string;
    },
  ): Promise<Page<InboundEvent>>;
  replayEvent(id: string): Promise<InboundEvent>;
  jobs(
    query: ListQuery & { connection_id?: string; status?: string },
  ): Promise<Page<SyncJob>>;
  startSync(
    connectionId: string,
    input: { entity: string; mode: "incremental" | "full" },
  ): Promise<SyncJob>;
  jobAction(id: string, action: JobAction): Promise<SyncJob>;
  failures(query: ListQuery): Promise<Page<Failure>>;
  health(): Promise<IntegrationHealth>;
  apiKeys(): Promise<ApiKey[]>;
  createApiKey(input: ApiKeyInput): Promise<ApiKeyCreated>;
  revokeApiKey(id: string): Promise<void>;
}

const P = "/integrations";
const paging = ({ page = 1, pageSize = 25 }: ListQuery) => ({
  page,
  page_size: Math.min(100, pageSize),
});

const live: IntegrationsService = {
  definitions: () =>
    apiRequest("GET", `${P}/definitions`, z.array(definitionSchema)),
  connections: ({ integration_key, status, ...q }) =>
    apiRequest("GET", `${P}/connections`, pageSchema(connectionSchema), {
      query: { ...paging(q), integration_key, status },
    }),
  connection: (id) =>
    apiRequest("GET", `${P}/connections/${id}`, connectionDetailSchema),
  createConnection: (input) =>
    apiRequest("POST", `${P}/connections`, connectionSchema, { body: input }),
  updateConnection: (id, patch) =>
    apiRequest("PATCH", `${P}/connections/${id}`, connectionDetailSchema, {
      body: patch,
    }),
  rotateCredentials: (id, credentials) =>
    apiRequest(
      "PUT",
      `${P}/connections/${id}/credentials`,
      connectionDetailSchema,
      { body: { credentials } },
    ),
  testConnection: (id) =>
    apiRequest("POST", `${P}/connections/${id}/test`, testResultSchema),
  enableConnection: (id) =>
    apiRequest("POST", `${P}/connections/${id}/enable`, connectionDetailSchema),
  disableConnection: (id) =>
    apiRequest(
      "POST",
      `${P}/connections/${id}/disable`,
      connectionDetailSchema,
    ),
  disconnect: (id) => apiRequest("DELETE", `${P}/connections/${id}`, null),
  startOAuth: (id) =>
    apiRequest(
      "POST",
      `${P}/connections/${id}/oauth/start`,
      z.object({ authorization_url: z.string().url() }),
    ),
  eventTypes: () =>
    apiRequest("GET", `${P}/event-types`, z.array(eventTypeSchema)),
  webhooks: (q) =>
    apiRequest("GET", `${P}/webhooks`, pageSchema(webhookSubscriptionSchema), {
      query: paging(q),
    }),
  createWebhook: (input) =>
    apiRequest("POST", `${P}/webhooks`, webhookSubscriptionCreatedSchema, {
      body: input,
    }),
  updateWebhook: (id, patch) =>
    apiRequest("PATCH", `${P}/webhooks/${id}`, webhookSubscriptionSchema, {
      body: patch,
    }),
  rotateWebhookSecret: (id) =>
    apiRequest(
      "POST",
      `${P}/webhooks/${id}/rotate-secret`,
      webhookSubscriptionCreatedSchema,
    ),
  deleteWebhook: (id) => apiRequest("DELETE", `${P}/webhooks/${id}`, null),
  deliveries: (id, q) =>
    apiRequest(
      "GET",
      `${P}/webhooks/${id}/deliveries`,
      pageSchema(deliverySchema),
      {
        query: paging(q),
      },
    ),
  retryDelivery: (id) =>
    apiRequest("POST", `${P}/deliveries/${id}/retry`, deliverySchema),
  events: ({ connection_id, status, event_type, ...q }) =>
    apiRequest("GET", `${P}/events`, pageSchema(inboundEventSchema), {
      query: { ...paging(q), connection_id, status, event_type },
    }),
  replayEvent: (id) =>
    apiRequest("POST", `${P}/events/${id}/replay`, inboundEventSchema),
  jobs: ({ connection_id, status, ...q }) =>
    apiRequest("GET", `${P}/jobs`, pageSchema(syncJobSchema), {
      query: { ...paging(q), connection_id, status },
    }),
  startSync: (id, input) =>
    apiRequest("POST", `${P}/connections/${id}/sync`, syncJobSchema, {
      body: input,
    }),
  jobAction: (id, action) =>
    apiRequest("POST", `${P}/jobs/${id}/${action}`, syncJobSchema),
  failures: (q) =>
    apiRequest("GET", `${P}/failures`, pageSchema(failureSchema), {
      query: paging(q),
    }),
  health: () => apiRequest("GET", `${P}/health`, healthSchema),
  apiKeys: () => apiRequest("GET", `${P}/api-keys`, z.array(apiKeySchema)),
  createApiKey: (input) =>
    apiRequest("POST", `${P}/api-keys`, apiKeyCreatedSchema, { body: input }),
  revokeApiKey: (id) => apiRequest("DELETE", `${P}/api-keys/${id}`, null),
};

export const integrationsService = select<IntegrationsService>({
  demo: demoIntegrationsService,
  live,
});
