"use client";

import { useQuery } from "@tanstack/react-query";
import { Globe, ImageIcon, Mail, MapPin } from "lucide-react";
import * as React from "react";

import {
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
} from "@/components/ui";
import { errorText, get, put } from "@/lib/api";
import { useAction, useBusinessKey, useCan } from "@/lib/session";

interface Profile {
  about: string;
  description: string;
  address: string;
  email: string;
  vertical: string;
  websites: string[];
  photo_url: string;
}

interface ProfileView {
  connected: boolean;
  number: string | null;
  profile: Profile | null;
  verticals: string[];
  can_edit: boolean;
}

interface Form {
  about: string;
  description: string;
  address: string;
  email: string;
  vertical: string;
  site1: string;
  site2: string;
}

const LABELS: Record<string, string> = {
  HEALTH: "Health",
  PROF_SERVICES: "Professional services",
  EVENT_PLAN: "Event planning",
  EDU: "Education",
  ENTERTAIN: "Entertainment",
  AUTO: "Automotive",
  GOVT: "Government",
  NONPROFIT: "Non-profit",
  OTC_DRUGS: "Over-the-counter drugs",
  OTHER: "Other",
};

function verticalLabel(value: string) {
  return (
    LABELS[value] ??
    value
      .toLowerCase()
      .split("_")
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ")
  );
}

function toForm(p: Profile | null): Form {
  return {
    about: p?.about ?? "",
    description: p?.description ?? "",
    address: p?.address ?? "",
    email: p?.email ?? "",
    vertical: p?.vertical || "OTHER",
    site1: p?.websites?.[0] ?? "",
    site2: p?.websites?.[1] ?? "",
  };
}

function sites(f: Form) {
  return [f.site1.trim(), f.site2.trim()].filter(Boolean);
}

function Counter({ value, max }: { value: string; max: number }) {
  return (
    <span
      className={`text-[13px] tabular-nums ${value.length > max ? "text-danger" : "text-muted-foreground"}`}
    >
      {value.length}/{max}
    </span>
  );
}

function PhotoTile({ url, className }: { url: string; className?: string }) {
  const [brokenUrl, setBrokenUrl] = React.useState<string | null>(null);
  const broken = brokenUrl === url;
  return (
    <div
      className={`flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-surface-muted text-muted-foreground ${className ?? "size-20"}`}
    >
      {url && !broken ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={url}
          alt="Profile photo"
          className="size-full object-cover"
          onError={() => setBrokenUrl(url)}
        />
      ) : (
        <ImageIcon className="size-6" aria-hidden />
      )}
    </div>
  );
}

