"use client";

import { useQuery } from "@tanstack/react-query";
import { Megaphone } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import {
  Badge,
  Button,
  Card,
  CardSection,
  EmptyState,
  ErrorState,
  Field,
  Input,
  LoadingBlock,
  Notice,
  PageHeader,
  Select,
  Textarea,
} from "@/components/ui";
import { errorText, get, post, put } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { useAction, useBusinessKey, useCan } from "@/lib/session";

interface Results {
  recipients: number;
  waiting: number;
  sent: number;
  delivered: number;
  read: number;
  failed: number;
  skipped: number;
  replied: number;
  skipped_reasons: Record<string, number>;
}

interface Campaign {
  id: string;
  name: string;
  template_name: string;
  template_language: string;
  audience_tag: string | null;
  status: "draft" | "scheduled" | "sending" | "completed" | "cancelled";
  scheduled_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  max_recipients: number;
  daily_limit: number;
  quiet_start: number;
  quiet_end: number;
  results: Results;
}

interface Audience {
  count: number;
  plan_allows: boolean;
  whatsapp_connected: boolean;
}

const STATUS: Record<
  Campaign["status"],
  [string, "neutral" | "info" | "accent" | "success" | "danger"]
> = {
  draft: ["Draft", "neutral"],
  scheduled: ["Scheduled", "info"],
  sending: ["Sending", "accent"],
  completed: ["Sent", "success"],
  cancelled: ["Cancelled", "danger"],
};

const REASONS: Record<string, string> = {
  OPTED_OUT: "said stop",
  HUMAN_TAKEOVER: "your team was chatting with them",
  CAMPAIGN_CANCELLED: "campaign cancelled",
  NO_WHATSAPP_CONTACT: "no WhatsApp number",
};

const EMPTY = {
  name: "",
  template_name: "",
  template_language: "en",
  audience_tag: "",
  max_recipients: "500",
  daily_limit: "200",
  quiet_start: "21",
  quiet_end: "9",
};

export function CampaignsPage() {
  const key = useBusinessKey();
  const can = useCan();
  const campaigns = useQuery({
    queryKey: key(["campaigns"]),
    queryFn: () => get<Campaign[]>("/pi/campaigns"),
    enabled: can("pi.campaigns.read"),
    refetchInterval: 15_000,
  });
  if (!can("pi.campaigns.read")) {
    return (
      <div>
        <PageHeader title="Campaigns" />
        <Notice tone="info">
          Ask your business owner to give you access to campaigns.
        </Notice>
      </div>
    );
  }
  return (
    <div>
      <PageHeader
        title="Campaigns"
        description="Send an approved WhatsApp message to customers who agreed to hear from you. Anyone who replies STOP is removed at once."
        action={
          <Link className="text-sm text-accent underline" href="/customers">
            Back to customers
          </Link>
        }
      />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        {can("pi.campaigns.manage") ? <NewCampaign /> : null}
        <section aria-labelledby="campaign-list" className="space-y-3">
          <h2 id="campaign-list" className="text-base font-semibold">
            Your campaigns
          </h2>
          {campaigns.isPending ? (
            <LoadingBlock rows={3} />
          ) : campaigns.isError ? (
            <ErrorState
              message={errorText(campaigns.error)}
              onRetry={() => campaigns.refetch()}
            />
          ) : !campaigns.data.length ? (
            <Card>
              <EmptyState
                icon={<Megaphone className="size-5" aria-hidden />}
                title="No campaigns yet"
              >
                Your first campaign will appear here with its results.
              </EmptyState>
            </Card>
          ) : (
            campaigns.data.map((c) => <CampaignCard key={c.id} campaign={c} />)
          )}
        </section>
      </div>
    </div>
  );
}

