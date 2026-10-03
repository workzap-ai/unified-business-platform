"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BellRing,
  BookOpenText,
  FlaskConical,
  Globe,
  MessageSquareText,
  PlugZap,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  Bot,
  Settings2,
} from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { SubNav } from "@/components/shell";
import { RemindersAndForms } from "@/features/forms-settings";
import { TeachFromFile } from "@/features/teach-files";
import { OneClickForms, TemplatesCard } from "@/features/templates";
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
  Switch,
  Textarea,
} from "@/components/ui";
import {
  AVAILABLE_TOOL_GROUPS,
  HelpForm,
  LANGUAGES,
  TOOL_LABEL,
  useAccount,
} from "@/features/setup";
import { ConnectorsSection, useConnectors } from "@/features/connectors";
import { TestConversation } from "@/features/test-pi";
import product from "@/components/product.module.css";
import { del, errorText, get, patch, post } from "@/lib/api";
import { date } from "@/lib/format";
import { useAction, useBusinessKey, useCan } from "@/lib/session";
import type { Draft } from "@/lib/types";

const SECTIONS = [
  { href: "/my-pi/knowledge", label: "Business knowledge" },
  { href: "/my-pi/behaviour", label: "Behaviour" },
  { href: "/my-pi/agents", label: "Agents" },
  { href: "/my-pi/tools", label: "Tools" },
  { href: "/my-pi/follow-ups", label: "Follow-ups" },
  { href: "/my-pi/advanced", label: "Advanced" },
  { href: "/my-pi/test", label: "Test pi" },
];

function Shell({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <PageHeader title={title} description={description} />
      <SubNav items={SECTIONS} />
      {children}
    </div>
  );
}

