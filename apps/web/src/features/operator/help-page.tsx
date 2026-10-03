"use client";

import * as React from "react";
import { BookOpen, EyeOff, Plus, RotateCcw } from "lucide-react";
import { EmptyState, ErrorState } from "@/components/app/states";
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

type Guide = {
  id: string;
  title: string;
  body: string;
  tags: string[];
  page: string | null;
  builtin: boolean;
  hidden: boolean;
  updated_by: string | null;
  updated_at: string | null;
};
type Listing = { pages: string[]; items: Guide[] };
type GuideInput = {
  title: string;
  body: string;
  tags: string[];
  page: string | null;
};

const base = "/operator/pi/help";
const helpApi = {
  list: () => apiRequest<Listing>("GET", base, null),
  create: (body: GuideInput) => apiRequest<Guide>("POST", base, null, { body }),
  update: (id: string, body: GuideInput) =>
    apiRequest<Guide>("PUT", `${base}/${id}`, null, { body }),
  hide: (id: string, hidden: boolean) =>
    apiRequest("POST", `${base}/${id}/${hidden ? "hide" : "show"}`, null, {
      body: {},
    }),
  reset: (id: string) => apiRequest("DELETE", `${base}/${id}`, null),
};
const invalidate = [["operator", "help"]];

export function OperatorHelpPage() {
  return (
    <OperatorShell
      title="Pi help guides"
      description="Setup guides the Pi Assistant answers from inside every business's Pi app. Edit the built-in ones, add your own, or hide what doesn't apply."
    >
      {(me) => <Guides me={me} />}
    </OperatorShell>
  );
}

function Guides({ me }: { me: OperatorMe }) {
  const allowed =
    me.capabilities.includes("operator.onboarding.assist") ||
    me.capabilities.includes("operator.settings.manage");
  const listing = useScopedQuery(["operator", "help"], helpApi.list, {
    enabled: allowed,
  });
  const [editing, setEditing] = React.useState<Guide | "new" | null>(null);
  if (!allowed)
    return (
      <EmptyState
        icon={BookOpen}
        title="Onboarding team only"
        description="Operators who help businesses set up can manage these guides."
      />
    );
  if (listing.isPending) return <Skeleton className="h-64 w-full" />;
  if (listing.isError)
    return (
      <ErrorState error={listing.error} onRetry={() => listing.refetch()} />
    );
  const { items, pages } = listing.data;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-[13px] text-muted-foreground">
          {items.filter((g) => !g.hidden).length} guides live ·{" "}
          {items.filter((g) => g.hidden).length} hidden. Changes reach every
          business right away.
        </p>
        <Button size="sm" onClick={() => setEditing("new")}>
          <Plus className="mr-1 size-4" aria-hidden />
          New guide
        </Button>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {items.map((guide) => (
          <GuideCard
            key={guide.id}
            guide={guide}
            onEdit={() => setEditing(guide)}
          />
        ))}
      </div>
      {editing ? (
        <GuideDialog
          guide={editing === "new" ? null : editing}
          pages={pages}
          onClose={() => setEditing(null)}
        />
      ) : null}
    </div>
  );
}

