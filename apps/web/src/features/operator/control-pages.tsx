"use client";

import * as React from "react";
import Link from "next/link";
import {
  CheckCircle2,
  ClipboardCopy,
  KeyRound,
  Plus,
  Trash2,
  XCircle,
} from "lucide-react";
import { EmptyState, ErrorState, Notice } from "@/components/app/states";
import { Button } from "@/components/ui/button";
import { Badge, Card, Skeleton } from "@/components/ui/display";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
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

const pretty = (value: string | null | undefined) =>
  (value ?? "—").replaceAll("_", " ").replace(/^\w/, (c) => c.toUpperCase());
const when = (value: string | null | undefined) =>
  value
    ? new Date(value).toLocaleString(undefined, {
        day: "numeric",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";

// ------------------------------------------------------------------ platform keys

interface KeyItem {
  key: string;
  group: string;
  label: string;
  kind:
    | "secret"
    | "text"
    | "url"
    | "choice"
    | "number"
    | "bool"
    | "models"
    | "list";
  purpose: string;
  where: string;
  required: boolean;
  choices: string[];
  placeholder: string;
  server_only: boolean;
  testable: boolean;
  set: boolean;
  source: "dashboard" | "env" | null;
  env_set: boolean;
  hint?: string;
  value?: unknown;
}
interface KeyListing {
  groups: { key: string; label: string }[];
  items: KeyItem[];
  missing_required: string[];
  encryption_ready: boolean;
}

const MODEL_JOBS = [
  "agent",
  "router",
  "summarize",
  "vision",
  "embed",
  "transcribe",
];
const keysApi = {
  list: () => apiRequest<KeyListing>("GET", "/operator/pi/platform-keys", null),
  save: (key: string, value: unknown) =>
    apiRequest<KeyItem>("PUT", `/operator/pi/platform-keys/${key}`, null, {
      body: { value },
    }),
  remove: (key: string) =>
    apiRequest<KeyItem>("DELETE", `/operator/pi/platform-keys/${key}`, null),
  test: (key: string) =>
    apiRequest<{ ok: boolean; message: string }>(
      "POST",
      `/operator/pi/platform-keys/${key}/test`,
      null,
    ),
};

export function OperatorKeysPage() {
  return (
    <OperatorShell
      title="Platform keys"
      description="Every key the platform needs, what it's for and where to get it. Saved keys are encrypted and override the server's .env."
    >
      {(me) => <PlatformKeys me={me} />}
    </OperatorShell>
  );
}

function PlatformKeys({ me }: { me: OperatorMe }) {
  const allowed = me.capabilities.includes("operator.settings.manage");
  const listing = useScopedQuery(["operator", "platform-keys"], keysApi.list, {
    enabled: allowed,
  });
  const [copied, setCopied] = React.useState(false);
  if (!allowed)
    return (
      <EmptyState
        icon={KeyRound}
        title="Owners only"
        description="Only a super admin can see and change platform keys."
      />
    );
  if (listing.isPending) return <Skeleton className="h-64 w-full" />;
  if (listing.isError)
    return (
      <ErrorState error={listing.error} onRetry={() => listing.refetch()} />
    );
  const data = listing.data;
  const missing = data.items.filter((i) => !i.set);
  const envBlock = [
    "# Pi platform settings missing on this server",
    ...data.groups.flatMap((g) => {
      const keys = missing.filter((i) => i.group === g.key);
      return keys.length
        ? ["", `# ${g.label}`, ...keys.map((k) => `${k.key}=`)]
        : [];
    }),
  ].join("\n");
  return (
    <div className="space-y-5">
      {!data.encryption_ready ? (
        <Notice tone="danger" title="Encryption key missing">
          Set SECRETS_ENCRYPTION_KEY in the server&apos;s .env first. Secret
          keys can&apos;t be saved without it.
        </Notice>
      ) : null}
      <Card className="flex flex-wrap items-center gap-3 p-4">
        {data.missing_required.length ? (
          <XCircle className="size-5 text-danger" aria-hidden />
        ) : (
          <CheckCircle2 className="size-5 text-success" aria-hidden />
        )}
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold">
            {data.missing_required.length
              ? `${data.missing_required.length} required key(s) missing`
              : "Every required key is set"}
          </p>
          {data.missing_required.length ? (
            <p className="text-[13px] text-muted-foreground">
              {data.missing_required.join(", ")}
            </p>
          ) : null}
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(envBlock);
              setCopied(true);
              window.setTimeout(() => setCopied(false), 2000);
            } catch {
              setCopied(false);
            }
          }}
        >
          <ClipboardCopy className="size-4" aria-hidden />
          {copied ? "Copied" : "Copy missing as .env"}
        </Button>
      </Card>
      {data.groups.map((group) => {
        const items = data.items.filter((i) => i.group === group.key);
        if (!items.length) return null;
        return (
          <section key={group.key} aria-labelledby={`group-${group.key}`}>
            <h2
              id={`group-${group.key}`}
              className="mb-2 text-[15px] font-semibold"
            >
              {group.label}
            </h2>
            <Card className="divide-y divide-border">
              {items.map((item) => (
                <KeyRow key={item.key} item={item} />
              ))}
            </Card>
          </section>
        );
      })}
    </div>
  );
}

