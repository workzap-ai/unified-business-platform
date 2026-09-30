"use client";

import * as React from "react";
import { ExternalLink, Phone, Plus, RefreshCw } from "lucide-react";
import { ErrorState, Notice } from "@/components/app/states";
import { Button } from "@/components/ui/button";
import { Badge, Card, Skeleton } from "@/components/ui/display";
import { Input, NativeSelect } from "@/components/ui/input";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/overlays";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { apiRequest } from "@/services/api-client";
import { OperatorShell } from "./operator-pages";
import type { OperatorMe } from "./service";

interface PoolRow {
  id: string;
  phone_number_id: string;
  display_phone_number: string;
  country: string;
  price_label: string;
  status: "available" | "reserved" | "assigned" | "retired";
  quality_rating: string | null;
  display_name_status: string;
  warnings: string[];
  webhook_status: string;
  notes: string;
  assigned_tenant_id: string | null;
}
interface KapsoNumber {
  phone_number_id: string;
  display_phone_number: string;
  in_pool: boolean;
  pool_status: string | null;
  warnings: string[];
  used_by: { tenant_id: string } | null;
}
interface Inventory {
  pool: PoolRow[];
  numbers: KapsoNumber[];
  billing_mode: string;
  webhook_url: string | null;
}
interface WorkspaceOption {
  id: string;
  name: string;
  kind: string;
}

// Numbers that can't be given to anyone until fixed (sandbox numbers can, for testing).
const BLOCKING = ["meta_test_number", "quality_red", "inbound_processing_off"];

const WARNING: Record<string, string> = {
  meta_test_number:
    "Meta test number: stops after ~5 messages. Delete it in Kapso and use a verified number.",
  display_name_not_approved: "Display name not approved by Meta yet",
  quality_red: "Quality RED",
  quality_yellow: "Quality YELLOW",
  inbound_processing_off: "Inbound processing is off in Kapso",
  sandbox: "Sandbox number: for testing only",
  default_customer:
    "In another Kapso customer: can't join the pool through the API",
  no_customer: "Not linked to a Kapso customer",
};

const api = {
  inventory: () => apiRequest<Inventory>("GET", "/operator/pi/numbers", null),
  connect: (body: Record<string, string>) =>
    apiRequest<PoolRow>("POST", "/operator/pi/numbers/connect", null, { body }),
  provision: (country: string) =>
    apiRequest<{ setup_url: string }>(
      "POST",
      "/operator/pi/numbers/provision",
      null,
      {
        body: { country },
      },
    ),
  update: (id: string, body: Record<string, string>) =>
    apiRequest<PoolRow>("PATCH", `/operator/pi/numbers/${id}`, null, { body }),
  offer: (id: string, tenantId: string) =>
    apiRequest<PoolRow>("POST", `/operator/pi/numbers/${id}/offer`, null, {
      body: { tenant_id: tenantId },
    }),
  withdraw: (id: string) =>
    apiRequest<PoolRow>("POST", `/operator/pi/numbers/${id}/withdraw`, null, {
      body: {},
    }),
  workspaces: () =>
    apiRequest<{ items: WorkspaceOption[] }>(
      "GET",
      "/operator/workspaces",
      null,
      {
        query: { page_size: 100 },
      },
    ),
  workspaceWhatsapp: (tenantId: string) =>
    apiRequest<WorkspaceWhatsApp>(
      "GET",
      `/operator/workspaces/${tenantId}/whatsapp`,
      null,
    ),
  workspaceHealth: (tenantId: string) =>
    apiRequest<WorkspaceWhatsApp>(
      "POST",
      `/operator/workspaces/${tenantId}/whatsapp/health`,
      null,
      {
        body: {},
      },
    ),
  usage: () =>
    apiRequest<WhatsAppUsage>("GET", "/operator/pi/whatsapp-usage", null),
  setup: () => apiRequest<PlatformSetup>("GET", "/operator/pi/setup", null),
};

