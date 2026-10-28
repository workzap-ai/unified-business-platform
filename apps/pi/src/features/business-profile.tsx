"use client";

/**
 * The Business Profile (platform spec v1.4, 16.3): what pi understood about each business, where
 * each fact came from (the owner, a page or a photo) and whether it is confirmed. A page or photo
 * fact is provisional until it is confirmed, and only confirmed facts ground pi's ideas. A fact can
 * be corrected, confirmed or deleted here. GET /pi/business-profiles, PATCH, POST .../confirm and
 * DELETE /pi/business-profiles/{id}/facts/{fact_id}.
 */

import { useQuery } from "@tanstack/react-query";
import { Check, Pencil, Trash2 } from "lucide-react";
import * as React from "react";

import { SubNav } from "@/components/shell";
import {
  Badge,
  Button,
  Card,
  CardSection,
  Dialog,
  DialogClose,
  DialogContent,
  DialogTrigger,
  EmptyState,
  ErrorState,
  Input,
  LoadingBlock,
  Notice,
  PageHeader,
} from "@/components/ui";
import { SECTIONS } from "@/features/brain";
import { del, errorText, get, patch, post } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { useAction, useBusinessKey, useCan } from "@/lib/session";

export type ProfileFact = {
  id: string;
  key: string;
  value: string;
  source: "owner" | "page" | "photo";
  confirmed: boolean;
  confirmed_at: string | null;
  evidence: string;
  url: string;
  fetched_at: string | null;
};

export type Profile = {
  id: string;
  customer_id: string;
  customer_name: string;
  display_name: string;
  what_they_do: string;
  updated_at: string;
  facts: ProfileFact[];
  snapshots: { url: string; fetched_at: string; status: string }[];
};

export const FACT_LABELS: Record<string, string> = {
  business_name: "Business name",
  what_they_do: "What it does or sells",
  industry: "Industry",
  places: "Places and outlets",
  since: "Since when",
  size: "Size",
  channels: "Channels",
  website_url: "Website",
  social_urls: "Social pages",
  website: "Website status",
  online_orders: "Takes orders online",
  language: "Language",
};

export const SOURCE_LABELS: Record<ProfileFact["source"], string> = {
  owner: "Told by the owner",
  page: "From their page",
  photo: "From a photo",
};

/** "none" for the website is a fact, not a problem (spec 16.5). */
export function factValue(fact: Pick<ProfileFact, "key" | "value">): string {
  if (fact.key === "website" && fact.value === "none") return "No website";
  return fact.value;
}

const LIST = ["pi", "business-profiles"];

export function BusinessProfilePage() {
  const can = useCan();
  return (
    <div className="min-w-0">
      <PageHeader
        title="Business profile"
        description="What pi understood about each business it talks to, and where each fact came from. Facts from a page or photo stay provisional until they are confirmed, and pi only builds ideas on confirmed facts."
      />
      <SubNav items={SECTIONS} />
      <div className="mt-6 min-w-0">
        {can("pi.memory.read") ? (
          <Profiles />
        ) : (
          <Notice tone="warning" title="You can't see business profiles">
            Ask your business owner to give you access.
          </Notice>
        )}
      </div>
    </div>
  );
}

function Profiles() {
  const key = useBusinessKey();
  const query = useQuery({
    queryKey: key(LIST),
    queryFn: () => get<{ items: Profile[] }>("/pi/business-profiles"),
  });
  if (query.isPending)
    return <LoadingBlock rows={3} label="Loading business profiles" />;
  if (query.isError)
    return (
      <ErrorState
        message={errorText(query.error)}
        onRetry={() => query.refetch()}
      />
    );
  if (query.data.items.length === 0)
    return (
      <Card>
        <EmptyState title="No business profiles yet">
          When an owner says hello and tells pi about their business, what pi
          understood appears here.
        </EmptyState>
      </Card>
    );
  return (
    <div className="grid min-w-0 gap-5" data-testid="business-profiles">
      {query.data.items.map((profile) => (
        <ProfileCard key={profile.id} profile={profile} />
      ))}
    </div>
  );
}

