"use client";

import { useMemo, useState } from "react";
import { Building2, Globe, Mail, MapPin } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, Skeleton } from "@/components/ui/display";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { FormField } from "@/components/app/forms";
import { EmptyState, ErrorState, InlineError } from "@/components/app/states";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { ApiError, errorMessage } from "@/services/api-client";
import { cn } from "@/lib/utils";
import {
  whatsappProfileService,
  type WhatsAppProfile,
  type WhatsAppProfileInput,
} from "../whatsapp-profile-service";

const KEY = ["pi", "whatsapp", "profile"] as const;
const ABOUT_MAX = 139;
const DESCRIPTION_MAX = 512;

const VERTICAL_LABELS: Record<string, string> = {
  OTHER: "Other",
  AUTO: "Automotive",
  BEAUTY: "Beauty, spa and salon",
  APPAREL: "Clothing and apparel",
  EDU: "Education",
  ENTERTAIN: "Entertainment",
  EVENT_PLAN: "Event planning",
  FINANCE: "Finance and banking",
  GROCERY: "Grocery and retail",
  GOVT: "Government",
  HOTEL: "Hotel and lodging",
  HEALTH: "Health",
  NONPROFIT: "Non-profit",
  PROF_SERVICES: "Professional services",
  RETAIL: "Shopping and retail",
  TRAVEL: "Travel and transportation",
  RESTAURANT: "Restaurant",
  ALCOHOL: "Alcoholic beverages",
  ONLINE_GAMBLING: "Online gambling",
  PHYSICAL_GAMBLING: "Physical gambling",
  OTC_DRUGS: "Over-the-counter drugs",
};

