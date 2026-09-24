"use client";

import { useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Layers, Plus } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatNumber, relativeTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Badge, Card } from "@/components/ui/display";
import { Switch } from "@/components/ui/controls";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/overlays";
import {
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import { ConfirmDialog, FormField } from "@/components/app/forms";
import { EmptyState, ErrorState } from "@/components/app/states";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { piService } from "../../service";
import type { KnowledgeSource } from "../../types";
import { CardsSkeleton, SOURCE_KIND_LABELS, Stat, piKeys } from "../shared";
import { KNOWLEDGE_HEADER, KnowledgeNav } from "./knowledge-shared";

export function KnowledgeSourcesPage() {
  return (
    <RequirePermission permission="pi.knowledge.manage" area="PI knowledge">
      <Sources />
    </RequirePermission>
  );
}

function Sources() {
  const params = useSearchParams();
  const [open, setOpen] = useState(params.get("new") === "1");
  const [disableTarget, setDisableTarget] = useState<KnowledgeSource | null>(
    null,
  );
  const sources = useScopedQuery(piKeys.sources, () => piService.sources());
  const setStatus = useScopedMutation(
    (input: { id: string; status: KnowledgeSource["status"] }) =>
      piService.setSourceStatus(input.id, input.status),
    {
      invalidate: [[...piKeys.sources], [...piKeys.overview]],
      success: (s) =>
        s.status === "active" ? `${s.name} enabled` : `${s.name} disabled`,
      onSuccess: () => setDisableTarget(null),
    },
  );

  return (
    <PageShell>
      <PageHeader
        {...KNOWLEDGE_HEADER}
        actions={
          <Button onClick={() => setOpen(true)}>
            <Plus /> New source
          </Button>
        }
      />
      <KnowledgeNav />
      {sources.isError ? (
        <Card>
          <ErrorState
            error={sources.error}
            onRetry={() => void sources.refetch()}
          />
        </Card>
      ) : !sources.data ? (
        <CardsSkeleton />
      ) : sources.data.length === 0 ? (
        <Card>
          <EmptyState
            tone="pi"
            icon={Layers}
            title="No knowledge sources"
            description="Sources group related documents — e.g. FAQ, return policy or company information — so you can switch them on or off together."
            action={
              <Button size="sm" onClick={() => setOpen(true)}>
                <Plus /> New source
              </Button>
            }
          />
        </Card>
      ) : (
        <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {sources.data.map((s) => {
            const id = `source-${s.id}`;
            const active = s.status === "active";
            return (
              <li key={s.id}>
                <Card
                  className={cn(
                    "flex h-full flex-col p-4",
                    !active && "bg-surface-muted/50",
                  )}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h2 className="truncate text-[14px] font-semibold">
                        {s.name}
                      </h2>
                      <Badge tone="outline" className="mt-1">
                        {SOURCE_KIND_LABELS[s.kind]}
                      </Badge>
                    </div>
                    <div className="flex items-center gap-2">
                      <span
                        className="text-xs text-muted-foreground"
                        aria-hidden="true"
                      >
                        {active ? "Active" : "Disabled"}
                      </span>
                      <Switch
                        id={id}
                        aria-label={
                          active ? `Disable ${s.name}` : `Enable ${s.name}`
                        }
                        checked={active}
                        disabled={
                          setStatus.isPending &&
                          setStatus.variables?.id === s.id
                        }
                        onCheckedChange={(checked) =>
                          checked
                            ? setStatus.mutate({ id: s.id, status: "active" })
                            : setDisableTarget(s)
                        }
                      />
                    </div>
                  </div>
                  <p className="mt-2 line-clamp-3 text-[13px] text-muted-foreground">
                    {s.description || "No description"}
                  </p>
                  <dl className="mt-auto grid grid-cols-3 gap-3 pt-4">
                    <Stat label="Documents" value={formatNumber(s.documents)} />
                    <Stat label="Ready" value={formatNumber(s.ready)} />
                    <Stat
                      label="Failed"
                      value={formatNumber(s.failed)}
                      tone={s.failed ? "danger" : undefined}
                    />
                  </dl>
                  <div className="mt-3 flex items-center justify-between border-t border-border pt-3 text-xs">
                    <span className="text-muted-foreground">
                      Updated {relativeTime(s.updated_at)}
                    </span>
                    <Link
                      href={`/pi/knowledge/documents?source=${s.id}`}
                      className="font-medium text-primary hover:underline"
                    >
                      Documents
                    </Link>
                  </div>
                </Card>
              </li>
            );
          })}
        </ul>
      )}
      <NewSourceDialog open={open} onOpenChange={setOpen} />
      <ConfirmDialog
        open={Boolean(disableTarget)}
        onOpenChange={(o) => !o && setDisableTarget(null)}
        title={`Disable ${disableTarget?.name ?? "source"}?`}
        description="PI stops using this source's documents in answers."
        consequences={[
          "Documents are kept and can be used again when you re-enable the source.",
          "Answers that relied on this source may hand off to your team instead.",
        ]}
        confirmLabel="Disable source"
        loading={setStatus.isPending}
        onConfirm={() =>
          disableTarget &&
          setStatus.mutate({ id: disableTarget.id, status: "disabled" })
        }
      />
    </PageShell>
  );
}

const KINDS = Object.keys(SOURCE_KIND_LABELS) as KnowledgeSource["kind"][];

const schema = z.object({
  name: z.string().trim().min(2, "Enter a name").max(80),
  kind: z.enum(
    KINDS as [KnowledgeSource["kind"], ...KnowledgeSource["kind"][]],
  ),
  description: z.string().trim().max(300, "Keep it under 300 characters"),
});
type Values = z.infer<typeof schema>;

function NewSourceDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", kind: "faq", description: "" },
  });
  const create = useScopedMutation((v: Values) => piService.createSource(v), {
    invalidate: [[...piKeys.sources], [...piKeys.overview]],
    success: (s) => `${s.name} created`,
    onSuccess: () => {
      form.reset();
      onOpenChange(false);
    },
  });
  const err = form.formState.errors;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form
          onSubmit={form.handleSubmit((v) => create.mutate(v))}
          noValidate
          className="flex min-h-0 flex-1 flex-col"
        >
          <DialogHeader
            title="New knowledge source"
            description="A source groups related documents that PI can quote from."
          />
          <DialogBody className="space-y-4">
            <FormField
              label="Name"
              htmlFor="source-name"
              required
              error={err.name}
            >
              <Input
                id="source-name"
                aria-invalid={Boolean(err.name)}
                placeholder="e.g. Returns & exchanges"
                {...form.register("name")}
              />
            </FormField>
            <FormField
              label="Kind"
              htmlFor="source-kind"
              required
              error={err.kind}
            >
              <NativeSelect id="source-kind" {...form.register("kind")}>
                {KINDS.map((k) => (
                  <option key={k} value={k}>
                    {SOURCE_KIND_LABELS[k]}
                  </option>
                ))}
              </NativeSelect>
            </FormField>
            <FormField
              label="Description"
              htmlFor="source-description"
              optional
              error={err.description}
            >
              <Textarea
                id="source-description"
                rows={3}
                maxLength={300}
                {...form.register("description")}
              />
            </FormField>
          </DialogBody>
          <DialogFooter>
            <Button
              type="button"
              variant="secondary"
              onClick={() => onOpenChange(false)}
              disabled={create.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" loading={create.isPending}>
              Create source
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