function ProfileCard({ profile }: { profile: Profile }) {
  const can = useCan();
  const heading = profile.display_name || profile.customer_name;
  return (
    <Card data-testid="business-profile">
      <CardSection>
        <div className="flex min-w-0 flex-wrap items-baseline justify-between gap-2">
          <h2 className="min-w-0 break-words text-lg font-semibold tracking-[-0.02em]">
            {heading}
          </h2>
          <span className="text-xs text-muted-foreground">
            Updated {dateTime(profile.updated_at)}
          </span>
        </div>
        {profile.facts.length === 0 ? (
          <p className="mt-3 text-sm text-muted-foreground">
            Nothing is kept for this business.
          </p>
        ) : (
          <ul className="mt-4 divide-y divide-border">
            {profile.facts.map((fact) => (
              <FactRow
                key={fact.id}
                profileId={profile.id}
                fact={fact}
                canChange={can("pi.settings.manage")}
              />
            ))}
          </ul>
        )}
        {profile.snapshots.length > 0 ? (
          <p className="mt-4 text-xs text-muted-foreground">
            Last page look: {profile.snapshots[0].url},{" "}
            {dateTime(profile.snapshots[0].fetched_at)}
          </p>
        ) : null}
      </CardSection>
    </Card>
  );
}

function FactRow({
  profileId,
  fact,
  canChange,
}: {
  profileId: string;
  fact: ProfileFact;
  canChange: boolean;
}) {
  const [editing, setEditing] = React.useState(false);
  const [value, setValue] = React.useState(fact.value);
  const path = `/pi/business-profiles/${profileId}/facts/${fact.id}`;
  const confirm = useAction(() => post(`${path}/confirm`), {
    success: "Confirmed",
    invalidate: [LIST],
  });
  const save = useAction((next: string) => patch(path, { value: next }), {
    success: "Saved",
    invalidate: [LIST],
    onSuccess: () => setEditing(false),
  });
  const remove = useAction(() => del(path), {
    success: "Deleted",
    invalidate: [LIST],
  });
  const label = FACT_LABELS[fact.key] ?? fact.key;
  return (
    <li className="py-3" data-testid={`fact-${fact.key}`}>
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div className="min-w-0 flex-1">
          <p className="text-xs font-medium text-muted-foreground">{label}</p>
          {editing ? (
            <form
              className="mt-1 flex flex-wrap gap-2"
              onSubmit={(event) => {
                event.preventDefault();
                if (value.trim()) save.mutate(value.trim());
              }}
            >
              <Input
                aria-label={`Edit ${label}`}
                value={value}
                maxLength={300}
                onChange={(event) => setValue(event.target.value)}
                className="h-10 min-w-0 flex-1"
              />
              <Button type="submit" size="sm" loading={save.isPending}>
                Save
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => {
                  setEditing(false);
                  setValue(fact.value);
                }}
              >
                Cancel
              </Button>
            </form>
          ) : (
            <p className="mt-0.5 break-words text-[15px]">{factValue(fact)}</p>
          )}
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            <Badge tone={fact.source === "owner" ? "accent" : "neutral"}>
              {SOURCE_LABELS[fact.source]}
            </Badge>
            {fact.confirmed ? (
              <Badge tone="success">Confirmed</Badge>
            ) : (
              <Badge tone="warning">Not confirmed yet</Badge>
            )}
            {fact.evidence ? (
              <span className="text-xs text-muted-foreground">
                {fact.evidence}
              </span>
            ) : null}
          </div>
        </div>
        {canChange && !editing ? (
          <div className="flex shrink-0 flex-wrap gap-1">
            {!fact.confirmed ? (
              <Button
                size="sm"
                variant="secondary"
                loading={confirm.isPending}
                onClick={() => confirm.mutate(undefined)}
              >
                <Check className="size-4" aria-hidden />
                Confirm
              </Button>
            ) : null}
            <Button
              size="sm"
              variant="ghost"
              aria-label={`Edit ${label}`}
              onClick={() => setEditing(true)}
            >
              <Pencil className="size-4" aria-hidden />
              Edit
            </Button>
            <Dialog>
              <DeleteButton label={label} />
              <DialogContent title={`Delete ${label.toLowerCase()}?`}>
                <p className="text-sm text-foreground-secondary">
                  pi will forget this fact about the business. This cannot be
                  undone.
                </p>
                <div className="mt-5 flex justify-end gap-2">
                  <DialogClose asChild>
                    <Button variant="ghost">Keep it</Button>
                  </DialogClose>
                  <DialogClose asChild>
                    <Button
                      variant="danger"
                      onClick={() => remove.mutate(undefined)}
                    >
                      Delete
                    </Button>
                  </DialogClose>
                </div>
              </DialogContent>
            </Dialog>
          </div>
        ) : null}
      </div>
    </li>
  );
}

function DeleteButton({ label }: { label: string }) {
  return (
    <DialogTrigger asChild>
      <Button size="sm" variant="ghost" aria-label={`Delete ${label}`}>
        <Trash2 className="size-4" aria-hidden />
        Delete
      </Button>
    </DialogTrigger>
  );
}