function GuideCard({ guide, onEdit }: { guide: Guide; onEdit: () => void }) {
  const hide = useScopedMutation(() => helpApi.hide(guide.id, !guide.hidden), {
    invalidate,
    success: guide.hidden
      ? "Guide is live again"
      : "Guide hidden from businesses",
  });
  const edited = guide.builtin && guide.updated_at;
  const reset = useScopedMutation(() => helpApi.reset(guide.id), {
    invalidate,
    success: guide.builtin ? "Back to the original text" : "Guide deleted",
  });
  return (
    <Card className={`p-4 ${guide.hidden ? "opacity-60" : ""}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold">{guide.title}</h3>
          <div className="mt-1 flex flex-wrap gap-1.5">
            <Badge tone={guide.builtin ? "neutral" : "primary"}>
              {guide.builtin
                ? edited
                  ? "Built-in · edited"
                  : "Built-in"
                : "Yours"}
            </Badge>
            {guide.hidden ? <Badge tone="warning">Hidden</Badge> : null}
            {guide.page ? <Badge tone="outline">{guide.page}</Badge> : null}
          </div>
        </div>
        <Button variant="secondary" size="sm" onClick={onEdit}>
          Edit
        </Button>
      </div>
      <p className="mt-3 line-clamp-3 text-[13px] text-muted-foreground">
        {guide.body}
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
        <Button
          variant="ghost"
          size="sm"
          disabled={hide.isPending}
          onClick={() => hide.mutate(undefined)}
        >
          <EyeOff className="mr-1 size-3.5" aria-hidden />
          {guide.hidden ? "Show" : "Hide"}
        </Button>
        {edited || !guide.builtin ? (
          <Button
            variant="ghost"
            size="sm"
            disabled={reset.isPending}
            onClick={() => {
              if (
                guide.builtin ||
                window.confirm(`Delete "${guide.title}" for every business?`)
              )
                reset.mutate(undefined);
            }}
          >
            <RotateCcw className="mr-1 size-3.5" aria-hidden />
            {guide.builtin ? "Restore original" : "Delete"}
          </Button>
        ) : null}
        {guide.updated_by ? (
          <span className="ml-auto text-muted-foreground">
            Edited by {guide.updated_by}
          </span>
        ) : null}
      </div>
    </Card>
  );
}

function GuideDialog({
  guide,
  pages,
  onClose,
}: {
  guide: Guide | null;
  pages: string[];
  onClose: () => void;
}) {
  const [title, setTitle] = React.useState(guide?.title ?? "");
  const [body, setBody] = React.useState(guide?.body ?? "");
  const [tags, setTags] = React.useState((guide?.tags ?? []).join(", "));
  const [page, setPage] = React.useState(guide?.page ?? "");
  const input = (): GuideInput => ({
    title: title.trim(),
    body: body.trim(),
    tags: tags
      .split(",")
      .map((t) => t.trim().toLowerCase())
      .filter(Boolean)
      .slice(0, 12),
    page: page || null,
  });
  const save = useScopedMutation(
    () => (guide ? helpApi.update(guide.id, input()) : helpApi.create(input())),
    {
      invalidate,
      success: guide ? "Guide updated" : "Guide added",
      onSuccess: onClose,
    },
  );
  const valid = title.trim().length >= 3 && body.trim().length >= 10;
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader
          title={guide ? "Edit guide" : "New guide"}
          description="Write it as you'd explain it to a business owner: short steps and the page to open."
        />
        <DialogBody className="space-y-3">
          <label className="block text-[13px] font-medium">
            Title
            <Input
              className="mt-1"
              value={title}
              maxLength={120}
              onChange={(e) => setTitle(e.target.value)}
            />
          </label>
          <label className="block text-[13px] font-medium">
            Guide text
            <Textarea
              className="mt-1 min-h-40"
              value={body}
              maxLength={6000}
              onChange={(e) => setBody(e.target.value)}
            />
          </label>
          <label className="block text-[13px] font-medium">
            Search words (comma separated)
            <Input
              className="mt-1"
              value={tags}
              placeholder="whatsapp, connect, number"
              onChange={(e) => setTags(e.target.value)}
            />
          </label>
          <label className="block text-[13px] font-medium">
            Pi app page to open
            <NativeSelect
              className="mt-1"
              value={page}
              onChange={(e) => setPage(e.target.value)}
            >
              <option value="">None</option>
              {pages.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </NativeSelect>
          </label>
        </DialogBody>
        <DialogFooter>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={!valid || save.isPending}
            onClick={() => save.mutate(undefined)}
          >
            {save.isPending ? "Saving…" : "Save guide"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