function NewCampaign() {
  const key = useBusinessKey();
  const [form, setForm] = React.useState(EMPTY);
  const set =
    (field: keyof typeof EMPTY) =>
    (
      e: React.ChangeEvent<
        HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement
      >,
    ) =>
      setForm((f) => ({ ...f, [field]: e.target.value }));
  const tag = form.audience_tag.trim().toLowerCase();
  const audience = useQuery({
    queryKey: key(["campaign-audience", tag]),
    queryFn: () =>
      get<Audience>(
        `/pi/campaigns/audience${tag ? `?tag=${encodeURIComponent(tag)}` : ""}`,
      ),
  });
  const create = useAction(
    () =>
      post<Campaign>("/pi/campaigns", {
        name: form.name,
        template_name: form.template_name.trim(),
        template_language: form.template_language.trim(),
        audience_tag: tag || null,
        max_recipients: Number(form.max_recipients),
        daily_limit: Number(form.daily_limit),
        quiet_start: Number(form.quiet_start),
        quiet_end: Number(form.quiet_end),
      }),
    {
      invalidate: [["campaigns"]],
      success: "Saved as a draft. Schedule it when you're ready.",
      onSuccess: () => setForm(EMPTY),
    },
  );
  const check = useAction(
    () =>
      post<{ approved: boolean; body?: string; message?: string }>(
        "/pi/whatsapp/templates/check",
        {
          name: form.template_name.trim(),
          language: form.template_language.trim(),
        },
      ),
    { silentError: false },
  );
  const hours = Array.from({ length: 24 }, (_, h) => h);
  const valid =
    form.name.trim() &&
    /^[a-z0-9_]{1,512}$/.test(form.template_name.trim()) &&
    /^[a-z]{2,3}(_[A-Z]{2})?$/.test(form.template_language.trim());
  return (
    <Card>
      <CardSection className="space-y-4">
        <h2 className="font-semibold">New campaign</h2>
        {audience.data && !audience.data.plan_allows ? (
          <Notice tone="warning">
            Campaigns are included in the Growth and Business plans.
          </Notice>
        ) : null}
        {audience.data && !audience.data.whatsapp_connected ? (
          <Notice tone="warning">Connect your WhatsApp number first.</Notice>
        ) : null}
        <Field
          label="Campaign name"
          htmlFor="c-name"
          hint="Only your team sees this."
        >
          <Input
            id="c-name"
            value={form.name}
            onChange={set("name")}
            maxLength={120}
          />
        </Field>
        <div className="grid gap-3 sm:grid-cols-[1fr_8rem]">
          <Field
            label="WhatsApp template name"
            htmlFor="c-template"
            hint="An approved template without variables, created in your WhatsApp Manager."
          >
            <Input
              id="c-template"
              value={form.template_name}
              onChange={set("template_name")}
              placeholder="eid_offer"
            />
          </Field>
          <Field label="Language code" htmlFor="c-lang">
            <Input
              id="c-lang"
              value={form.template_language}
              onChange={set("template_language")}
              placeholder="en"
            />
          </Field>
        </div>
        <div>
          <Button
            size="sm"
            variant="secondary"
            disabled={!valid}
            loading={check.isPending}
            onClick={() => check.mutate(undefined)}
          >
            Check template
          </Button>
          {check.data ? (
            check.data.approved ? (
              <div className="mt-2 rounded-lg border border-border bg-surface-muted p-3 text-sm">
                <Badge tone="success">Approved</Badge>
                <p className="mt-2 whitespace-pre-line" data-user-text>
                  {check.data.body}
                </p>
              </div>
            ) : (
              <p className="mt-2 text-sm text-danger" role="alert">
                {check.data.message}
              </p>
            )
          ) : null}
        </div>
        <Field
          label="Only customers tagged"
          htmlFor="c-tag"
          optional
          hint="Leave empty to include everyone who agreed."
        >
          <Input
            id="c-tag"
            value={form.audience_tag}
            onChange={set("audience_tag")}
            maxLength={40}
            placeholder="vip"
          />
        </Field>
        <p className="text-sm" aria-live="polite">
          {audience.data
            ? `${audience.data.count} customer${audience.data.count === 1 ? "" : "s"} agreed to receive messages${tag ? ` with the tag "${tag}"` : ""}.`
            : " "}
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="At most this many people" htmlFor="c-max">
            <Input
              id="c-max"
              inputMode="numeric"
              value={form.max_recipients}
              onChange={set("max_recipients")}
            />
          </Field>
          <Field label="At most per day" htmlFor="c-day">
            <Input
              id="c-day"
              inputMode="numeric"
              value={form.daily_limit}
              onChange={set("daily_limit")}
            />
          </Field>
          <Field label="Don't send after" htmlFor="c-qs">
            <Select
              id="c-qs"
              value={form.quiet_start}
              onChange={set("quiet_start")}
            >
              {hours.map((h) => (
                <option key={h} value={h}>
                  {`${h}:00`}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Start again at" htmlFor="c-qe">
            <Select
              id="c-qe"
              value={form.quiet_end}
              onChange={set("quiet_end")}
            >
              {hours.map((h) => (
                <option key={h} value={h}>
                  {`${h}:00`}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <Button
          loading={create.isPending}
          disabled={!valid}
          onClick={() => create.mutate(undefined)}
        >
          Save draft
        </Button>
      </CardSection>
    </Card>
  );
}

function CampaignCard({ campaign: c }: { campaign: Campaign }) {
  const can = useCan();
  const [when, setWhen] = React.useState("");
  const schedule = useAction(
    () =>
      post<Campaign>(`/pi/campaigns/${c.id}/schedule`, {
        scheduled_at: when ? new Date(when).toISOString() : null,
      }),
    {
      invalidate: [["campaigns"]],
      success: when ? "Scheduled" : "Sending has started",
    },
  );
  const cancel = useAction(() => post(`/pi/campaigns/${c.id}/cancel`), {
    invalidate: [["campaigns"]],
    success: "Campaign cancelled. Nothing more will be sent.",
  });
  const [label, tone] = STATUS[c.status];
  const r = c.results;
  const reasons = Object.entries(r.skipped_reasons);
  return (
    <Card>
      <CardSection className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="flex-1 font-semibold" data-user-text>
            {c.name}
          </h3>
          <Badge tone={tone}>{label}</Badge>
        </div>
        <p className="text-sm text-muted-foreground">
          Template{" "}
          <span className="font-medium text-foreground">{c.template_name}</span>{" "}
          ({c.template_language})
          {c.audience_tag
            ? ` · tagged "${c.audience_tag}"`
            : " · everyone who agreed"}
          {` · up to ${c.daily_limit}/day, quiet ${c.quiet_start}:00–${c.quiet_end}:00`}
        </p>
        {c.scheduled_at && c.status === "scheduled" ? (
          <p className="text-sm">Starts {dateTime(c.scheduled_at)}</p>
        ) : null}
        {r.recipients ? (
          <dl className="grid grid-cols-3 gap-2 text-center text-sm sm:grid-cols-6">
            {(
              [
                ["Recipients", r.recipients],
                ["Waiting", r.waiting],
                ["Sent", r.sent],
                ["Delivered", r.delivered],
                ["Read", r.read],
                ["Replied", r.replied],
              ] as const
            ).map(([name, value]) => (
              <div key={name} className="rounded-lg bg-surface-muted p-2">
                <dt className="text-xs text-muted-foreground">{name}</dt>
                <dd className="text-base font-semibold tabular-nums">
                  {value}
                </dd>
              </div>
            ))}
          </dl>
        ) : null}
        {r.failed || reasons.length ? (
          <p className="text-xs text-muted-foreground">
            {r.failed ? `${r.failed} failed. ` : ""}
            {reasons.length
              ? `Not sent: ${reasons
                  .map(
                    ([code, n]) =>
                      `${n} ${REASONS[code] ?? code.toLowerCase()}`,
                  )
                  .join(", ")}.`
              : ""}
          </p>
        ) : null}
        {can("pi.campaigns.manage") ? (
          <div className="flex flex-wrap items-end gap-2">
            {c.status === "draft" ? (
              <>
                <Field label="Send at (optional)" htmlFor={`when-${c.id}`}>
                  <Input
                    id={`when-${c.id}`}
                    type="datetime-local"
                    value={when}
                    onChange={(e) => setWhen(e.target.value)}
                  />
                </Field>
                <Button
                  loading={schedule.isPending}
                  onClick={() => schedule.mutate(undefined)}
                >
                  {when ? "Schedule" : "Start sending"}
                </Button>
              </>
            ) : null}
            {["draft", "scheduled", "sending"].includes(c.status) ? (
              <Button
                variant="danger"
                size="sm"
                loading={cancel.isPending}
                onClick={() => cancel.mutate(undefined)}
              >
                Cancel campaign
              </Button>
            ) : null}
          </div>
        ) : null}
      </CardSection>
    </Card>
  );
}

/** Record or withdraw a customer's agreement to receive marketing messages. */
export function MarketingConsent({
  customerId,
  granted,
}: {
  customerId: string;
  granted: boolean;
}) {
  const [source, setSource] = React.useState("");
  const save = useAction(
    (allow: boolean) =>
      put(`/pi/customers/${customerId}/consent`, {
        purpose: "marketing",
        granted: allow,
        source: allow ? source : "",
      }),
    {
      invalidate: [["profile", customerId], ["campaign-audience"]],
      success: (_) => "Saved",
      onSuccess: () => setSource(""),
    },
  );
  if (granted) {
    return (
      <Button
        size="sm"
        variant="secondary"
        loading={save.isPending}
        onClick={() => save.mutate(false)}
      >
        Stop marketing messages
      </Button>
    );
  }
  return (
    <details className="rounded-lg border border-border p-3 text-sm">
      <summary className="cursor-pointer font-medium">
        Customer agreed to offers and news
      </summary>
      <div className="mt-3 space-y-2">
        <label htmlFor={`consent-${customerId}`} className="block text-sm">
          How did they agree?
        </label>
        <Textarea
          id={`consent-${customerId}`}
          rows={2}
          maxLength={300}
          value={source}
          placeholder="Ticked the box on our order form, 30 Sept"
          onChange={(e) => setSource(e.target.value)}
        />
        <Button
          size="sm"
          loading={save.isPending}
          disabled={source.trim().length < 5}
          onClick={() => save.mutate(true)}
        >
          Record agreement
        </Button>
      </div>
    </details>
  );
}