function initial(item: KeyItem): string {
  if (item.kind === "secret" || item.value === null || item.value === undefined)
    return "";
  if (Array.isArray(item.value)) return item.value.join(", ");
  return String(item.value);
}

function KeyRow({ item }: { item: KeyItem }) {
  const [value, setValue] = React.useState(initial(item));
  const [models, setModels] = React.useState<Record<string, string>>(
    item.kind === "models" && item.value && typeof item.value === "object"
      ? (item.value as Record<string, string>)
      : {},
  );
  const [result, setResult] = React.useState<{
    ok: boolean;
    message: string;
  } | null>(null);
  const invalidate = [["operator", "platform-keys"]];
  const save = useScopedMutation(
    () =>
      keysApi.save(
        item.key,
        item.kind === "models"
          ? models
          : item.kind === "bool"
            ? value === "true"
            : value,
      ),
    {
      invalidate,
      success: `${item.label} saved`,
      onSuccess: () => item.kind === "secret" && setValue(""),
    },
  );
  const remove = useScopedMutation(() => keysApi.remove(item.key), {
    invalidate,
    success: `${item.label} now uses the server .env value`,
  });
  const test = useScopedMutation(() => keysApi.test(item.key), {
    onSuccess: (r) => setResult(r),
  });
  const id = `key-${item.key}`;
  return (
    <div className="grid gap-3 p-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <label htmlFor={id} className="text-sm font-semibold">
            {item.label}
          </label>
          {item.required ? <Badge tone="info">Required</Badge> : null}
          {item.set ? (
            <Badge tone="success">
              {item.source === "dashboard" ? "Saved here" : "From .env"}
            </Badge>
          ) : (
            <Badge tone={item.required ? "danger" : "neutral"}>Missing</Badge>
          )}
        </div>
        <p className="mt-1 font-mono text-[11px] text-muted-foreground">
          {item.key}
        </p>
        <p className="mt-1 text-[13px] text-muted-foreground">{item.purpose}</p>
        {item.where ? (
          <p className="mt-1 text-[12px] text-muted-foreground">
            Where: {item.where}
          </p>
        ) : null}
      </div>
      {item.server_only ? (
        <p className="self-center text-[13px] text-muted-foreground">
          Set this in the server&apos;s .env (the database needs it before it
          can read anything saved here).
        </p>
      ) : (
        <div className="space-y-2">
          {item.kind === "models" ? (
            <div className="grid grid-cols-2 gap-2">
              {MODEL_JOBS.map((job) => (
                <label key={job} className="space-y-1 text-[12px]">
                  <span className="text-muted-foreground">{pretty(job)}</span>
                  <Input
                    value={models[job] ?? ""}
                    placeholder="Recommended default"
                    onChange={(e) =>
                      setModels((m) => ({ ...m, [job]: e.target.value }))
                    }
                  />
                </label>
              ))}
            </div>
          ) : item.kind === "choice" || item.kind === "bool" ? (
            <NativeSelect
              id={id}
              value={value}
              onChange={(e) => setValue(e.target.value)}
            >
              {item.kind === "bool" ? (
                <>
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </>
              ) : (
                item.choices.map((c) => (
                  <option key={c} value={c}>
                    {c === "" ? "None" : c}
                  </option>
                ))
              )}
            </NativeSelect>
          ) : (
            <Input
              id={id}
              type={item.kind === "secret" ? "password" : "text"}
              autoComplete="off"
              inputMode={item.kind === "number" ? "decimal" : undefined}
              value={value}
              placeholder={
                item.kind === "secret"
                  ? item.set
                    ? `Saved (${item.hint || "hidden"}) · paste a new value to replace`
                    : "Paste the key"
                  : item.placeholder
              }
              onChange={(e) => setValue(e.target.value)}
            />
          )}
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              loading={save.isPending}
              disabled={item.kind === "secret" && !value}
              aria-label={`Save ${item.label}`}
              onClick={() => save.mutate(undefined)}
            >
              Save
            </Button>
            {item.testable ? (
              <Button
                size="sm"
                variant="secondary"
                loading={test.isPending}
                aria-label={`Test ${item.label}`}
                onClick={() => test.mutate(undefined)}
              >
                Test
              </Button>
            ) : null}
            {item.source === "dashboard" ? (
              <Button
                size="sm"
                variant="ghost"
                loading={remove.isPending}
                onClick={() => remove.mutate(undefined)}
              >
                Use .env value
              </Button>
            ) : null}
            {result ? (
              <span
                role="status"
                className={
                  "text-[13px] " + (result.ok ? "text-success" : "text-danger")
                }
              >
                {result.message}
              </span>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ reviews

interface ReviewItem {
  tenant_id: string;
  business: string;
  country: string;
  status: string;
  details: Record<string, string>;
  missing: string[];
  submitted_at: string | null;
  decided_at: string | null;
  note: string;
}
const reviewsApi = {
  list: (status: string) =>
    apiRequest<{
      items: ReviewItem[];
      total: number;
      counts: Record<string, number>;
    }>("GET", "/operator/pi/reviews", null, {
      query: status ? { status } : {},
    }),
  decide: (tenantId: string, body: { action: string; note: string }) =>
    apiRequest<ReviewItem>(
      "POST",
      `/operator/pi/accounts/${tenantId}/review`,
      null,
      { body },
    ),
};
const REVIEW_TONE: Record<
  string,
  "info" | "warning" | "success" | "danger" | "neutral"
> = {
  submitted: "info",
  changes_requested: "warning",
  approved: "success",
  rejected: "danger",
};
const DETAIL_LABELS: [string, string][] = [
  ["legal_name", "Business name"],
  ["category", "Type"],
  ["address", "Address"],
  ["city", "City"],
  ["contact_phone", "Phone"],
  ["website", "Website / page"],
  ["about", "What they sell"],
];

export function OperatorReviewsPage() {
  return (
    <OperatorShell
      title="Business reviews"
      description="Approve businesses before their WhatsApp number goes live. After approval they connect once their plan is paid (or you give them a free plan)."
    >
      {(me) => <Reviews me={me} />}
    </OperatorShell>
  );
}

function Reviews({ me }: { me: OperatorMe }) {
  const [status, setStatus] = React.useState("submitted");
  const [open, setOpen] = React.useState<ReviewItem | null>(null);
  const canDecide = me.capabilities.includes("operator.accounts.manage");
  const list = useScopedQuery(["operator", "reviews", status], () =>
    reviewsApi.list(status),
  );
  const tabs = [
    ["submitted", "Waiting"],
    ["changes_requested", "Changes asked"],
    ["approved", "Approved"],
    ["rejected", "Declined"],
    ["", "All"],
  ];
  return (
    <div className="space-y-4">
      <div
        className="flex flex-wrap gap-1"
        role="tablist"
        aria-label="Review status"
      >
        {tabs.map(([value, text]) => (
          <Button
            key={value}
            role="tab"
            aria-selected={status === value}
            size="sm"
            variant={status === value ? "default" : "secondary"}
            onClick={() => setStatus(value)}
          >
            {text}
            {value && list.data?.counts[value]
              ? ` (${list.data.counts[value]})`
              : ""}
          </Button>
        ))}
      </div>
      {list.isPending ? (
        <Skeleton className="h-40 w-full" />
      ) : list.isError ? (
        <ErrorState error={list.error} onRetry={() => list.refetch()} />
      ) : !list.data.items.length ? (
        <EmptyState
          icon={CheckCircle2}
          title="Nothing here"
          description="Businesses appear here when they send their details."
        />
      ) : (
        <Card className="divide-y divide-border">
          {list.data.items.map((item) => (
            <div
              key={item.tenant_id}
              className="flex flex-wrap items-center gap-3 p-4"
            >
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Link
                    href={`/operator/businesses/${item.tenant_id}`}
                    className="font-semibold hover:underline"
                  >
                    {item.business}
                  </Link>
                  <Badge tone={REVIEW_TONE[item.status] ?? "neutral"}>
                    {pretty(item.status)}
                  </Badge>
                </div>
                <p className="text-[13px] text-muted-foreground">
                  {[
                    item.details.legal_name,
                    item.details.city,
                    item.details.category,
                  ]
                    .filter(Boolean)
                    .join(" · ")}{" "}
                  · sent {when(item.submitted_at)}
                </p>
              </div>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => setOpen(item)}
              >
                Review
              </Button>
            </div>
          ))}
        </Card>
      )}
      {open ? (
        <ReviewDialog
          item={open}
          canDecide={canDecide}
          onClose={() => setOpen(null)}
        />
      ) : null}
    </div>
  );
}

function ReviewDialog({
  item,
  canDecide,
  onClose,
}: {
  item: ReviewItem;
  canDecide: boolean;
  onClose: () => void;
}) {
  const [note, setNote] = React.useState("");
  const decide = useScopedMutation(
    (action: string) => reviewsApi.decide(item.tenant_id, { action, note }),
    {
      invalidate: [
        ["operator", "reviews"],
        ["operator", "needs-you"],
      ],
      success: (r) => `${r.business ?? item.business}: ${pretty(r.status)}`,
      onSuccess: onClose,
    },
  );
  const needsNote = note.trim().length < 5;
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader
          title={item.business}
          description={`Status: ${pretty(item.status)}`}
        />
        <DialogBody className="space-y-4">
          <dl className="grid gap-x-4 gap-y-2 text-[13px] sm:grid-cols-[140px_1fr]">
            {DETAIL_LABELS.map(([k, text]) => (
              <React.Fragment key={k}>
                <dt className="text-muted-foreground">{text}</dt>
                <dd className="whitespace-pre-line break-words">
                  {item.details[k] || "—"}
                </dd>
              </React.Fragment>
            ))}
          </dl>
          {item.note ? (
            <Notice tone="info" title="Last note to the business">
              {item.note}
            </Notice>
          ) : null}
          {canDecide ? (
            <label className="block space-y-1 text-[13px]">
              <span className="font-medium">Note to the business</span>
              <Textarea
                value={note}
                maxLength={500}
                placeholder="Needed when asking for changes or declining."
                onChange={(e) => setNote(e.target.value)}
              />
            </label>
          ) : (
            <Notice tone="info">
              You can view reviews; approving needs account management access.
            </Notice>
          )}
        </DialogBody>
        {canDecide ? (
          <DialogFooter>
            <Button
              variant="secondary"
              disabled={needsNote || decide.isPending}
              onClick={() => decide.mutate("reject")}
            >
              Decline
            </Button>
            <Button
              variant="secondary"
              disabled={needsNote || decide.isPending}
              onClick={() => decide.mutate("request_changes")}
            >
              Ask for changes
            </Button>
            <Button
              loading={decide.isPending}
              onClick={() => decide.mutate("approve")}
            >
              Approve
            </Button>
          </DialogFooter>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

// ------------------------------------------------------------------ needs you

export function NeedsYouCard() {
  const needs = useScopedQuery(["operator", "needs-you"], () =>
    apiRequest<{
      items: { kind: string; count: number; label: string; href: string }[];
      total: number;
    }>("GET", "/operator/pi/needs-you", null),
  );
  if (needs.isPending || needs.isError || !needs.data.items.length) return null;
  return (
    <Card className="p-4">
      <h2 className="mb-3 text-[15px] font-semibold">Needs you</h2>
      <ul className="grid gap-2 sm:grid-cols-3">
        {needs.data.items.map((i) => (
          <li key={i.kind}>
            <Link
              href={i.href}
              className="flex items-center gap-3 rounded-lg border border-border p-3 hover:bg-surface-muted"
            >
              <span className="text-2xl font-semibold tabular-nums">
                {i.count}
              </span>
              <span className="text-[13px] text-muted-foreground">
                {i.label}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </Card>
  );
}

// ------------------------------------------------------------------ plans

export interface PlanRow {
  key: string;
  name: string;
  description: string;
  status: "draft" | "available" | "retired";
  monthly_price: string | null;
  currency: string;
  trial_days: number;
  allowances: Record<string, number | null>;
  features: string[];
  visibility: "public" | "private";
  sort_order: number;
  free: boolean;
  stripe_price_configured: boolean;
  manual_monthly_price_pkr: string | null;
}
const plansApi = {
  list: () => apiRequest<PlanRow[]>("GET", "/operator/pi/plans", null),
  catalog: () =>
    apiRequest<{ features: string[]; allowances: string[] }>(
      "GET",
      "/operator/pi/plan-features",
      null,
    ),
  create: (body: Record<string, unknown>) =>
    apiRequest<PlanRow>("POST", "/operator/pi/plans", null, { body }),
  update: (key: string, body: Record<string, unknown>) =>
    apiRequest<PlanRow>("PUT", `/operator/pi/plans/${key}`, null, { body }),
  remove: (key: string) =>
    apiRequest<{ result: string }>("DELETE", `/operator/pi/plans/${key}`, null),
};

export function PlansManager({ me }: { me: OperatorMe }) {
  const canEdit = me.capabilities.includes("operator.plans.manage");
  const plans = useScopedQuery(["operator", "plans"], plansApi.list);
  const catalog = useScopedQuery(
    ["operator", "plan-features"],
    plansApi.catalog,
  );
  const [editing, setEditing] = React.useState<PlanRow | "new" | null>(null);
  if (plans.isPending || catalog.isPending)
    return <Skeleton className="h-64 w-full" />;
  if (plans.isError)
    return <ErrorState error={plans.error} onRetry={() => plans.refetch()} />;
  if (catalog.isError)
    return (
      <ErrorState error={catalog.error} onRetry={() => catalog.refetch()} />
    );
  return (
    <div className="space-y-4">
      {canEdit ? (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-[13px] text-muted-foreground">
            Free plan = price 0 (give it from a business&apos;s page). Private
            plans are never shown to businesses. PKR prices for bank and cash
            are set on{" "}
            <Link href="/settings/pi-billing" className="underline">
              Subscription payments
            </Link>
            .
          </p>
          <Button onClick={() => setEditing("new")}>
            <Plus className="size-4" aria-hidden />
            New plan
          </Button>
        </div>
      ) : null}
      <div className="grid gap-4 lg:grid-cols-3">
        {plans.data.map((p) => (
          <Card key={p.key} className="space-y-3 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="font-semibold">{p.name}</h3>
              <Badge tone={p.status === "available" ? "success" : "neutral"}>
                {pretty(p.status)}
              </Badge>
              {p.free ? <Badge tone="pi">Free</Badge> : null}
              {p.visibility === "private" ? (
                <Badge tone="warning">Private</Badge>
              ) : null}
            </div>
            <p className="text-2xl font-semibold tabular-nums">
              {p.monthly_price === null
                ? "Price on request"
                : p.free
                  ? "Free"
                  : `${p.currency} ${p.monthly_price}`}
              {p.manual_monthly_price_pkr ? (
                <span className="ml-2 text-[13px] font-normal text-muted-foreground">
                  PKR {p.manual_monthly_price_pkr}
                </span>
              ) : null}
            </p>
            {p.description ? (
              <p className="text-[13px] text-muted-foreground">
                {p.description}
              </p>
            ) : null}
            <p className="text-[13px]">
              {p.trial_days ? `${p.trial_days}-day trial` : "No trial"} ·{" "}
              {p.stripe_price_configured
                ? "Card checkout ready"
                : "No card checkout"}
            </p>
            <div className="flex flex-wrap gap-1">
              {p.features.map((f) => (
                <Badge key={f} tone="neutral">
                  {pretty(f)}
                </Badge>
              ))}
            </div>
            <dl className="grid grid-cols-2 gap-1 text-[12px]">
              {Object.entries(p.allowances).map(([k, v]) => (
                <React.Fragment key={k}>
                  <dt className="text-muted-foreground">{pretty(k)}</dt>
                  <dd className="text-right tabular-nums">
                    {v === null ? "Not included" : v.toLocaleString()}
                  </dd>
                </React.Fragment>
              ))}
            </dl>
            {canEdit ? (
              <Button
                variant="secondary"
                className="w-full"
                onClick={() => setEditing(p)}
              >
                Edit plan
              </Button>
            ) : null}
          </Card>
        ))}
      </div>
      {editing ? (
        <PlanDialog
          plan={editing === "new" ? null : editing}
          features={catalog.data.features}
          allowanceKeys={catalog.data.allowances}
          onClose={() => setEditing(null)}
        />
      ) : null}
    </div>
  );
}

function PlanDialog({
  plan,
  features,
  allowanceKeys,
  onClose,
}: {
  plan: PlanRow | null;
  features: string[];
  allowanceKeys: string[];
  onClose: () => void;
}) {
  const [form, setForm] = React.useState({
    key: plan?.key ?? "",
    name: plan?.name ?? "",
    description: plan?.description ?? "",
    status: plan?.status ?? "draft",
    visibility: plan?.visibility ?? "public",
    monthly_price: plan?.monthly_price ?? "",
    currency: plan?.currency ?? "USD",
    trial_days: String(plan?.trial_days ?? 0),
    stripe_price_id: "",
  });
  const [picked, setPicked] = React.useState<string[]>(
    plan?.features ?? ["inbox", "knowledge"],
  );
  const [limits, setLimits] = React.useState<Record<string, string>>(
    Object.fromEntries(
      allowanceKeys.map((k) => {
        const v = plan?.allowances[k];
        return [k, v === undefined ? "" : v === null ? "none" : String(v)];
      }),
    ),
  );
  const set = (k: keyof typeof form, v: string) =>
    setForm((f) => ({ ...f, [k]: v }));
  const body = () => {
    const allowances: Record<string, number | null> = {};
    for (const [k, v] of Object.entries(limits)) {
      if (v === "none") allowances[k] = null;
      else if (v.trim() !== "") allowances[k] = Number(v);
    }
    return {
      name: form.name,
      description: form.description,
      status: form.status,
      visibility: form.visibility,
      monthly_price: form.monthly_price === "" ? null : form.monthly_price,
      currency: form.currency,
      trial_days: Number(form.trial_days || 0),
      features: picked,
      allowances,
      ...(form.stripe_price_id
        ? { stripe_price_id: form.stripe_price_id }
        : {}),
    };
  };
  const invalidate = [["operator", "plans"]];
  const save = useScopedMutation(
    () =>
      plan
        ? plansApi.update(plan.key, body())
        : plansApi.create({ key: form.key, ...body() }),
    { invalidate, success: `${form.name || "Plan"} saved`, onSuccess: onClose },
  );
  const remove = useScopedMutation(() => plansApi.remove(plan?.key ?? ""), {
    invalidate,
    success: (r) =>
      r.result === "deleted" ? "Plan deleted" : "Plan retired (it was in use)",
    onSuccess: onClose,
  });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader
          title={plan ? `Edit ${plan.name}` : "New plan"}
          description="Limits: empty = no limit, “none” = not included."
        />
        <DialogBody className="space-y-3 text-[13px]">
          <div className="grid gap-3 sm:grid-cols-2">
            {!plan ? (
              <label className="space-y-1">
                <span className="font-medium">Key</span>
                <Input
                  value={form.key}
                  placeholder="growth-plus"
                  onChange={(e) => set("key", e.target.value.toLowerCase())}
                />
              </label>
            ) : null}
            <label className="space-y-1">
              <span className="font-medium">Name</span>
              <Input
                value={form.name}
                onChange={(e) => set("name", e.target.value)}
              />
            </label>
            <label className="space-y-1">
              <span className="font-medium">Monthly price (0 = free)</span>
              <Input
                inputMode="decimal"
                value={form.monthly_price}
                placeholder="Price on request"
                onChange={(e) => set("monthly_price", e.target.value)}
              />
            </label>
            <label className="space-y-1">
              <span className="font-medium">Currency</span>
              <Input
                value={form.currency}
                maxLength={3}
                onChange={(e) => set("currency", e.target.value.toUpperCase())}
              />
            </label>
            <label className="space-y-1">
              <span className="font-medium">Trial days (0 = none)</span>
              <Input
                inputMode="numeric"
                value={form.trial_days}
                onChange={(e) => set("trial_days", e.target.value)}
              />
            </label>
            <label className="space-y-1">
              <span className="font-medium">Status</span>
              <NativeSelect
                value={form.status}
                onChange={(e) => set("status", e.target.value)}
              >
                <option value="draft">Draft</option>
                <option value="available">Available</option>
                <option value="retired">Retired</option>
              </NativeSelect>
            </label>
            <label className="space-y-1">
              <span className="font-medium">Who can see it</span>
              <NativeSelect
                value={form.visibility}
                onChange={(e) => set("visibility", e.target.value)}
              >
                <option value="public">Everyone (pricing page)</option>
                <option value="private">Private (you assign it)</option>
              </NativeSelect>
            </label>
            <label className="space-y-1">
              <span className="font-medium">Stripe price id</span>
              <Input
                value={form.stripe_price_id}
                placeholder={
                  plan?.stripe_price_configured
                    ? "Set · paste to replace"
                    : "price_…"
                }
                onChange={(e) => set("stripe_price_id", e.target.value)}
              />
            </label>
          </div>
          <label className="block space-y-1">
            <span className="font-medium">Description</span>
            <Textarea
              value={form.description}
              maxLength={300}
              onChange={(e) => set("description", e.target.value)}
            />
          </label>
          <fieldset>
            <legend className="mb-1 font-medium">Included features</legend>
            <div className="grid grid-cols-2 gap-1 sm:grid-cols-3">
              {features.map((f) => (
                <label key={f} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={picked.includes(f)}
                    onChange={(e) =>
                      setPicked((p) =>
                        e.target.checked ? [...p, f] : p.filter((x) => x !== f),
                      )
                    }
                  />
                  {pretty(f)}
                </label>
              ))}
            </div>
          </fieldset>
          <fieldset>
            <legend className="mb-1 font-medium">Monthly limits</legend>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {allowanceKeys.map((k) => (
                <label key={k} className="space-y-1">
                  <span className="text-muted-foreground">{pretty(k)}</span>
                  <Input
                    value={limits[k] ?? ""}
                    placeholder="No limit"
                    onChange={(e) =>
                      setLimits((l) => ({ ...l, [k]: e.target.value }))
                    }
                  />
                </label>
              ))}
            </div>
          </fieldset>
        </DialogBody>
        <DialogFooter>
          {plan ? (
            <Button
              variant="ghost"
              loading={remove.isPending}
              onClick={() => remove.mutate(undefined)}
            >
              <Trash2 className="size-4" aria-hidden />
              Delete
            </Button>
          ) : null}
          <Button
            loading={save.isPending}
            disabled={!form.name || (!plan && form.key.length < 2)}
            onClick={() => save.mutate(undefined)}
          >
            Save plan
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