const STATUS_TONE: Record<
  PoolRow["status"],
  "success" | "info" | "primary" | "neutral"
> = {
  available: "success",
  reserved: "info",
  assigned: "primary",
  retired: "neutral",
};

export function OperatorNumbersPage() {
  return (
    <OperatorShell
      title="WhatsApp numbers"
      description="The platform's Kapso number pool. Businesses and workspaces choose from here, or you set a number aside for one."
    >
      {(me) => <Numbers me={me} />}
    </OperatorShell>
  );
}

function Numbers({ me }: { me: OperatorMe }) {
  const canManage = me.capabilities.includes("operator.numbers.manage");
  const inventory = useScopedQuery(["operator", "numbers"], api.inventory, {
    retry: false,
  });
  const [connecting, setConnecting] = React.useState(false);
  const [offering, setOffering] = React.useState<PoolRow | null>(null);
  const [country, setCountry] = React.useState("US");
  const invalidate = [["operator", "numbers"]];
  const provision = useScopedMutation(() => api.provision(country), {
    onSuccess: (r) => window.open(r.setup_url, "_blank", "noopener"),
  });
  const update = useScopedMutation(
    ({ id, body }: { id: string; body: Record<string, string> }) =>
      api.update(id, body),
    { invalidate, success: "Saved" },
  );
  const withdraw = useScopedMutation((id: string) => api.withdraw(id), {
    invalidate,
    success: "Offer withdrawn",
  });
  if (inventory.isPending) return <Skeleton className="h-64 rounded-xl" />;
  if (inventory.isError)
    return (
      <Card>
        <ErrorState
          error={inventory.error}
          onRetry={() => void inventory.refetch()}
        />
      </Card>
    );
  const inv = inventory.data;
  const outside = inv.numbers.filter((n) => !n.in_pool);
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="secondary"
          size="sm"
          onClick={() => void inventory.refetch()}
        >
          <RefreshCw /> Sync from Kapso
        </Button>
        {canManage ? (
          <>
            <NativeSelect
              aria-label="Country for a new number"
              value={country}
              onChange={(e) => setCountry(e.target.value)}
              className="h-8 w-28"
            >
              <option value="US">US</option>
            </NativeSelect>
            <Button
              size="sm"
              loading={provision.isPending}
              onClick={() => provision.mutate(undefined)}
            >
              <Plus /> New number from Kapso <ExternalLink />
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setConnecting(true)}
            >
              Connect a number we own
            </Button>
          </>
        ) : null}
        <span className="ms-auto text-[12px] text-muted-foreground">
          WhatsApp fees:{" "}
          {inv.billing_mode === "partner_managed"
            ? "Kapso credits (platform pays)"
            : "each business pays Meta"}
        </span>
      </div>
      {!inv.webhook_url ? (
        <Notice tone="warning" title="Webhooks can't be set up automatically">
          Set INTEGRATIONS_PUBLIC_BASE_URL to the API&apos;s public https://
          address so each number sends messages to Pi.
        </Notice>
      ) : null}
      <Card className="overflow-hidden">
        {!inv.pool.length ? (
          <div className="p-6 text-[13px] text-muted-foreground">
            The pool is empty. Add a new number from Kapso or connect one you
            own.
          </div>
        ) : (
          <ul className="divide-y divide-border">
            {inv.pool.map((n) => (
              <li key={n.id} className="space-y-2 px-4 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Phone className="size-4 text-muted-foreground" aria-hidden />
                  <span className="font-medium tabular-nums">
                    {n.display_phone_number}
                  </span>
                  <Badge tone={STATUS_TONE[n.status]}>{n.status}</Badge>
                  {n.quality_rating ? (
                    <Badge tone="outline">
                      quality {n.quality_rating.toLowerCase()}
                    </Badge>
                  ) : null}
                  {n.webhook_status === "failed" ? (
                    <Badge tone="danger">webhook failed</Badge>
                  ) : null}
                  <span className="flex-1" />
                  {canManage &&
                  n.status === "available" &&
                  !n.warnings.some((w) => BLOCKING.includes(w)) ? (
                    <Button
                      size="xs"
                      variant="secondary"
                      onClick={() => setOffering(n)}
                    >
                      Offer to…
                    </Button>
                  ) : null}
                  {canManage && n.status === "reserved" ? (
                    <Button
                      size="xs"
                      variant="secondary"
                      loading={withdraw.isPending}
                      onClick={() => withdraw.mutate(n.id)}
                    >
                      Withdraw offer
                    </Button>
                  ) : null}
                  {canManage && n.status === "available" ? (
                    <Button
                      size="xs"
                      variant="danger-outline"
                      onClick={() =>
                        update.mutate({ id: n.id, body: { status: "retired" } })
                      }
                    >
                      Retire
                    </Button>
                  ) : null}
                </div>
                {n.warnings.length ? (
                  <ul className="space-y-0.5 text-[12px] text-warning">
                    {n.warnings.map((w) => (
                      <li key={w}>⚠ {WARNING[w] ?? w}</li>
                    ))}
                  </ul>
                ) : null}
                {canManage && n.status !== "retired" ? (
                  <PoolLabels
                    row={n}
                    onSave={(body) => update.mutate({ id: n.id, body })}
                  />
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </Card>
      {outside.length ? (
        <Card className="p-4">
          <h2 className="mb-2 text-[15px] font-semibold">
            Other numbers in the Kapso project
          </h2>
          <ul className="space-y-1 text-[13px]">
            {outside.map((n) => (
              <li key={n.phone_number_id}>
                <span className="tabular-nums">{n.display_phone_number}</span>{" "}
                <span className="text-muted-foreground">
                  {n.used_by
                    ? "· connected to a workspace"
                    : "· not used by Pi"}
                  {n.warnings.map((w) => ` · ${WARNING[w] ?? w}`).join("")}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
      <ConnectDialog open={connecting} onOpenChange={setConnecting} />
      <OfferDialog
        row={offering}
        onOpenChange={(o) => !o && setOffering(null)}
      />
    </div>
  );
}

function PoolLabels({
  row,
  onSave,
}: {
  row: PoolRow;
  onSave: (body: Record<string, string>) => void;
}) {
  const [price, setPrice] = React.useState(row.price_label);
  const [country, setCountry] = React.useState(row.country);
  const dirty = price !== row.price_label || country !== row.country;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Input
        aria-label="Country code"
        className="h-8 w-20"
        maxLength={2}
        value={country}
        onChange={(e) => setCountry(e.target.value.toUpperCase())}
      />
      <Input
        aria-label="Price shown to businesses"
        placeholder="Price shown to businesses, e.g. Included in Growth"
        className="h-8 max-w-sm flex-1"
        maxLength={80}
        value={price}
        onChange={(e) => setPrice(e.target.value)}
      />
      {dirty ? (
        <Button
          size="xs"
          onClick={() => onSave({ price_label: price, country })}
        >
          Save
        </Button>
      ) : null}
    </div>
  );
}

function ConnectDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
}) {
  const [form, setForm] = React.useState({
    phone_number_id: "",
    business_account_id: "",
    access_token: "",
    country: "",
  });
  const connect = useScopedMutation(() => api.connect(form), {
    invalidate: [["operator", "numbers"]],
    success: "Number added to the pool",
    onSuccess: () => {
      setForm({
        phone_number_id: "",
        business_account_id: "",
        access_token: "",
        country: "",
      });
      onOpenChange(false);
    },
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader
          title="Connect a number we own"
          description="Uses a permanent System User token from Meta Business Settings. It is sent to Kapso once and never stored by Pi."
        />
        <DialogBody className="grid gap-3">
          <Input
            aria-label="Phone number ID"
            placeholder="Phone number ID"
            inputMode="numeric"
            value={form.phone_number_id}
            onChange={(e) =>
              setForm({ ...form, phone_number_id: e.target.value.trim() })
            }
          />
          <Input
            aria-label="WhatsApp Business Account ID"
            placeholder="WhatsApp Business Account ID"
            inputMode="numeric"
            value={form.business_account_id}
            onChange={(e) =>
              setForm({ ...form, business_account_id: e.target.value.trim() })
            }
          />
          <Input
            aria-label="Permanent access token"
            placeholder="Permanent System User token"
            type="password"
            autoComplete="off"
            value={form.access_token}
            onChange={(e) => setForm({ ...form, access_token: e.target.value })}
          />
          <Input
            aria-label="Country code"
            placeholder="Country (e.g. US)"
            maxLength={2}
            value={form.country}
            onChange={(e) =>
              setForm({ ...form, country: e.target.value.toUpperCase() })
            }
          />
        </DialogBody>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            loading={connect.isPending}
            disabled={
              !/^\d{5,32}$/.test(form.phone_number_id) ||
              !/^\d{5,32}$/.test(form.business_account_id) ||
              form.access_token.trim().length < 40
            }
            onClick={() => connect.mutate(undefined)}
          >
            Add to pool
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function OfferDialog({
  row,
  onOpenChange,
}: {
  row: PoolRow | null;
  onOpenChange: (o: boolean) => void;
}) {
  const workspaces = useScopedQuery(
    ["operator", "workspace-options"],
    api.workspaces,
    {
      enabled: Boolean(row),
    },
  );
  const [tenant, setTenant] = React.useState("");
  const offer = useScopedMutation(() => api.offer(row!.id, tenant), {
    invalidate: [["operator", "numbers"]],
    success: "Offered. They'll see it on their WhatsApp page and accept it.",
    onSuccess: () => {
      setTenant("");
      onOpenChange(false);
    },
  });
  return (
    <Dialog open={Boolean(row)} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader
          title={`Offer ${row?.display_phone_number ?? ""}`}
          description="Set this number aside for one business or workspace. They accept it themselves."
        />
        <DialogBody>
          <NativeSelect
            aria-label="Business or workspace"
            value={tenant}
            onChange={(e) => setTenant(e.target.value)}
          >
            <option value="">Choose a business or workspace</option>
            {(workspaces.data?.items ?? []).map((w) => (
              <option key={w.id} value={w.id}>
                {w.name} ({w.kind === "pi" ? "Pi business" : "Owner OS"})
              </option>
            ))}
          </NativeSelect>
        </DialogBody>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={!tenant}
            loading={offer.isPending}
            onClick={() => offer.mutate(undefined)}
          >
            Offer number
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------- workspace panel

interface WorkspaceWhatsApp {
  connection: {
    status: string;
    display_phone_number?: string | null;
    connection_type?: string | null;
    health?: { status?: string } | null;
    problem?: string | null;
  };
  numbers: {
    provider: string;
    display_phone_number: string;
    status: string;
    last_error_code: string | null;
  }[];
  pool: PoolRow[];
}

export function WorkspaceWhatsAppDialog({
  tenant,
  onOpenChange,
}: {
  tenant: { id: string; name: string } | null;
  onOpenChange: (open: boolean) => void;
}) {
  const panel = useScopedQuery(
    ["operator", "workspace-whatsapp", tenant?.id ?? ""],
    () => api.workspaceWhatsapp(tenant!.id),
    { enabled: Boolean(tenant) },
  );
  const health = useScopedMutation(() => api.workspaceHealth(tenant!.id), {
    invalidate: [["operator", "workspace-whatsapp", tenant?.id ?? ""]],
    success: "Health checked",
  });
  const p = panel.data;
  return (
    <Dialog open={Boolean(tenant)} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader
          title={`WhatsApp · ${tenant?.name ?? ""}`}
          description="Number, provider and health. Offer a pool number from the Numbers page."
        />
        <DialogBody className="space-y-3 text-[13px]">
          {!p ? (
            <Skeleton className="h-24 rounded-lg" />
          ) : (
            <>
              <p>
                Status:{" "}
                <Badge
                  tone={
                    p.connection.status === "connected" ? "success" : "neutral"
                  }
                >
                  {p.connection.status}
                </Badge>{" "}
                {p.connection.display_phone_number ?? ""}
                {p.connection.health?.status
                  ? ` · health ${p.connection.health.status}`
                  : ""}
                {p.connection.problem ? ` · ${p.connection.problem}` : ""}
              </p>
              {p.numbers.length ? (
                <ul className="space-y-1">
                  {p.numbers.map((n) => (
                    <li key={`${n.provider}-${n.display_phone_number}`}>
                      {n.display_phone_number} ·{" "}
                      {n.provider === "kapso" ? "Kapso" : "Meta"} · {n.status}
                      {n.last_error_code ? ` · ${n.last_error_code}` : ""}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-muted-foreground">No WhatsApp number yet.</p>
              )}
              {p.pool.length ? (
                <p>
                  Pool:{" "}
                  {p.pool
                    .map((r) => `${r.display_phone_number} (${r.status})`)
                    .join(", ")}
                </p>
              ) : null}
            </>
          )}
        </DialogBody>
        <DialogFooter>
          <Button
            variant="secondary"
            loading={health.isPending}
            disabled={p?.connection.status !== "connected"}
            onClick={() => health.mutate(undefined)}
          >
            Check health
          </Button>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------- overview cards

interface WhatsAppUsage {
  period: string;
  billing_mode: string;
  totals: Record<"messages_in" | "messages_out" | "template_messages", number>;
  businesses: {
    tenant_id: string;
    name: string;
    messages_in: number;
    messages_out: number;
    template_messages: number;
  }[];
  kapso_dashboard: string;
}
interface PlatformSetup {
  checks: { key: string; label: string; ok: boolean; fix: string }[];
  ready: boolean;
}

export function WhatsAppUsageCard() {
  const usage = useScopedQuery(["operator", "whatsapp-usage"], api.usage, {
    retry: false,
  });
  if (!usage.data) return null;
  const u = usage.data;
  return (
    <Card className="p-4">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <h2 className="text-[15px] font-semibold">WhatsApp this month</h2>
        <span className="text-[12px] text-muted-foreground">
          {u.billing_mode === "partner_managed"
            ? "Fees are paid from Kapso credits"
            : "Businesses pay Meta directly"}
        </span>
        <a
          href={u.kapso_dashboard}
          target="_blank"
          rel="noreferrer"
          className="ms-auto text-[13px] font-medium text-primary underline"
        >
          Credits balance in Kapso
        </a>
      </div>
      <p className="text-[13px]">
        {u.totals.messages_out} sent · {u.totals.template_messages} templates
        (reminders and campaigns) · {u.totals.messages_in} received
      </p>
      {u.businesses.length ? (
        <ul className="mt-2 space-y-0.5 text-[12px] text-muted-foreground">
          {u.businesses.slice(0, 8).map((b) => (
            <li key={b.tenant_id}>
              {b.name}: {b.messages_out} sent, {b.template_messages} templates
            </li>
          ))}
        </ul>
      ) : null}
    </Card>
  );
}

export function PlatformChecklistCard() {
  const setup = useScopedQuery(["operator", "platform-setup"], api.setup, {
    retry: false,
  });
  if (!setup.data) return null;
  const missing = setup.data.checks.filter((c) => !c.ok);
  return (
    <Card className="p-4">
      <h2 className="mb-2 text-[15px] font-semibold">
        Platform setup{" "}
        {missing.length ? `· ${missing.length} to do` : "· all set"}
      </h2>
      <ul className="grid gap-1 text-[13px] sm:grid-cols-2">
        {setup.data.checks.map((c) => (
          <li key={c.key} className={c.ok ? "" : "text-warning"}>
            {c.ok ? "✓" : "✗"} {c.label}
            {!c.ok && c.fix ? (
              <span className="block text-[12px] text-muted-foreground">
                {c.fix}
              </span>
            ) : null}
          </li>
        ))}
      </ul>
    </Card>
  );
}