export function WhatsAppProfileCard() {
  const key = useBusinessKey();
  const can = useCan();
  const view = useQuery({
    queryKey: key(["whatsapp-profile"]),
    queryFn: () => get<ProfileView>("/pi/whatsapp/profile"),
  });
  const data = view.data;
  const [form, setForm] = React.useState<Form>(() => toForm(null));
  const [base, setBase] = React.useState<Form>(() => toForm(null));
  const [saved, setSaved] = React.useState(false);
  const loaded = React.useRef<ProfileView | undefined>(undefined);

  // Reset the form whenever fresh server data arrives.
  React.useEffect(() => {
    if (data && loaded.current !== data) {
      loaded.current = data;
      const next = toForm(data.profile);
      setForm(next);
      setBase(next);
    }
  }, [data]);

  const save = useAction(
    (f: Form) =>
      put<ProfileView>("/pi/whatsapp/profile", {
        about: f.about.trim(),
        description: f.description.trim(),
        address: f.address.trim(),
        email: f.email.trim(),
        vertical: f.vertical,
        websites: sites(f),
      }),
    {
      invalidate: [["whatsapp-profile"]],
      silentError: true,
      onSuccess: () => setSaved(true),
    },
  );

  const set = (patch: Partial<Form>) => {
    setSaved(false);
    save.reset();
    setForm((f) => ({ ...f, ...patch }));
  };

  const dirty = JSON.stringify(form) !== JSON.stringify(base);
  const editable = Boolean(data?.can_edit) && can("pi.whatsapp.manage");
  const valid = form.about.trim().length > 0 && form.about.length <= 139;

  let body: React.ReactNode;
  if (view.isError) {
    body = (
      <ErrorState
        message={errorText(view.error)}
        onRetry={() => view.refetch()}
      />
    );
  } else if (!data) {
    body = <LoadingBlock rows={3} />;
  } else if (!data.connected) {
    body = (
      <Notice tone="info">
        Connect a WhatsApp number to edit its profile.
      </Notice>
    );
  } else {
    const verticals = data.verticals.includes(form.vertical)
      ? data.verticals
      : [form.vertical, ...data.verticals];
    const photo = data.profile?.photo_url ?? "";
    body = (
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,320px)]">
        <form
          className="min-w-0 space-y-5"
          onSubmit={(e) => {
            e.preventDefault();
            if (dirty && editable && valid) save.mutate(form);
          }}
        >
          <Field
            label="Profile photo"
            htmlFor="wp-photo"
            hint="Photo changes aren't available here yet."
          >
            <div id="wp-photo">
              <PhotoTile url={photo} />
            </div>
          </Field>
          <Field
            label="About"
            htmlFor="wp-about"
            hint="A short line under your name, up to 139 characters."
          >
            <Input
              id="wp-about"
              value={form.about}
              maxLength={139}
              disabled={!editable}
              onChange={(e) => set({ about: e.target.value })}
            />
            <div className="text-end">
              <Counter value={form.about} max={139} />
            </div>
          </Field>
          <Field label="Email" htmlFor="wp-email" optional>
            <Input
              id="wp-email"
              type="email"
              maxLength={128}
              value={form.email}
              disabled={!editable}
              onChange={(e) => set({ email: e.target.value })}
            />
          </Field>
          <Field label="Address" htmlFor="wp-address" optional>
            <Input
              id="wp-address"
              maxLength={256}
              value={form.address}
              disabled={!editable}
              onChange={(e) => set({ address: e.target.value })}
            />
          </Field>
          <Field label="Category" htmlFor="wp-vertical">
            <Select
              id="wp-vertical"
              value={form.vertical}
              disabled={!editable}
              onChange={(e) => set({ vertical: e.target.value })}
            >
              {verticals.map((v) => (
                <option key={v} value={v}>
                  {verticalLabel(v)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Description" htmlFor="wp-description" optional>
            <Textarea
              id="wp-description"
              rows={4}
              maxLength={512}
              value={form.description}
              disabled={!editable}
              onChange={(e) => set({ description: e.target.value })}
            />
            <div className="text-end">
              <Counter value={form.description} max={512} />
            </div>
          </Field>
          <Field
            label="Websites"
            htmlFor="wp-site1"
            hint="Up to two, starting with http:// or https://."
          >
            <div className="space-y-2">
              <Input
                id="wp-site1"
                type="url"
                inputMode="url"
                maxLength={256}
                placeholder="https://"
                value={form.site1}
                disabled={!editable}
                onChange={(e) => set({ site1: e.target.value })}
              />
              <Input
                id="wp-site2"
                type="url"
                inputMode="url"
                maxLength={256}
                placeholder="https://"
                aria-label="Second website"
                value={form.site2}
                disabled={!editable}
                onChange={(e) => set({ site2: e.target.value })}
              />
            </div>
          </Field>
          {save.isError ? (
            <p className="text-sm text-danger" role="alert">
              {errorText(save.error)}
            </p>
          ) : null}
          {saved ? (
            <Notice tone="success">
              Profile saved. WhatsApp may take a few minutes to show it.
            </Notice>
          ) : null}
          {!editable ? (
            <p className="text-sm text-muted-foreground">
              Only people who manage WhatsApp can change this profile.
            </p>
          ) : null}
          <div className="flex flex-wrap gap-2">
            <Button
              type="submit"
              loading={save.isPending}
              disabled={!dirty || !editable || !valid}
            >
              Save profile
            </Button>
            {dirty ? (
              <Button
                type="button"
                variant="ghost"
                disabled={save.isPending}
                onClick={() => {
                  setForm(base);
                  setSaved(false);
                  save.reset();
                }}
              >
                Discard
              </Button>
            ) : null}
          </div>
        </form>
        <Preview form={form} number={data.number} photo={photo} />
      </div>
    );
  }

  return (
    <Card>
      <CardSection className="space-y-5">
        <div>
          <h2 className="font-semibold">WhatsApp profile</h2>
          <p className="text-sm text-muted-foreground">
            What customers see when they open your business profile in WhatsApp.
          </p>
        </div>
        {body}
      </CardSection>
    </Card>
  );
}

function Preview({
  form,
  number,
  photo,
}: {
  form: Form;
  number: string | null;
  photo: string;
}) {
  const links = sites(form);
  return (
    <aside
      aria-label="Preview"
      className="min-w-0 lg:sticky lg:top-4 lg:self-start"
    >
      <p className="mb-2 text-sm font-medium text-muted-foreground">Preview</p>
      <div className="overflow-hidden rounded-2xl border border-border bg-surface-muted">
        <div className="flex flex-col items-center gap-2 bg-surface px-4 py-6 text-center">
          <PhotoTile url={photo} className="size-24" />
          <p className="max-w-full break-words text-lg font-semibold tabular-nums">
            {number ?? "Your number"}
          </p>
          <p className="max-w-full break-words text-sm text-muted-foreground">
            {form.about || "Your About line"}
          </p>
        </div>
        <div className="space-y-3 p-4 text-sm">
          <p className="text-muted-foreground">
            {verticalLabel(form.vertical)}
          </p>
          {form.description ? (
            <p className="whitespace-pre-wrap break-words">
              {form.description}
            </p>
          ) : null}
          {form.address ? (
            <p className="flex items-start gap-2 break-words">
              <MapPin
                className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                aria-hidden
              />
              <span className="min-w-0">{form.address}</span>
            </p>
          ) : null}
          {form.email ? (
            <p className="flex items-start gap-2">
              <Mail
                className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                aria-hidden
              />
              <span className="min-w-0 break-all">{form.email}</span>
            </p>
          ) : null}
          {links.map((url) => (
            <p key={url} className="flex items-start gap-2">
              <Globe
                className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                aria-hidden
              />
              <a
                href={/^https?:\/\//i.test(url) ? url : undefined}
                target="_blank"
                rel="noreferrer noopener"
                className="min-w-0 break-all text-accent underline"
              >
                {url}
              </a>
            </p>
          ))}
        </div>
      </div>
    </aside>
  );
}