function verticalLabel(v: string) {
  if (VERTICAL_LABELS[v]) return VERTICAL_LABELS[v];
  const s = v.replace(/_/g, " ").toLowerCase();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

type Draft = {
  about: string;
  email: string;
  address: string;
  vertical: string;
  description: string;
  website1: string;
  website2: string;
};

function toDraft(p: WhatsAppProfile | null): Draft {
  return {
    about: p?.about ?? "",
    email: p?.email ?? "",
    address: p?.address ?? "",
    vertical: p?.vertical || "OTHER",
    description: p?.description ?? "",
    website1: p?.websites[0] ?? "",
    website2: p?.websites[1] ?? "",
  };
}

function toInput(d: Draft): WhatsAppProfileInput {
  return {
    about: d.about.trim(),
    email: d.email.trim(),
    address: d.address.trim(),
    vertical: d.vertical,
    description: d.description.trim(),
    websites: [d.website1.trim(), d.website2.trim()].filter(Boolean),
  };
}

function saveError(e: unknown) {
  if (e instanceof ApiError && e.serverMessage) return e.serverMessage;
  return errorMessage(e, "The profile couldn't be saved. Please try again.");
}

export function WhatsAppProfileCard() {
  const query = useScopedQuery(KEY, whatsappProfileService.get);
  const data = query.data;

  return (
    <Card className="mb-4">
      <CardHeader
        title="WhatsApp profile"
        description="What customers see when they open your business profile in WhatsApp."
      />
      <CardBody>
        {query.isError ? (
          <ErrorState
            error={query.error}
            onRetry={() => void query.refetch()}
          />
        ) : !data ? (
          <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
            <Skeleton className="h-96 rounded-xl" />
            <Skeleton className="h-96 rounded-xl" />
          </div>
        ) : !data.connected ? (
          <EmptyState
            tone="pi"
            icon={Building2}
            title="Connect a WhatsApp number to edit its profile."
            description="Once a number is connected, you can set the about text, category and contact details customers see."
          />
        ) : (
          <ProfileEditor
            number={data.number}
            profile={data.profile}
            verticals={data.verticals}
            canEdit={data.can_edit}
          />
        )}
      </CardBody>
    </Card>
  );
}

function ProfileEditor({
  number,
  profile,
  verticals,
  canEdit,
}: {
  number: string | null;
  profile: WhatsAppProfile | null;
  verticals: string[];
  canEdit: boolean;
}) {
  const saved = useMemo(() => toDraft(profile), [profile]);
  const [draft, setDraft] = useState<Draft>(saved);
  const [error, setError] = useState<string | null>(null);

  // Take the server's copy whenever it changes (after a save or refetch).
  const [seen, setSeen] = useState(saved);
  if (seen !== saved) {
    setSeen(saved);
    setDraft(saved);
  }

  const set = <K extends keyof Draft>(k: K, v: Draft[K]) =>
    setDraft((d) => ({ ...d, [k]: v }));
  const dirty = (Object.keys(saved) as (keyof Draft)[]).some(
    (k) => saved[k] !== draft[k],
  );
  const valid = draft.about.trim().length > 0;

  const save = useScopedMutation(whatsappProfileService.save, {
    invalidate: [[...KEY]],
    success: "Profile saved. WhatsApp may take a few minutes to show it.",
    toastErrors: false,
    onSuccess: () => setError(null),
  });

  const options = verticals.includes(draft.vertical)
    ? verticals
    : [...verticals, draft.vertical];
  const disabled = !canEdit || save.isPending;

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    save.mutate(toInput(draft), { onError: (err) => setError(saveError(err)) });
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <form onSubmit={submit} noValidate className="min-w-0 space-y-4">
        {!canEdit && (
          <p className="text-[13px] text-muted-foreground">
            You can view this profile but not change it.
          </p>
        )}
        <div className="flex items-center gap-3">
          <PhotoTile url={profile?.photo_url} name={number} size="size-16" />
          <div>
            <p className="text-[13px] font-medium">Profile photo</p>
            <p className="text-xs text-muted-foreground">
              Photo changes aren&apos;t available here yet.
            </p>
          </div>
        </div>
        <FormField
          label="About"
          htmlFor="wap-about"
          required
          help={
            <span className="tabular-nums">
              {draft.about.length}/{ABOUT_MAX}
            </span>
          }
        >
          <Input
            id="wap-about"
            value={draft.about}
            maxLength={ABOUT_MAX}
            disabled={disabled}
            onChange={(e) => set("about", e.target.value)}
          />
        </FormField>
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField label="Email" htmlFor="wap-email" optional>
            <Input
              id="wap-email"
              type="email"
              inputMode="email"
              maxLength={128}
              disabled={disabled}
              value={draft.email}
              onChange={(e) => set("email", e.target.value)}
            />
          </FormField>
          <FormField label="Category" htmlFor="wap-vertical">
            <NativeSelect
              id="wap-vertical"
              value={draft.vertical}
              disabled={disabled}
              onChange={(e) => set("vertical", e.target.value)}
            >
              {options.map((v) => (
                <option key={v} value={v}>
                  {verticalLabel(v)}
                </option>
              ))}
            </NativeSelect>
          </FormField>
        </div>
        <FormField label="Address" htmlFor="wap-address" optional>
          <Input
            id="wap-address"
            maxLength={256}
            disabled={disabled}
            value={draft.address}
            onChange={(e) => set("address", e.target.value)}
          />
        </FormField>
        <FormField
          label="Description"
          htmlFor="wap-description"
          optional
          help={
            <span className="tabular-nums">
              {draft.description.length}/{DESCRIPTION_MAX}
            </span>
          }
        >
          <Textarea
            id="wap-description"
            rows={4}
            maxLength={DESCRIPTION_MAX}
            disabled={disabled}
            value={draft.description}
            onChange={(e) => set("description", e.target.value)}
          />
        </FormField>
        <FormField label="Websites" htmlFor="wap-site1" optional>
          <div className="space-y-2">
            <Input
              id="wap-site1"
              type="url"
              inputMode="url"
              placeholder="https://"
              maxLength={256}
              disabled={disabled}
              value={draft.website1}
              onChange={(e) => set("website1", e.target.value)}
            />
            <Input
              id="wap-site2"
              type="url"
              inputMode="url"
              placeholder="https://"
              aria-label="Second website"
              maxLength={256}
              disabled={disabled}
              value={draft.website2}
              onChange={(e) => set("website2", e.target.value)}
            />
          </div>
        </FormField>
        {error && <InlineError message={error} />}
        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="submit"
            loading={save.isPending}
            disabled={!canEdit || !dirty || !valid}
          >
            Save profile
          </Button>
          {dirty && !save.isPending && (
            <button
              type="button"
              className="text-[13px] text-muted-foreground underline underline-offset-2 hover:text-foreground"
              onClick={() => {
                setDraft(saved);
                setError(null);
              }}
            >
              Discard
            </button>
          )}
        </div>
      </form>
      <Preview draft={draft} number={number} photo={profile?.photo_url} />
    </div>
  );
}

