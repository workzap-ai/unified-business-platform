"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  CircleHelp,
  ExternalLink,
  Globe,
  LifeBuoy,
  Plus,
  Rocket,
  Smartphone,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import {
  Badge,
  Button,
  Card,
  CardSection,
  ErrorState,
  Field,
  Input,
  LoadingBlock,
  Notice,
  Select,
  Textarea,
  cn,
} from "@/components/ui";
import { WhatsAppAccess } from "@/features/journey";
import { PoolNumberPicker } from "@/features/number-picker";
import { TestConversation } from "@/features/test-pi";
import { errorText, get, post, put } from "@/lib/api";
import { useAction, useBusinessKey } from "@/lib/session";
import type { Account, Draft, SessionView } from "@/lib/types";
import product from "@/components/product.module.css";

const STEPS = [
  { n: 1, title: "Your business" },
  { n: 2, title: "What you offer" },
  { n: 3, title: "Connect WhatsApp" },
  { n: 4, title: "How pi should help" },
  { n: 5, title: "Try pi and launch" },
];

export const LANGUAGES: [string, string][] = [
  ["en", "English"],
  ["ar", "Arabic"],
  ["ur", "Urdu"],
  ["roman_ur", "Roman Urdu"],
  ["hi", "Hindi"],
  ["es", "Spanish"],
  ["fr", "French"],
  ["de", "German"],
  ["pt", "Portuguese"],
];

export const CURRENCIES = ["PKR", "USD", "AED", "SAR", "EUR", "GBP"];

function guessCurrency(timezone: string): string {
  if (timezone === "Asia/Karachi") return "PKR";
  if (timezone === "Asia/Dubai") return "AED";
  if (timezone === "Asia/Riyadh") return "SAR";
  if (timezone === "Europe/London") return "GBP";
  if (timezone.startsWith("Europe/")) return "EUR";
  return "USD";
}

function timezones(): string[] {
  try {
    return (
      Intl as unknown as { supportedValuesOf(k: string): string[] }
    ).supportedValuesOf("timeZone");
  } catch {
    return [
      "UTC",
      "Asia/Dubai",
      "Asia/Riyadh",
      "Asia/Karachi",
      "Europe/London",
      "America/New_York",
    ];
  }
}

export function useAccount() {
  const key = useBusinessKey();
  return useQuery({
    queryKey: key(["account"]),
    queryFn: () => get<Account>("/account"),
  });
}

function Stepper({
  step,
  done,
  onGo,
}: {
  step: number;
  done: number[];
  onGo: (n: number) => void;
}) {
  return (
    <>
      <ol
        className="mb-2 flex min-w-0 flex-wrap gap-1.5 sm:mb-6 sm:gap-2"
        aria-label="Setup progress"
      >
        {STEPS.map((s) => {
          const complete = done.includes(s.n);
          const current = s.n === step;
          return (
            <li key={s.n} className="shrink-0">
              <button
                onClick={() => onGo(s.n)}
                aria-current={current ? "step" : undefined}
                className={cn(
                  "flex h-10 items-center gap-2 rounded-full border px-2 text-sm sm:px-3",
                  current
                    ? "border-accent bg-accent-soft font-semibold text-accent-soft-foreground"
                    : "border-border bg-surface text-foreground-secondary hover:bg-surface-muted",
                )}
              >
                <span
                  className={cn(
                    "flex size-6 items-center justify-center rounded-full text-xs",
                    complete
                      ? "bg-accent text-accent-foreground"
                      : "bg-surface-sunken",
                  )}
                  aria-hidden
                >
                  {complete ? <Check className="size-3.5" /> : s.n}
                </span>
                <span className="sr-only sm:not-sr-only">{s.title}</span>
                <span className="sr-only">{complete ? "(done)" : ""}</span>
              </button>
            </li>
          );
        })}
      </ol>
      <p className="mb-6 text-sm font-medium text-foreground-secondary sm:hidden">
        Step {step} of {STEPS.length} · {STEPS.find((s) => s.n === step)?.title}
      </p>
    </>
  );
}

function StepCard({
  title,
  description,
  children,
  footer,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
  footer: React.ReactNode;
}) {
  return (
    <Card className="animate-rise">
      <CardSection>
        <h2 className="text-xl font-semibold">{title}</h2>
        <p className="mt-1 text-[15px] text-muted-foreground">{description}</p>
        <div className="mt-6 space-y-5">{children}</div>
      </CardSection>
      <div className="flex flex-col-reverse gap-2 border-t border-border px-5 py-4 sm:flex-row sm:items-center sm:justify-end sm:px-6">
        {footer}
      </div>
    </Card>
  );
}