export function MyPiOverview() {
  const cards = [
    {
      href: "/my-pi/knowledge",
      icon: BookOpenText,
      title: "Business knowledge",
      body: "What pi knows and may tell customers. Teach pi something new.",
    },
    {
      href: "/my-pi/behaviour",
      icon: SlidersHorizontal,
      title: "Behaviour",
      body: "Tone, prices, approvals and when pi hands over to your team.",
    },
    {
      href: "/my-pi/agents",
      icon: Bot,
      title: "Agents",
      body: "The specialists inside pi: their instructions, tools and versions.",
    },
    {
      href: "/my-pi/tools",
      icon: PlugZap,
      title: "Tools",
      body: "What pi may do: look up orders, book times, collect enquiries.",
    },
    {
      href: "/my-pi/follow-ups",
      icon: BellRing,
      title: "Follow-ups",
      body: "Friendly reminders for customers who agreed to them.",
    },
    {
      href: "/my-pi/advanced",
      icon: Settings2,
      title: "Advanced",
      body: "AI providers, handoff rules, knowledge search and tool permissions.",
    },
    {
      href: "/my-pi/test",
      icon: FlaskConical,
      title: "Test pi",
      body: "Chat with pi as a customer. Nothing is sent.",
    },
  ];
  return (
    <div>
      <PageHeader
        title="My pi"
        description="Shape how pi talks to your customers. No technical setup needed."
      />
      <div
        className={`grid gap-4 sm:grid-cols-2 lg:grid-cols-3 ${product.overviewCards}`}
      >
        {cards.map(({ href, icon: Icon, title, body }) => (
          <Link
            key={href}
            href={href}
            className="group rounded-xl focus-visible:outline-2"
          >
            <Card className="h-full transition-colors group-hover:border-accent/40">
              <CardSection>
                <div className="flex size-10 items-center justify-center rounded-lg bg-accent-soft text-accent-soft-foreground">
                  <Icon className="size-5" aria-hidden />
                </div>
                <h2 className="mt-3 font-semibold">{title}</h2>
                <p className="mt-1 text-sm text-muted-foreground">{body}</p>
              </CardSection>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}

function DraftCard({ draft }: { draft: Draft }) {
  const can = useCan();
  const [editing, setEditing] = React.useState(false);
  const [title, setTitle] = React.useState(draft.title);
  const [content, setContent] = React.useState(draft.content);
  const [visible, setVisible] = React.useState(draft.customer_visible);
  const save = useAction(
    () =>
      patch(`/knowledge/drafts/${draft.id}`, {
        title,
        content,
        customer_visible: visible,
      }),
    {
      invalidate: [["drafts"]],
      success: "Draft saved",
      onSuccess: () => setEditing(false),
    },
  );
  const publish = useAction(
    () => post(`/knowledge/drafts/${draft.id}/publish`),
    {
      invalidate: [["drafts"], ["documents"], ["account"]],
      success: visible
        ? "Published. pi can use this now."
        : "Saved for your team only.",
    },
  );
  const discard = useAction(
    () => post(`/knowledge/drafts/${draft.id}/discard`),
    {
      invalidate: [["drafts"]],
      success: "Draft discarded",
    },
  );
  return (
    <Card>
      <CardSection className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="warning">Draft — not used yet</Badge>
          <Badge>
            {draft.origin === "website"
              ? "From your website"
              : draft.origin === "ask_owner"
                ? "From a customer question"
                : draft.origin === "owner_upload"
                  ? "From your file"
                  : draft.origin === "owner_audio"
                    ? "From your voice note"
                    : "From you"}
          </Badge>
          <span className="ms-auto text-xs text-muted-foreground">
            {date(draft.created_at)}
          </span>
        </div>
        {editing ? (
          <div className="space-y-3">
            <Field label="Title" htmlFor={`t-${draft.id}`}>
              <Input
                id={`t-${draft.id}`}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                maxLength={200}
              />
            </Field>
            <Field label="What pi should know" htmlFor={`c-${draft.id}`}>
              <Textarea
                id={`c-${draft.id}`}
                value={content}
                onChange={(e) => setContent(e.target.value)}
                rows={8}
                maxLength={20000}
              />
            </Field>
            <label
              className="flex items-center gap-3 text-sm"
              htmlFor={`v-${draft.id}`}
            >
              <Switch
                id={`v-${draft.id}`}
                checked={visible}
                onCheckedChange={setVisible}
                label="Customers may be told this"
              />
              Customers may be told this
            </label>
          </div>
        ) : (
          <>
            <h3 className="font-semibold">{draft.title}</h3>
            <p
              className="line-clamp-6 whitespace-pre-line text-sm text-foreground-secondary"
              data-user-text
            >
              {draft.content}
            </p>
            {!draft.customer_visible ? (
              <Badge tone="info">Team only — never told to customers</Badge>
            ) : null}
            {draft.source_note ? (
              <p className="text-xs text-muted-foreground">
                {draft.source_note}
              </p>
            ) : null}
          </>
        )}
        <div className="flex flex-wrap justify-end gap-2">
          {editing ? (
            <>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setEditing(false)}
              >
                Cancel
              </Button>
              <Button
                size="sm"
                loading={save.isPending}
                onClick={() => save.mutate(undefined)}
              >
                Save draft
              </Button>
            </>
          ) : (
            <>
              <Button
                variant="ghost"
                size="sm"
                loading={discard.isPending}
                onClick={() => discard.mutate(undefined)}
              >
                Discard
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setEditing(true)}
              >
                Edit
              </Button>
              {can("pi.knowledge.publish") ? (
                <Button
                  size="sm"
                  loading={publish.isPending}
                  onClick={() => publish.mutate(undefined)}
                >
                  Publish
                </Button>
              ) : (
                <span className="text-sm text-muted-foreground">
                  An owner or admin must publish this.
                </span>
              )}
            </>
          )}
        </div>
      </CardSection>
    </Card>
  );
}

export function KnowledgePage() {
  const key = useBusinessKey();
  const can = useCan();
  const account = useAccount();
  const [note, setNote] = React.useState("");
  const [typedUrl, setUrl] = React.useState<string | null>(null);
  const url = typedUrl ?? account.data?.website ?? "";
  const drafts = useQuery({
    queryKey: key(["drafts"]),
    queryFn: () => get<Draft[]>("/knowledge/drafts"),
    enabled: can("pi.knowledge.manage"),
  });
  const documents = useQuery({
    queryKey: key(["documents"]),
    queryFn: () =>
      get<
        {
          id: string;
          title: string;
          status: string;
          source_name: string;
          created_at: string;
          body: string;
        }[]
      >("/pi/knowledge/documents"),
    enabled: can("pi.knowledge.manage"),
  });
  const teach = useAction(
    () => post<Draft>("/knowledge/teach", { text: note }),
    {
      invalidate: [["drafts"]],
      success: "pi drafted this. Review it below, then publish.",
      onSuccess: () => setNote(""),
    },
  );
  const website = useAction(() => post<Draft>("/knowledge/website", { url }), {
    invalidate: [["drafts"]],
    success: "We read the page. Review what pi learned below.",
    onSuccess: () => setUrl(null),
  });
  const remove = useAction(
    (id: string) => del(`/pi/knowledge/documents/${id}`),
    {
      invalidate: [["documents"], ["account"]],
      success: "Removed. pi won't use this anymore.",
    },
  );
  if (!can("pi.knowledge.manage")) {
    return (
      <Shell
        title="Business knowledge"
        description="What pi knows about your business."
      >
        <Notice tone="info">
          Ask your business owner to give you access to knowledge.
        </Notice>
      </Shell>
    );
  }
  return (
    <Shell
      title="Business knowledge"
      description="pi only tells customers what you've published here."
    >
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardSection className="space-y-3">
            <h2 className="flex items-center gap-2 font-semibold">
              <Sparkles className="size-4 text-accent" aria-hidden /> Teach pi
            </h2>
            <p className="text-sm text-muted-foreground">
              Write it the way you&apos;d tell a new employee. pi turns it into
              a draft for you to check.
            </p>
            <label htmlFor="teach" className="sr-only">
              What should pi know?
            </label>
            <Textarea
              id="teach"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={4}
              maxLength={8000}
              placeholder="We're closed on Fridays. Deliveries in the city take 2 days."
            />
            <Button
              loading={teach.isPending}
              disabled={note.trim().length < 3}
              onClick={() => teach.mutate(undefined)}
            >
              Create draft
            </Button>
          </CardSection>
        </Card>
        <Card>
          <CardSection className="space-y-3">
            <h2 className="flex items-center gap-2 font-semibold">
              <Globe className="size-4 text-accent" aria-hidden /> Learn from a
              web page
            </h2>
            <p className="text-sm text-muted-foreground">
              pi reads one public page. You review everything before it&apos;s
              used.
            </p>
            <label htmlFor="page-url" className="sr-only">
              Page address
            </label>
            <Input
              id="page-url"
              type="url"
              inputMode="url"
              placeholder="https://"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
            <Button
              variant="secondary"
              loading={website.isPending}
              disabled={!url.startsWith("https://")}
              onClick={() => website.mutate(undefined)}
            >
              Read page
            </Button>
          </CardSection>
        </Card>
        <TeachFromFile />
      </div>

      <section className="mt-8" aria-labelledby="drafts-title">
        <h2 id="drafts-title" className="mb-3 text-base font-semibold">
          Waiting for review
        </h2>
        {drafts.isPending ? (
          <LoadingBlock rows={2} />
        ) : drafts.isError ? (
          <ErrorState
            message={errorText(drafts.error)}
            onRetry={() => drafts.refetch()}
          />
        ) : drafts.data.length ? (
          <div className="grid gap-3 lg:grid-cols-2">
            {drafts.data.map((d) => (
              <DraftCard key={d.id} draft={d} />
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            No drafts. Anything you teach pi appears here first.
          </p>
        )}
      </section>

      <section className="mt-8" aria-labelledby="published-title">
        <h2 id="published-title" className="mb-3 text-base font-semibold">
          Published
        </h2>
        {documents.isPending ? (
          <LoadingBlock rows={2} />
        ) : documents.isError ? (
          <ErrorState
            message={errorText(documents.error)}
            onRetry={() => documents.refetch()}
          />
        ) : documents.data.length ? (
          <Card>
            <ul className="divide-y divide-border">
              {documents.data.map((doc) => (
                <li
                  key={doc.id}
                  className="flex items-start gap-3 px-4 py-3 sm:px-5"
                >
                  <div className="min-w-0 flex-1">
                    <p className="font-medium">{doc.title}</p>
                    <p
                      className="line-clamp-2 text-sm text-muted-foreground"
                      data-user-text
                    >
                      {doc.body}
                    </p>
                    <div className="mt-1 flex flex-wrap gap-2">
                      <Badge
                        tone={
                          doc.source_name === "Team only" ? "info" : "success"
                        }
                      >
                        {doc.source_name === "Team only"
                          ? "Team only"
                          : "Customers may be told"}
                      </Badge>
                      {doc.status !== "ready" ? (
                        <Badge tone="warning">
                          {doc.status === "failed"
                            ? "Couldn't process"
                            : "Processing"}
                        </Badge>
                      ) : null}
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`Remove ${doc.title}`}
                    loading={remove.isPending && remove.variables === doc.id}
                    onClick={() => remove.mutate(doc.id)}
                  >
                    <Trash2 className="size-4" aria-hidden />
                  </Button>
                </li>
              ))}
            </ul>
          </Card>
        ) : (
          <Card>
            <EmptyState
              icon={<MessageSquareText className="size-6" aria-hidden />}
              title="Nothing published yet"
            >
              Publish a draft so pi can answer questions.
            </EmptyState>
          </Card>
        )}
      </section>
    </Shell>
  );
}

interface PiSettings {
  response_rules: Record<string, unknown>;
  business_hours: {
    enabled: boolean;
    outside_hours: string;
    notice: string;
    days: Record<string, { open: boolean; start: string; end: string }>;
  };
  whatsapp_config: Record<string, unknown> & {
    reminder_enabled: boolean;
    reminder_after_days: number;
    reminder_templates: Record<string, { name: string; language: string }>;
  };
}

function useSettings() {
  const key = useBusinessKey();
  return useQuery({
    queryKey: key(["settings"]),
    queryFn: () => get<PiSettings>("/pi/settings"),
  });
}

function useSaveSection(section: string) {
  const client = useQueryClient();
  const key = useBusinessKey();
  return useAction(
    (value: unknown) => patch<PiSettings>(`/pi/settings/${section}`, { value }),
    {
      success: "Saved",
      onSuccess: (settings) => client.setQueryData(key(["settings"]), settings),
    },
  );
}

const DAYS: [string, string][] = [
  ["mon", "Monday"],
  ["tue", "Tuesday"],
  ["wed", "Wednesday"],
  ["thu", "Thursday"],
  ["fri", "Friday"],
  ["sat", "Saturday"],
  ["sun", "Sunday"],
];

function VoiceCard({ settings }: { settings: PiSettings }) {
  // The API merges a section with defaults, so the full current section is always sent.
  const [rules, setRules] = React.useState(settings.response_rules);
  const save = useSaveSection("response_rules");
  const set =
    (field: string) =>
    (
      e: React.ChangeEvent<
        HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement
      >,
    ) =>
      setRules((r) => ({ ...r, [field]: e.target.value }));
  return (
    <Card>
      <CardSection className="space-y-4">
        <h2 className="font-semibold">Voice</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Tone" htmlFor="tone">
            <Select
              id="tone"
              value={String(rules.tone ?? "friendly")}
              onChange={set("tone")}
            >
              <option value="friendly">Friendly</option>
              <option value="formal">Formal</option>
              <option value="concise">Short and to the point</option>
            </Select>
          </Field>
          <Field label="Summaries for your team in" htmlFor="summary-lang">
            <Select
              id="summary-lang"
              value={String(rules.staff_summary_language ?? "en")}
              onChange={set("staff_summary_language")}
            >
              {LANGUAGES.filter(([v]) => v.length <= 3).map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <Field
          label="Greeting"
          htmlFor="greeting"
          hint="pi replies in the customer's own language."
        >
          <Textarea
            id="greeting"
            value={String(rules.greeting ?? "")}
            onChange={set("greeting")}
            maxLength={2000}
            rows={2}
          />
        </Field>
        <div className="flex justify-end">
          <Button loading={save.isPending} onClick={() => save.mutate(rules)}>
            Save voice
          </Button>
        </div>
      </CardSection>
    </Card>
  );
}

function HoursCard({ settings }: { settings: PiSettings }) {
  const [hours, setHours] = React.useState(settings.business_hours);
  const save = useSaveSection("business_hours");
  return (
    <Card>
      <CardSection className="space-y-4">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="font-semibold">Opening hours</h2>
            <p className="text-sm text-muted-foreground">
              What pi does when your team is away.
            </p>
          </div>
          <Switch
            id="hours-on"
            checked={hours.enabled}
            onCheckedChange={(v) => setHours((h) => ({ ...h, enabled: v }))}
            label="Use opening hours"
          />
        </div>
        {hours.enabled ? (
          <>
            <ul className="space-y-2">
              {DAYS.map(([day, label]) => {
                const d = hours.days[day];
                return (
                  <li
                    key={day}
                    className="grid grid-cols-[6.5rem_auto_1fr] items-center gap-3 text-sm sm:grid-cols-[8rem_auto_8rem_8rem]"
                  >
                    <span>{label}</span>
                    <Switch
                      id={`open-${day}`}
                      checked={d.open}
                      onCheckedChange={(open) =>
                        setHours((h) => ({
                          ...h,
                          days: { ...h.days, [day]: { ...d, open } },
                        }))
                      }
                      label={`Open on ${label}`}
                    />
                    {d.open ? (
                      <span className="col-span-1 flex gap-2 sm:col-span-2">
                        <Input
                          aria-label={`${label} opens`}
                          type="time"
                          value={d.start}
                          onChange={(e) =>
                            setHours((h) => ({
                              ...h,
                              days: {
                                ...h.days,
                                [day]: { ...d, start: e.target.value },
                              },
                            }))
                          }
                          className="h-9"
                        />
                        <Input
                          aria-label={`${label} closes`}
                          type="time"
                          value={d.end}
                          onChange={(e) =>
                            setHours((h) => ({
                              ...h,
                              days: {
                                ...h.days,
                                [day]: { ...d, end: e.target.value },
                              },
                            }))
                          }
                          className="h-9"
                        />
                      </span>
                    ) : (
                      <span className="text-muted-foreground">Closed</span>
                    )}
                  </li>
                );
              })}
            </ul>
            <Field label="When you're closed" htmlFor="outside">
              <Select
                id="outside"
                value={hours.outside_hours}
                onChange={(e) =>
                  setHours((h) => ({ ...h, outside_hours: e.target.value }))
                }
              >
                <option value="reply">pi replies as usual</option>
                <option value="reply_with_notice">
                  pi replies and mentions your hours
                </option>
                <option value="handoff_only">
                  pi tells customers your team will reply
                </option>
              </Select>
            </Field>
            <Field label="Message about your hours" htmlFor="notice">
              <Textarea
                id="notice"
                value={hours.notice}
                onChange={(e) =>
                  setHours((h) => ({ ...h, notice: e.target.value }))
                }
                maxLength={1000}
                rows={2}
              />
            </Field>
          </>
        ) : null}
        <div className="flex justify-end">
          <Button loading={save.isPending} onClick={() => save.mutate(hours)}>
            Save hours
          </Button>
        </div>
      </CardSection>
    </Card>
  );
}

export function BehaviourPage() {
  const account = useAccount();
  const settings = useSettings();
  const can = useCan();
  if (!can("pi.settings.manage")) {
    return (
      <Shell title="Behaviour" description="How pi talks and acts.">
        <Notice tone="info">
          Only owners and admins can change how pi behaves.
        </Notice>
      </Shell>
    );
  }
  return (
    <Shell
      title="Behaviour"
      description="How pi talks, what it may share and when your team steps in."
    >
      {account.isPending || settings.isPending ? (
        <LoadingBlock rows={3} />
      ) : account.isError ? (
        <ErrorState
          message={errorText(account.error)}
          onRetry={() => account.refetch()}
        />
      ) : settings.isError ? (
        <ErrorState
          message={errorText(settings.error)}
          onRetry={() => settings.refetch()}
        />
      ) : (
        <div className="space-y-6">
          <Card>
            <CardSection>
              <HelpForm
                account={account.data}
                next={() => undefined}
                submitLabel="Save behaviour"
              />
            </CardSection>
          </Card>
          <VoiceCard settings={settings.data} />
          <HoursCard settings={settings.data} />
        </div>
      )}
    </Shell>
  );
}

const WEEKDAYS = ["mon", "tue", "wed", "thu", "fri"] as const;
const ALL_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;

interface BookableService {
  id: string;
  name: string;
  duration_minutes: number;
  buffer_minutes: number;
  working_hours: Record<string, string[][]>;
  status: string;
}

function BookingsManager() {
  const key = useBusinessKey();
  const can = useCan();
  const [name, setName] = React.useState("");
  const [duration, setDuration] = React.useState("30");
  const [buffer, setBuffer] = React.useState("0");
  const [start, setStart] = React.useState("09:00");
  const [end, setEnd] = React.useState("17:00");
  const [weekend, setWeekend] = React.useState(false);
  const connectors = useConnectors();
  const calendar = connectors.data?.find((c) => c.key === "google_calendar");
  const services = useQuery({
    queryKey: key(["bookable-services"]),
    queryFn: () => get<BookableService[]>("/pi/bookable-services"),
    enabled: can("pi.bookings.read"),
  });
  const bookings = useQuery({
    queryKey: key(["bookings"]),
    queryFn: () =>
      get<
        {
          id: string;
          label: string;
          status: string;
          service_id: string;
          created_by: string;
          external_sync: string;
        }[]
      >("/pi/bookings"),
    enabled: can("pi.bookings.read"),
  });
  const add = useAction(
    () =>
      post("/pi/bookable-services", {
        name,
        duration_minutes: Number(duration),
        buffer_minutes: Number(buffer),
        working_hours: Object.fromEntries(
          (weekend ? ALL_DAYS : WEEKDAYS).map((d) => [d, [[start, end]]]),
        ),
      }),
    {
      invalidate: [["bookable-services"]],
      success: "Service added. pi can now offer these times.",
      onSuccess: () => setName(""),
    },
  );
  const cancel = useAction((id: string) => post(`/pi/bookings/${id}/cancel`), {
    invalidate: [["bookings"]],
    success: "Booking cancelled",
  });
  if (!can("pi.bookings.read")) return null;
  const serviceName = (id: string) =>
    services.data?.find((s) => s.id === id)?.name ?? "Booking";
  return (
    <Card className="md:col-span-2">
      <CardSection className="space-y-5">
        <div>
          <h2 className="font-semibold">Bookings</h2>
          <p className="text-sm text-muted-foreground">
            pi offers free times from your working hours and books only a time
            the customer clearly agrees to. Times are rechecked before booking,
            so double bookings can&apos;t happen.{" "}
            {calendar?.state === "connected"
              ? "Busy times in your Google Calendar are skipped, and confirmed bookings are added to it."
              : calendar?.state === "action_required"
                ? "Your Google Calendar needs reconnecting; until then pi can't offer times."
                : "No calendar is connected, so keep these hours up to date."}
          </p>
        </div>
        {services.data?.length ? (
          <ul className="divide-y divide-border rounded-lg border border-border text-sm">
            {services.data.map((s) => (
              <li
                key={s.id}
                className="flex flex-wrap items-center gap-2 px-3 py-2"
              >
                <span className="flex-1 font-medium">{s.name}</span>
                <span className="text-muted-foreground">
                  {s.duration_minutes} min
                  {s.buffer_minutes ? ` + ${s.buffer_minutes} min break` : ""}
                </span>
                <Badge tone={s.status === "active" ? "success" : "neutral"}>
                  {s.status}
                </Badge>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">
            No bookable services yet.
          </p>
        )}
        {can("pi.bookings.manage") ? (
          <div className="grid gap-3 rounded-lg border border-dashed border-border-strong p-3 sm:grid-cols-2 lg:grid-cols-6">
            <Field label="Service" htmlFor="bs-name">
              <Input
                id="bs-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={160}
                placeholder="Consultation"
              />
            </Field>
            <Field label="Length" htmlFor="bs-duration">
              <Select
                id="bs-duration"
                value={duration}
                onChange={(e) => setDuration(e.target.value)}
              >
                {[15, 30, 45, 60, 90, 120].map((m) => (
                  <option key={m} value={m}>
                    {m} min
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Break after" htmlFor="bs-buffer">
              <Select
                id="bs-buffer"
                value={buffer}
                onChange={(e) => setBuffer(e.target.value)}
              >
                {[0, 5, 10, 15, 30].map((m) => (
                  <option key={m} value={m}>
                    {m} min
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="From" htmlFor="bs-start">
              <Input
                id="bs-start"
                type="time"
                value={start}
                onChange={(e) => setStart(e.target.value)}
              />
            </Field>
            <Field label="Until" htmlFor="bs-end">
              <Input
                id="bs-end"
                type="time"
                value={end}
                onChange={(e) => setEnd(e.target.value)}
              />
            </Field>
            <div className="flex flex-col justify-end gap-2">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  className="size-4 accent-accent"
                  checked={weekend}
                  onChange={(e) => setWeekend(e.target.checked)}
                />
                Weekends too
              </label>
              <Button
                loading={add.isPending}
                disabled={!name.trim() || start >= end}
                onClick={() => add.mutate(undefined)}
              >
                Add
              </Button>
            </div>
          </div>
        ) : null}
        <div>
          <h3 className="mb-2 text-sm font-medium">Upcoming</h3>
          {bookings.data?.length ? (
            <ul className="divide-y divide-border text-sm">
              {bookings.data.map((b) => (
                <li
                  key={b.id}
                  className="flex flex-wrap items-center gap-2 py-2"
                >
                  <span className="flex-1">
                    {serviceName(b.service_id)} · {b.label}
                    <span className="block text-xs text-muted-foreground">
                      Booked by {b.created_by}
                      {b.external_sync === "failed"
                        ? " · Not added to your calendar"
                        : b.external_sync === "pending"
                          ? " · Adding to your calendar…"
                          : ""}
                    </span>
                  </span>
                  {can("pi.bookings.manage") ? (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => cancel.mutate(b.id)}
                    >
                      Cancel
                    </Button>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">
              No upcoming bookings.
            </p>
          )}
        </div>
      </CardSection>
    </Card>
  );
}

export function ToolsPage() {
  const account = useAccount();
  return (
    <Shell
      title="Tools"
      description="What pi may do for customers. Each tool follows your approval rules."
    >
      {account.isPending ? (
        <LoadingBlock rows={3} />
      ) : account.isError ? (
        <ErrorState
          message={errorText(account.error)}
          onRetry={() => account.refetch()}
        />
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {account.data.tool_groups.map((group) => {
            const [name, body] = TOOL_LABEL[group] ?? [group, ""];
            const on = account.data.tools.includes(group);
            const available = AVAILABLE_TOOL_GROUPS.has(group);
            return (
              <Card key={group}>
                <CardSection className="space-y-2">
                  <div className="flex items-center gap-2">
                    <h2 className="font-semibold">{name}</h2>
                    <span className="ms-auto">
                      {!available ? (
                        <Badge>Not available yet</Badge>
                      ) : on ? (
                        <Badge tone="success">On</Badge>
                      ) : (
                        <Badge>Off</Badge>
                      )}
                    </span>
                  </div>
                  <p className="text-sm text-muted-foreground">{body}</p>
                  {!available ? (
                    <p className="text-sm text-muted-foreground">
                      This tool isn&apos;t switched on for pi yet. pi will hand
                      these requests to your team.
                    </p>
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      {group === "catalog_orders"
                        ? "Orders are only placed after the customer confirms the summary. Stock is checked live."
                        : group === "quotes"
                          ? "Quotes are drafts until your team approves and sends them."
                          : group === "bookings"
                            ? "Only times you offer, only after the customer agrees. Customers can only see or cancel their own bookings."
                            : group === "tickets"
                              ? "Problems are logged with a priority and a response target for your team."
                              : group === "tasks"
                                ? "pi creates follow-up tasks; customers only see the status you mark as shareable."
                                : "Only the current customer's own records are used."}
                    </p>
                  )}
                </CardSection>
              </Card>
            );
          })}
          <ConnectorsSection />
          {account.data.tools.includes("bookings") ? <BookingsManager /> : null}
          <Notice tone="info" title="Turn tools on or off">
            Choose which tools pi may use in{" "}
            <Link className="text-accent underline" href="/my-pi/behaviour">
              Behaviour
            </Link>
            .
          </Notice>
        </div>
      )}
    </Shell>
  );
}

export function FollowUpsPage() {
  const settings = useSettings();
  return (
    <Shell
      title="Follow-ups"
      description="pi can remind a customer once if they went quiet — only if they agreed."
    >
      {settings.isPending ? (
        <LoadingBlock rows={2} />
      ) : settings.isError ? (
        <ErrorState
          message={errorText(settings.error)}
          onRetry={() => settings.refetch()}
        />
      ) : (
        <>
          <FollowUpsForm initial={settings.data.whatsapp_config} />
          <RemindersAndForms />
          <OneClickForms />
          <TemplatesCard />
        </>
      )}
    </Shell>
  );
}

function FollowUpsForm({
  initial,
}: {
  initial: PiSettings["whatsapp_config"];
}) {
  const can = useCan();
  const save = useSaveSection("whatsapp_config");
  const client = useQueryClient();
  const key = useBusinessKey();
  const [config, setConfig] = React.useState(initial);
  const [lang, setLang] = React.useState("en");
  const [template, setTemplate] = React.useState("");
  const [templateLang, setTemplateLang] = React.useState("en_US");
  return (
    <>
      {
        <Card>
          <CardSection className="space-y-5">
            <div className="flex items-center justify-between gap-4">
              <div>
                <h2 className="font-semibold">Friendly reminders</h2>
                <p className="text-sm text-muted-foreground">
                  One reminder per unanswered message, never a loop. A reply,
                  opt-out or takeover cancels it.
                </p>
              </div>
              <Switch
                id="reminders"
                checked={config.reminder_enabled}
                disabled={!can("pi.settings.manage")}
                onCheckedChange={(v) =>
                  setConfig((c) => ({ ...c, reminder_enabled: v }))
                }
                label="Send reminders"
              />
            </div>
            <Field
              label="Remind after"
              htmlFor="after"
              hint="Days after pi's last message without a reply."
            >
              <Select
                id="after"
                value={String(config.reminder_after_days)}
                onChange={(e) =>
                  setConfig((c) =>
                    c
                      ? { ...c, reminder_after_days: Number(e.target.value) }
                      : c,
                  )
                }
              >
                {[1, 2, 3, 5, 7, 10, 14, 21, 30].map((d) => (
                  <option key={d} value={d}>
                    {d} day{d === 1 ? "" : "s"}
                  </option>
                ))}
              </Select>
            </Field>
            <div>
              <h3 className="text-sm font-medium">
                Approved WhatsApp templates
              </h3>
              <p className="text-sm text-muted-foreground">
                WhatsApp requires an approved message template for reminders.
                Add one for each language your customers use.
              </p>
              <ul className="mt-2 space-y-1 text-sm">
                {Object.entries(config.reminder_templates).map(
                  ([language, t]) => (
                    <li key={language} className="flex items-center gap-2">
                      <Badge>{language}</Badge> {t.name} ({t.language})
                      <Button
                        variant="ghost"
                        size="sm"
                        aria-label={`Remove ${language} template`}
                        onClick={() =>
                          setConfig((c) => {
                            if (!c) return c;
                            const next = { ...c.reminder_templates };
                            delete next[language];
                            return { ...c, reminder_templates: next };
                          })
                        }
                      >
                        <Trash2 className="size-4" aria-hidden />
                      </Button>
                    </li>
                  ),
                )}
                {!Object.keys(config.reminder_templates).length ? (
                  <li className="text-muted-foreground">
                    No templates yet — reminders can&apos;t be sent until you
                    add one.
                  </li>
                ) : null}
              </ul>
              <div className="mt-3 grid gap-2 sm:grid-cols-[8rem_1fr_7rem_auto]">
                <Select
                  aria-label="Customer language"
                  value={lang}
                  onChange={(e) => setLang(e.target.value)}
                >
                  {LANGUAGES.map(([v, l]) => (
                    <option key={v} value={v}>
                      {l}
                    </option>
                  ))}
                </Select>
                <Input
                  aria-label="Template name"
                  placeholder="template_name"
                  value={template}
                  onChange={(e) => setTemplate(e.target.value.toLowerCase())}
                />
                <Input
                  aria-label="Template language code"
                  placeholder="en_US"
                  value={templateLang}
                  onChange={(e) => setTemplateLang(e.target.value)}
                />
                <Button
                  variant="secondary"
                  disabled={!/^[a-z0-9_]{1,512}$/.test(template)}
                  onClick={() => {
                    setConfig((c) =>
                      c
                        ? {
                            ...c,
                            reminder_templates: {
                              ...c.reminder_templates,
                              [lang]: {
                                name: template,
                                language: templateLang,
                              },
                            },
                          }
                        : c,
                    );
                    setTemplate("");
                  }}
                >
                  Add
                </Button>
              </div>
            </div>
            {can("pi.settings.manage") ? (
              <div className="flex justify-end">
                <Button
                  loading={save.isPending}
                  onClick={() =>
                    // Only this form's fields, over the latest saved settings (quiet
                    // hours and WhatsApp forms are edited separately on this page).
                    save.mutate({
                      ...(client.getQueryData<PiSettings>(key(["settings"]))
                        ?.whatsapp_config ?? initial),
                      reminder_enabled: config.reminder_enabled,
                      reminder_after_days: config.reminder_after_days,
                      reminder_templates: config.reminder_templates,
                    })
                  }
                >
                  Save follow-ups
                </Button>
              </div>
            ) : null}
          </CardSection>
        </Card>
      }
    </>
  );
}

export function TestPiPage() {
  return (
    <Shell
      title="Test pi"
      description="Chat with pi the way a customer would. Nothing is sent and nothing is saved."
    >
      <TestConversation includeDraftsToggle />
    </Shell>
  );
}