function PhotoTile({
  url,
  name,
  size,
}: {
  url?: string | null;
  name: string | null;
  size: string;
}) {
  const [brokenUrl, setBrokenUrl] = useState<string | null>(null);
  if (url && url !== brokenUrl) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={url}
        alt="Profile photo"
        className={cn(
          size,
          "shrink-0 rounded-full border border-border object-cover",
        )}
        onError={() => setBrokenUrl(url)}
      />
    );
  }
  const initials = (name ?? "").replace(/\D/g, "").slice(-2);
  return (
    <div
      aria-hidden="true"
      className={cn(
        size,
        "flex shrink-0 items-center justify-center rounded-full border border-border bg-surface-muted text-muted-foreground",
      )}
    >
      {initials ? (
        <span className="text-sm font-medium">{initials}</span>
      ) : (
        <Building2 className="size-1/2" />
      )}
    </div>
  );
}

function Preview({
  draft,
  number,
  photo,
}: {
  draft: Draft;
  number: string | null;
  photo?: string | null;
}) {
  const sites = [draft.website1, draft.website2]
    .map((s) => s.trim())
    .filter(Boolean);
  const isHttp = (s: string) => /^https?:\/\//i.test(s);
  const address = draft.address.trim();
  const email = draft.email.trim();
  return (
    <div className="min-w-0">
      <p className="mb-2 text-xs font-medium text-muted-foreground">Preview</p>
      <div className="overflow-hidden rounded-xl border border-border bg-surface-muted">
        <div className="flex flex-col items-center gap-2 border-b border-border bg-surface px-4 py-5 text-center">
          <PhotoTile url={photo} name={number} size="size-20" />
          <p className="max-w-full break-words text-base font-semibold tabular-nums">
            {number ?? "Your business"}
          </p>
          <p className="text-xs text-muted-foreground">
            {verticalLabel(draft.vertical)}
          </p>
        </div>
        <div className="space-y-3 px-4 py-4 text-[13px]">
          <section>
            <p className="text-xs text-muted-foreground">About</p>
            <p className="break-words">
              {draft.about.trim() || (
                <span className="text-muted-foreground">Your About text</span>
              )}
            </p>
          </section>
          {draft.description.trim() && (
            <section>
              <p className="text-xs text-muted-foreground">Description</p>
              <p className="whitespace-pre-line break-words">
                {draft.description.trim()}
              </p>
            </section>
          )}
          {(address || email || sites.length > 0) && (
            <ul className="space-y-2 border-t border-border pt-3">
              {address && (
                <li className="flex items-start gap-2">
                  <MapPin
                    className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                    aria-hidden="true"
                  />
                  <span className="min-w-0 break-words">{address}</span>
                </li>
              )}
              {email && (
                <li className="flex items-start gap-2">
                  <Mail
                    className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                    aria-hidden="true"
                  />
                  <span className="min-w-0 break-all text-primary">
                    {email}
                  </span>
                </li>
              )}
              {sites.map((s) => (
                <li key={s} className="flex items-start gap-2">
                  <Globe
                    className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                    aria-hidden="true"
                  />
                  {isHttp(s) ? (
                    <a
                      href={s}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="min-w-0 break-all text-primary underline-offset-2 hover:underline"
                    >
                      {s}
                    </a>
                  ) : (
                    <span className="min-w-0 break-all">{s}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