function useSaveStep(step: number, onDone: () => void) {
  const client = useQueryClient();
  const key = useBusinessKey();
  return useAction(
    (body: unknown) => put<Account>(`/account/onboarding/${step}`, body),
    {
      onSuccess: (account) => {
        client.setQueryData(key(["account"]), account);
        client.invalidateQueries({ queryKey: ["session"] });
        onDone();
      },
      success: "Saved",
    },
  );
}

function SavedState({ dirty }: { dirty: boolean }) {
  return (
    <span className="me-auto text-sm text-muted-foreground" aria-live="polite">
      {dirty ? "Unsaved changes" : "All changes saved"}
    </span>
  );
}

function BusinessStep({
  account,
  next,
}: {
  account: Account;
  next: () => void;
}) {
  const [values, setValues] = React.useState({
    name: account.name,
    business_category: account.business_category,
    language: account.language || "en",
    timezone:
      account.timezone && account.timezone !== "UTC"
        ? account.timezone
        : Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
    website: account.website,
    description: account.description,
    currency:
      account.currency && account.currency !== "USD"
        ? account.currency
        : guessCurrency(
            account.timezone && account.timezone !== "UTC"
              ? account.timezone
              : Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
          ),
  });
  const [dirty, setDirty] = React.useState(false);
  const save = useSaveStep(1, () => {
    setDirty(false);
    next();
  });
  const set =
    (field: keyof typeof values) =>
    (
      event: React.ChangeEvent<
        HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement
      >,
    ) => {
      setValues((v) => ({ ...v, [field]: event.target.value }));
      setDirty(true);
    };
  const zones = React.useMemo(() => timezones(), []);
  return (
    <StepCard
      title="Tell us about your business"
      description="pi uses this to introduce itself and to know when you're open."
      footer={
        <>
          <SavedState dirty={dirty} />
          <Button
            loading={save.isPending}
            disabled={!values.name.trim()}
            onClick={() =>
              save.mutate({
                ...values,
                website: values.website.trim() || null,
                country: "",
              })
            }
          >
            Save and continue
          </Button>
        </>
      }
    >
      <div className="grid gap-5 sm:grid-cols-2">
        <Field label="Business name" htmlFor="b-name">
          <Input
            id="b-name"
            value={values.name}
            onChange={set("name")}
            maxLength={160}
            required
          />
        </Field>
        <Field
          label="Type of business"
          htmlFor="b-cat"
          optional
          hint="For example: salon, web agency, bakery"
        >
          <Input
            id="b-cat"
            value={values.business_category}
            onChange={set("business_category")}
            maxLength={60}
          />
        </Field>
        <Field
          label="Your team's language"
          htmlFor="b-lang"
          hint="Summaries for your team use this language. pi replies to customers in theirs."
        >
          <Select
            id="b-lang"
            value={values.language}
            onChange={set("language")}
          >
            {LANGUAGES.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Time zone" htmlFor="b-tz">
          <Select id="b-tz" value={values.timezone} onChange={set("timezone")}>
            {zones.map((zone) => (
              <option key={zone} value={zone}>
                {zone.replaceAll("_", " ")}
              </option>
            ))}
          </Select>
        </Field>
        <Field
          label="Currency"
          htmlFor="b-currency"
          hint="Used on your invoices and payment requests."
        >
          <Select
            id="b-currency"
            value={values.currency}
            onChange={set("currency")}
          >
            {CURRENCIES.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </Select>
        </Field>
      </div>
      <Field
        label="Website"
        htmlFor="b-web"
        optional
        hint="We can read your homepage to get pi started."
      >
        <Input
          id="b-web"
          type="url"
          inputMode="url"
          placeholder="https://"
          value={values.website}
          onChange={set("website")}
        />
      </Field>
      <Field
        label="In a sentence or two, what do you do?"
        htmlFor="b-desc"
        optional
      >
        <Textarea
          id="b-desc"
          value={values.description}
          onChange={set("description")}
          maxLength={2000}
        />
      </Field>
    </StepCard>
  );
}

interface Offering {
  name: string;
  description: string;
  price: string;
  currency: string;
}

function OfferStep({ account, next }: { account: Account; next: () => void }) {
  const key = useBusinessKey();
  const [offerType, setOfferType] = React.useState(account.offer_type);
  const [items, setItems] = React.useState<Offering[]>([
    { name: "", description: "", price: "", currency: "USD" },
  ]);
  const drafts = useQuery({
    queryKey: key(["drafts"]),
    queryFn: () => get<Draft[]>("/knowledge/drafts"),
  });
  const importSite = useAction(
    (url: string) => post<Draft>("/knowledge/website", { url }),
    {
      invalidate: [["drafts"]],
      success: "We read your website. Check what pi learned below.",
    },
  );
  const publish = useAction(
    (id: string) => post<Draft>(`/knowledge/drafts/${id}/publish`),
    {
      invalidate: [["drafts"], ["account"]],
      success: "Published. pi can use this now.",
    },
  );
  const save = useSaveStep(2, next);
  const filled = items.filter((i) => i.name.trim());
  const priced = offerType !== "services";
  return (
    <StepCard
      title="What do you offer?"
      description="Add a few of your main services or products. You can add more later."
      footer={
        <Button
          loading={save.isPending}
          onClick={() =>
            save.mutate({
              offer_type: offerType,
              offerings: filled.map((i) => ({
                name: i.name.trim(),
                description: i.description.trim(),
                price: priced && i.price.trim() ? i.price.trim() : null,
                currency: i.currency,
              })),
            })
          }
        >
          Save and continue
        </Button>
      }
    >
      <fieldset>
        <legend className="mb-2 text-sm font-medium">You sell</legend>
        <div className="grid gap-2 sm:grid-cols-3">
          {(
            [
              ["services", "Services", "Projects, appointments, consulting"],
              ["products", "Products", "A shop with orders and delivery"],
              ["both", "Both", "Services and products"],
            ] as const
          ).map(([value, label, hint]) => (
            <label
              key={value}
              className={cn(
                "flex cursor-pointer flex-col rounded-lg border p-3 has-focus-visible:outline-2 has-focus-visible:outline-ring",
                offerType === value
                  ? "border-accent bg-accent-soft"
                  : "border-border bg-surface hover:bg-surface-muted",
              )}
            >
              <input
                type="radio"
                name="offer_type"
                value={value}
                checked={offerType === value}
                onChange={() => setOfferType(value)}
                className="sr-only"
              />
              <span className="font-medium">{label}</span>
              <span className="text-sm text-muted-foreground">{hint}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <div className="space-y-3">
        <p className="text-sm font-medium">
          Your main {offerType === "products" ? "products" : "services"}
        </p>
        {items.map((item, index) => (
          <div
            key={index}
            className="grid gap-2 rounded-lg border border-border p-3 sm:grid-cols-[1fr_1.4fr_auto]"
          >
            <Input
              aria-label={`Name ${index + 1}`}
              placeholder="Name"
              value={item.name}
              onChange={(e) =>
                setItems((all) =>
                  all.map((x, i) =>
                    i === index ? { ...x, name: e.target.value } : x,
                  ),
                )
              }
            />
            <Input
              aria-label={`Short description ${index + 1}`}
              placeholder="Short description (optional)"
              value={item.description}
              onChange={(e) =>
                setItems((all) =>
                  all.map((x, i) =>
                    i === index ? { ...x, description: e.target.value } : x,
                  ),
                )
              }
            />
            <Button
              variant="ghost"
              size="icon"
              aria-label={`Remove ${item.name || "row " + (index + 1)}`}
              onClick={() =>
                setItems((all) =>
                  all.length > 1 ? all.filter((_, i) => i !== index) : all,
                )
              }
            >
              <Trash2 className="size-4" aria-hidden />
            </Button>
            {priced ? (
              <div className="flex gap-2 sm:col-span-3">
                <Input
                  aria-label={`Price ${index + 1}`}
                  placeholder="Price (optional)"
                  inputMode="decimal"
                  value={item.price}
                  onChange={(e) =>
                    setItems((all) =>
                      all.map((x, i) =>
                        i === index ? { ...x, price: e.target.value } : x,
                      ),
                    )
                  }
                />
                <Select
                  aria-label={`Currency ${index + 1}`}
                  className="w-28"
                  value={item.currency}
                  onChange={(e) =>
                    setItems((all) =>
                      all.map((x, i) =>
                        i === index ? { ...x, currency: e.target.value } : x,
                      ),
                    )
                  }
                >
                  {["USD", "EUR", "GBP", "AED", "SAR", "PKR"].map((c) => (
                    <option key={c}>{c}</option>
                  ))}
                </Select>
              </div>
            ) : null}
          </div>
        ))}
        <Button
          variant="secondary"
          size="sm"
          onClick={() =>
            setItems((all) => [
              ...all,
              { name: "", description: "", price: "", currency: "USD" },
            ])
          }
          disabled={items.length >= 20}
        >
          <Plus className="size-4" aria-hidden /> Add another
        </Button>
        {priced ? (
          <p className="text-sm text-muted-foreground">
            Only prices you enter here become prices pi may share. You choose
            how pi talks about prices in step 4.
          </p>
        ) : null}
      </div>

      {account.website ? (
        <Notice
          tone="info"
          title="Learn from your website"
          action={
            <Button
              variant="secondary"
              size="sm"
              loading={importSite.isPending}
              onClick={() => importSite.mutate(account.website)}
            >
              <Globe className="size-4" aria-hidden /> Read{" "}
              {new URL(account.website).hostname}
            </Button>
          }
        >
          pi reads one page and shows you what it learned. Nothing is used until
          you publish it.
        </Notice>
      ) : null}

      {drafts.data && drafts.data.length > 0 ? (
        <div className="space-y-2">
          <p className="text-sm font-medium">Waiting for your review</p>
          {drafts.data.map((draft) => (
            <div
              key={draft.id}
              className="rounded-lg border border-border bg-surface-muted p-3"
            >
              <div className="flex items-start justify-between gap-3">
                <p className="font-medium">{draft.title}</p>
                <Button
                  size="sm"
                  loading={publish.isPending && publish.variables === draft.id}
                  onClick={() => publish.mutate(draft.id)}
                >
                  Publish
                </Button>
              </div>
              <p
                data-user-text
                className="mt-1 line-clamp-4 whitespace-pre-line text-sm text-foreground-secondary"
              >
                {draft.content}
              </p>
            </div>
          ))}
          <p className="text-sm text-muted-foreground">
            Edit drafts anytime in{" "}
            <Link className="text-accent underline" href="/my-pi/knowledge">
              My pi → Business knowledge
            </Link>
            .
          </p>
        </div>
      ) : null}
    </StepCard>
  );
}

export function WhatsAppConnect({
  account,
  onDone,
}: {
  account: Account;
  onDone?: () => void;
}) {
  const key = useBusinessKey();
  const status = useQuery({
    queryKey: key(["whatsapp"]),
    queryFn: () =>
      get<{
        production: Account["whatsapp"];
        provider_available: boolean;
        new_number_countries: string[];
      }>("/whatsapp"),
  });
  // "new" = a number from the platform's pool (the default).
  const [choice, setChoice] = React.useState<"existing" | "new">(
    account.whatsapp_choice ?? "new",
  );
  const [country, setCountry] = React.useState("");
  const [coexist, setCoexist] = React.useState(true);
  const start = useAction(
    () =>
      post<Account["whatsapp"]>("/whatsapp/setup", {
        connection_types: coexist
          ? ["coexistence", "dedicated"]
          : ["dedicated"],
      }),
    {
      invalidate: [["whatsapp"], ["account"]],
      onSuccess: (view) => {
        if (view.setup_url) window.location.assign(view.setup_url);
      },
    },
  );
  const request = useAction(
    () => post("/whatsapp/number-request", { country }),
    {
      invalidate: [["whatsapp"], ["account"]],
      success:
        "Request sent. We'll show you the price before anything is bought.",
    },
  );
  const confirmQuote = useAction(
    () => post("/whatsapp/number-request/confirm"),
    {
      invalidate: [["whatsapp"], ["account"]],
      success:
        "Thanks. We'll prepare your number and send you the link to finish.",
    },
  );
  if (status.isPending) return <LoadingBlock rows={2} />;
  if (status.isError)
    return (
      <ErrorState
        message={errorText(status.error)}
        onRetry={() => status.refetch()}
      />
    );
  const connection = status.data.production;
  if (connection.status === "connected") {
    return (
      <Notice
        tone="success"
        title="WhatsApp is connected"
        action={onDone ? <Button onClick={onDone}>Continue</Button> : null}
      >
        {connection.display_phone_number} is linked to pi.
      </Notice>
    );
  }
  const quote = connection.number_request?.quote;
  return (
    <div className="space-y-5">
      <WhatsAppAccess />
      {!status.data.provider_available ? (
        <Notice tone="warning" title="WhatsApp connection isn't available yet">
          Our WhatsApp provider isn&apos;t switched on for this service yet.
          Choose &ldquo;Help me set up&rdquo; and our team will contact you.
        </Notice>
      ) : null}
      {connection.status === "disconnected" ||
      connection.status === "action_required" ? (
        <Notice tone="danger" title="Your number needs to be reconnected">
          pi stopped replying on this number. Reconnect it below; your
          conversations are kept.
        </Notice>
      ) : null}
      <fieldset>
        <legend className="mb-2 text-sm font-medium">
          Which number should pi use?
        </legend>
        <div className="grid gap-2 sm:grid-cols-2">
          {(
            [
              [
                "new",
                "Choose a number from us",
                "Pick a ready number. We provide it and WhatsApp fees are part of your plan.",
              ],
              [
                "existing",
                "Use my own number (advanced)",
                "Keep your number. You can keep using the WhatsApp Business app on your phone where supported.",
              ],
            ] as const
          ).map(([value, label, hint]) => (
            <label
              key={value}
              className={cn(
                "flex cursor-pointer flex-col rounded-lg border p-4 has-focus-visible:outline-2 has-focus-visible:outline-ring",
                choice === value
                  ? "border-accent bg-accent-soft"
                  : "border-border bg-surface hover:bg-surface-muted",
              )}
            >
              <input
                type="radio"
                name="wa-choice"
                value={value}
                checked={choice === value}
                onChange={() => setChoice(value)}
                className="sr-only"
              />
              <span className="flex items-center gap-2 font-medium">
                <Smartphone className="size-4" aria-hidden /> {label}
              </span>
              <span className="mt-1 text-sm text-muted-foreground">{hint}</span>
            </label>
          ))}
        </div>
      </fieldset>
      {choice === "existing" ? (
        <div className="space-y-3">
          <label className="flex items-start gap-3 text-sm">
            <input
              type="checkbox"
              className="mt-1 size-4 accent-accent"
              checked={coexist}
              onChange={(e) => setCoexist(e.target.checked)}
            />
            <span>
              I want to keep using the WhatsApp Business app on my phone too.
              <span className="block text-muted-foreground">
                Messages from before the connection may not all be available in
                pi.
              </span>
            </span>
          </label>
          <p className="text-sm text-muted-foreground">
            You&apos;ll sign in with Facebook/Meta on a secure page to confirm
            you own the number. We never see your password.
          </p>
          {connection.status === "setup_pending" && connection.setup_url ? (
            <Button asChild>
              <a href={connection.setup_url}>
                Continue connecting{" "}
                <ExternalLink className="size-4" aria-hidden />
              </a>
            </Button>
          ) : (
            <Button
              loading={start.isPending}
              disabled={!status.data.provider_available}
              onClick={() => start.mutate(undefined)}
            >
              Connect WhatsApp
            </Button>
          )}
        </div>
      ) : (
        <PoolNumberPicker
          onChosen={onDone}
          fallback={
            <div className="space-y-3">
              {quote ? (
                <Notice tone="info" title="Your number quote">
                  <p>
                    {quote.number ? `${quote.number}: ` : ""}
                    {quote.monthly_price} {quote.currency} per month
                    {Number(quote.setup_fee) > 0
                      ? ` plus ${quote.setup_fee} ${quote.currency} one-time`
                      : ""}
                    . {quote.note}
                  </p>
                  {connection.number_request?.status === "quoted" ? (
                    <Button
                      className="mt-3"
                      loading={confirmQuote.isPending}
                      onClick={() => confirmQuote.mutate(undefined)}
                    >
                      I agree to these charges
                    </Button>
                  ) : (
                    <p className="mt-2 font-medium">
                      Confirmed. We&apos;ll send you a link to finish.
                    </p>
                  )}
                </Notice>
              ) : connection.number_request?.status === "requested" ? (
                <Notice tone="info" title="Checking availability">
                  We&apos;re checking real numbers for{" "}
                  {connection.number_request.country}. You&apos;ll see the price
                  here before anything is bought.
                </Notice>
              ) : (
                <>
                  <Field
                    label="Country"
                    htmlFor="wa-country"
                    hint="Local numbers aren't available in every country."
                  >
                    <Select
                      id="wa-country"
                      value={country}
                      onChange={(e) => setCountry(e.target.value)}
                    >
                      <option value="">Choose a country</option>
                      {[
                        ["US", "United States"],
                        ["GB", "United Kingdom"],
                        ["DE", "Germany"],
                        ["FR", "France"],
                        ["ES", "Spain"],
                        ["NL", "Netherlands"],
                        ["AE", "United Arab Emirates"],
                        ["SA", "Saudi Arabia"],
                      ].map(([code, name]) => (
                        <option key={code} value={code}>
                          {name}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  <Button
                    loading={request.isPending}
                    disabled={!country}
                    onClick={() => request.mutate(undefined)}
                  >
                    Check availability
                  </Button>
                </>
              )}
            </div>
          }
        />
      )}
    </div>
  );
}

const GOAL_LABEL: Record<string, string> = {
  answer_questions: "Answer common questions",
  capture_leads: "Collect enquiries and requirements",
  book_appointments: "Book appointments",
  take_orders: "Take orders",
  order_status: "Share order status",
  quotes: "Prepare quotes for my approval",
  payments: "Collect payment for invoices",
  support: "Handle support issues",
  follow_ups: "Follow up when customers go quiet (with permission)",
};
// Tool groups backed by controlled tools in this release. The others are listed so
// businesses know they're planned, but can't be switched on.
export const AVAILABLE_TOOL_GROUPS = new Set([
  "knowledge",
  "customers",
  "catalog_orders",
  "quotes",
  "billing_status",
  "bookings",
  "tasks",
  "tickets",
  "payments",
  "forms",
]);

export const TOOL_LABEL: Record<string, [string, string]> = {
  knowledge: ["Your business information", "Answer from what you've published"],
  customers: ["Customer memory", "Remember returning customers' details"],
  catalog_orders: [
    "Catalog and orders",
    "Check stock, draft orders, share order status",
  ],
  quotes: ["Quotes", "Draft quotations for your approval"],
  billing_status: ["Invoices", "Tell customers their own invoice status"],
  bookings: ["Bookings", "Offer times and book appointments"],
  tasks: ["Tasks", "Create follow-up tasks for your team"],
  tickets: ["Support tickets", "Log issues for your team"],
  forms: [
    "WhatsApp forms",
    "Send your lead, booking or feedback form (set up in My pi → Follow-ups)",
  ],
  payments: [
    "Payments",
    "Share how to pay an open invoice (card, bank, wallet or cash)",
  ],
};
export const PRICE_LABEL: Record<string, [string, string]> = {
  exact: ["Share exact prices", "Only prices you've approved in your catalog"],
  starting: ["Share starting prices", '"From …" prices you\'ve approved'],
  quote: ["Prepare a quote", "Collect details; your team sends the price"],
  ask_team: ["Ask my team", "pi says a team member will share pricing"],
  hidden: ["Never discuss prices", "pi politely declines price questions"],
};
export const MODE_LABEL: Record<string, [string, string]> = {
  human_approved: [
    "I approve every reply",
    "pi drafts, you send. Best for your first days.",
  ],
  mixed: [
    "I approve actions",
    "pi answers questions; orders, bookings and quotes wait for you.",
  ],
  ai_led: [
    "pi replies on its own",
    "You can take over any conversation at any time.",
  ],
};

export function HelpForm({
  account,
  next,
  step = 4,
  submitLabel = "Save and continue",
}: {
  account: Account;
  next: () => void;
  step?: number;
  submitLabel?: string;
}) {
  const [goals, setGoals] = React.useState<string[]>(account.goals);
  const [mode, setMode] = React.useState(account.automation_mode);
  const [price, setPrice] = React.useState(account.price_disclosure);
  const [tools, setTools] = React.useState<string[]>(
    account.tools.length ? account.tools : ["knowledge", "customers"],
  );
  const save = useSaveStep(step, next);
  const toggle = (list: string[], value: string) =>
    list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
  return (
    <div className="space-y-6">
      <fieldset>
        <legend className="mb-2 text-sm font-medium">
          What should pi help with?
        </legend>
        <div className="grid gap-2 sm:grid-cols-2">
          {account.goals_available.map((goal) => (
            <label
              key={goal}
              className="flex min-h-11 cursor-pointer items-center gap-3 rounded-lg border border-border px-3 py-2 text-sm hover:bg-surface-muted"
            >
              <input
                type="checkbox"
                className="size-4 accent-accent"
                checked={goals.includes(goal)}
                onChange={() => setGoals((g) => toggle(g, goal))}
              />
              {GOAL_LABEL[goal] ?? goal}
            </label>
          ))}
        </div>
      </fieldset>
      <RadioCards
        legend="How much should pi do on its own?"
        name="mode"
        value={mode}
        options={MODE_LABEL}
        onChange={(v) => setMode(v as Account["automation_mode"])}
      />
      <RadioCards
        legend="How should pi talk about prices?"
        name="price"
        value={price}
        options={PRICE_LABEL}
        onChange={(v) => setPrice(v as Account["price_disclosure"])}
      />
      <fieldset>
        <legend className="mb-2 text-sm font-medium">What may pi use?</legend>
        <div className="grid gap-2 sm:grid-cols-2">
          {account.tool_groups.map((group) => {
            const available = AVAILABLE_TOOL_GROUPS.has(group);
            return (
              <label
                key={group}
                className={cn(
                  "flex items-start gap-3 rounded-lg border border-border p-3 text-sm",
                  available
                    ? "cursor-pointer hover:bg-surface-muted"
                    : "cursor-not-allowed opacity-70",
                )}
              >
                <input
                  type="checkbox"
                  className="mt-0.5 size-4 accent-accent"
                  checked={available && tools.includes(group)}
                  disabled={!available}
                  onChange={() => setTools((t) => toggle(t, group))}
                />
                <span>
                  <span className="block font-medium">
                    {TOOL_LABEL[group]?.[0] ?? group}
                    {available ? null : (
                      <Badge className="ms-2">Not available yet</Badge>
                    )}
                  </span>
                  <span className="text-muted-foreground">
                    {TOOL_LABEL[group]?.[1]}
                  </span>
                </span>
              </label>
            );
          })}
        </div>
        <p className="mt-2 text-sm text-muted-foreground">
          Some tools also need a connection, like your calendar. Set those up in
          My pi → Tools.
        </p>
      </fieldset>
      <div className="flex justify-end">
        <Button
          loading={save.isPending}
          onClick={() =>
            save.mutate({
              tools: tools.filter((t) => AVAILABLE_TOOL_GROUPS.has(t)),
              goals,
              automation_mode: mode,
              price_disclosure: price,
            })
          }
        >
          {submitLabel}
        </Button>
      </div>
    </div>
  );
}

function RadioCards({
  legend,
  name,
  value,
  options,
  onChange,
}: {
  legend: string;
  name: string;
  value: string;
  options: Record<string, [string, string]>;
  onChange: (value: string) => void;
}) {
  return (
    <fieldset>
      <legend className="mb-2 text-sm font-medium">{legend}</legend>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {Object.entries(options).map(([key, [label, hint]]) => (
          <label
            key={key}
            className={cn(
              "flex cursor-pointer flex-col rounded-lg border p-3 text-sm has-focus-visible:outline-2 has-focus-visible:outline-ring",
              value === key
                ? "border-accent bg-accent-soft"
                : "border-border bg-surface hover:bg-surface-muted",
            )}
          >
            <input
              type="radio"
              name={name}
              value={key}
              checked={value === key}
              onChange={() => onChange(key)}
              className="sr-only"
            />
            <span className="font-medium">{label}</span>
            <span className="text-muted-foreground">{hint}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function LaunchStep({ account }: { account: Account }) {
  const router = useRouter();
  const launch = useAction(() => post<Account>("/account/launch"), {
    invalidate: [["account"], ["home"]],
    success: "pi is live. It will now reply to your customers.",
    onSuccess: () => router.push("/home"),
  });
  const missing = account.readiness.filter((i) => !i.done);
  return (
    <div className="space-y-6">
      <Card>
        <CardSection>
          <h2 className="text-xl font-semibold">
            Try pi before your customers do
          </h2>
          <p className="mt-1 text-[15px] text-muted-foreground">
            Send a message the way a customer would. Nothing is sent to WhatsApp
            and nothing is saved.
          </p>
          <div className="mt-5">
            <TestConversation includeDraftsToggle />
          </div>
        </CardSection>
      </Card>
      <Card>
        <CardSection>
          <h2 className="text-lg font-semibold">Ready to launch?</h2>
          <ul className="mt-4 space-y-2">
            {account.readiness.map((item) => (
              <li
                key={item.key}
                className="flex items-center gap-3 text-[15px]"
              >
                <span
                  className={cn(
                    "flex size-6 items-center justify-center rounded-full",
                    item.done
                      ? "bg-success-soft text-success"
                      : "bg-surface-sunken text-muted-foreground",
                  )}
                  aria-hidden
                >
                  {item.done ? (
                    <Check className="size-4" />
                  ) : (
                    <CircleHelp className="size-4" />
                  )}
                </span>
                <span className={item.done ? "" : "text-foreground-secondary"}>
                  {item.label}
                </span>
                <span className="sr-only">
                  {item.done ? "done" : "not done yet"}
                </span>
                {!item.done && item.key === "plan" ? (
                  <Link
                    href="/settings/billing"
                    className="ms-auto text-sm text-accent underline"
                  >
                    Choose a plan
                  </Link>
                ) : null}
              </li>
            ))}
          </ul>
          {account.setup_state === "active" ? (
            <Notice tone="success" title="pi is live">
              Manage it from your Home page.
            </Notice>
          ) : (
            <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center">
              <Button
                size="lg"
                disabled={missing.length > 0}
                loading={launch.isPending}
                onClick={() => launch.mutate(undefined)}
              >
                <Rocket className="size-5" aria-hidden /> Launch pi
              </Button>
              {missing.length > 0 ? (
                <p className="text-sm text-muted-foreground">
                  Finish {missing.length} more{" "}
                  {missing.length === 1 ? "item" : "items"} to launch.
                </p>
              ) : (
                <p className="text-sm text-muted-foreground">
                  You can pause pi anytime.
                </p>
              )}
            </div>
          )}
        </CardSection>
      </Card>
    </div>
  );
}

function HelpMeButton({ account }: { account: Account }) {
  const help = useAction(
    () => post("/account/help", { note: "Help me set up" }),
    {
      invalidate: [["account"]],
      success:
        "Our team will help. They can prepare settings, but only you can connect WhatsApp or pay.",
    },
  );
  if (account.help_requested_at) {
    return (
      <Badge tone="info">
        <LifeBuoy className="size-3.5" aria-hidden /> Our team is helping
      </Badge>
    );
  }
  return (
    <Button
      variant="secondary"
      size="sm"
      className="shrink-0 whitespace-nowrap"
      loading={help.isPending}
      onClick={() => help.mutate(undefined)}
    >
      <LifeBuoy className="size-4" aria-hidden /> Help me set up
    </Button>
  );
}

export function SetupWizard() {
  const account = useAccount();
  const params = useSearchParams();
  const router = useRouter();
  const requested = Number(params.get("step"));
  const step =
    requested >= 1 && requested <= 5
      ? requested
      : (account.data?.onboarding_step ?? 1);
  const go = (n: number) =>
    router.replace(`/setup?step=${n}`, { scroll: false });
  if (account.isPending) return <LoadingBlock rows={3} label="Loading setup" />;
  if (account.isError)
    return (
      <ErrorState
        message={errorText(account.error)}
        onRetry={() => account.refetch()}
      />
    );
  const data = account.data;
  return (
    <div className={cn("mx-auto min-w-0 max-w-3xl", product.setup)}>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1 basis-56">
          <h1 className="text-2xl font-semibold tracking-tight">Set up pi</h1>
          <p className="text-[15px] text-muted-foreground">
            Five short steps. Your progress is saved as you go.
          </p>
        </div>
        <HelpMeButton account={data} />
      </div>
      <Stepper
        step={step}
        done={data.completed_steps.concat(
          data.whatsapp.status === "connected" ? [3] : [],
        )}
        onGo={go}
      />
      {step === 1 ? <BusinessStep account={data} next={() => go(2)} /> : null}
      {step === 2 ? <OfferStep account={data} next={() => go(3)} /> : null}
      {step === 3 ? (
        <StepCard
          title="Connect WhatsApp"
          description="pi replies from your business WhatsApp number."
          footer={
            <Button variant="secondary" onClick={() => go(4)}>
              {data.whatsapp.status === "connected"
                ? "Continue"
                : "Do this later"}
            </Button>
          }
        >
          <WhatsAppConnect account={data} onDone={() => go(4)} />
        </StepCard>
      ) : null}
      {step === 4 ? (
        <Card className="animate-rise">
          <CardSection>
            <h2 className="text-xl font-semibold">How should pi help?</h2>
            <p className="mb-6 mt-1 text-[15px] text-muted-foreground">
              You can change all of this later.
            </p>
            <HelpForm account={data} next={() => go(5)} />
          </CardSection>
        </Card>
      ) : null}
      {step === 5 ? <LaunchStep account={data} /> : null}
    </div>
  );
}

export function NewBusinessPage() {
  const client = useQueryClient();
  const router = useRouter();
  const [name, setName] = React.useState("");
  const [offer, setOffer] = React.useState("services");
  const create = useAction(
    () => post<SessionView>("/businesses", { name, offer_type: offer }),
    {
      onSuccess: (session) => {
        client.removeQueries({ queryKey: ["biz"] });
        client.setQueryData(["session"], session);
        router.push("/setup");
      },
      success: "Business created",
    },
  );
  return (
    <div className="mx-auto max-w-lg">
      <Card>
        <CardSection className="space-y-5">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">
              Add a business
            </h1>
            <p className="text-[15px] text-muted-foreground">
              Each business has its own WhatsApp number, customers and settings.
              Nothing is shared between them.
            </p>
          </div>
          <Field label="Business name" htmlFor="nb-name">
            <Input
              id="nb-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={160}
            />
          </Field>
          <Field label="What do you offer?" htmlFor="nb-offer">
            <Select
              id="nb-offer"
              value={offer}
              onChange={(e) => setOffer(e.target.value)}
            >
              <option value="services">Services</option>
              <option value="products">Products</option>
              <option value="both">Both</option>
            </Select>
          </Field>
          <Button
            className="w-full"
            disabled={name.trim().length < 2}
            loading={create.isPending}
            onClick={() => create.mutate(undefined)}
          >
            Create business
          </Button>
        </CardSection>
      </Card>
    </div>
  );
}
