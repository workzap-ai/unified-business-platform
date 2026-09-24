"use client";

import { useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Controller, useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { FileText, Plus, Upload } from "lucide-react";
import { formatDateTime, formatNumber, relativeTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import {
  SegmentedList,
  SegmentedTrigger,
  Skeleton,
  Tabs,
} from "@/components/ui/display";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  SheetContent,
} from "@/components/ui/overlays";
import {
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import { DataTable, type Column } from "@/components/app/data-table";
import { FilterBar, FilterSelect, SearchInput } from "@/components/app/filters";
import { FormField } from "@/components/app/forms";
import { PropertyList } from "@/components/app/record";
import { EmptyState, ErrorState, Notice } from "@/components/app/states";
import { StatusBadge } from "@/components/app/status-badge";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useUrlState } from "@/hooks/use-url-state";
import { piService } from "../../service";
import type { KnowledgeDocument, KnowledgeSource } from "../../types";
import { formatBytesKb, humanizeError, piKeys } from "../shared";
import {
  KNOWLEDGE_HEADER,
  KnowledgeNav,
  pollWhileProcessing,
} from "./knowledge-shared";

export function KnowledgeDocumentsPage() {
  return (
    <RequirePermission permission="pi.knowledge.manage" area="PI knowledge">
      <Documents />
    </RequirePermission>
  );
}

function Documents() {
  const params = useSearchParams();
  const [state, set, reset] = useUrlState({ source: "", status: "", q: "" });
  const [adding, setAdding] = useState(params.get("add") === "1");
  const [openId, setOpenId] = useState<string | null>(null);
  const sources = useScopedQuery(piKeys.sources, () => piService.sources());
  const documents = useScopedQuery(
    [...piKeys.documents, state.source, state.status, state.q],
    () =>
      piService.documents({
        sourceId: state.source || undefined,
        status: state.status || undefined,
        search: state.q || undefined,
      }),
    { refetchInterval: (q) => pollWhileProcessing(q.state.data) },
  );

  const columns: Column<KnowledgeDocument>[] = [
    {
      key: "title",
      header: "Title",
      cell: (d) => (
        <div className="min-w-0">
          <p className="truncate font-medium">{d.title}</p>
          <p className="truncate text-xs text-muted-foreground sm:hidden">
            {d.source_name}
          </p>
        </div>
      ),
    },
    {
      key: "source",
      header: "Source",
      cell: (d) => d.source_name,
      hideBelow: "sm",
    },
    {
      key: "type",
      header: "Type",
      cell: (d) => (
        <span className="font-mono text-xs text-muted-foreground">
          {d.mime_type}
        </span>
      ),
      hideBelow: "xl",
    },
    {
      key: "size",
      header: "Size",
      align: "right",
      cell: (d) => (
        <span className="tabular">{formatBytesKb(d.byte_size)}</span>
      ),
      hideBelow: "lg",
    },
    {
      key: "passages",
      header: "Passages",
      align: "right",
      cell: (d) => (
        <span className="tabular">{formatNumber(d.chunk_count)}</span>
      ),
      hideBelow: "md",
    },
    {
      key: "status",
      header: "Status",
      cell: (d) => <StatusBadge status={d.status} />,
    },
    {
      key: "by",
      header: "Added by",
      cell: (d) => d.created_by_label,
      hideBelow: "xl",
    },
    {
      key: "added",
      header: "Added",
      cell: (d) => (
        <time dateTime={d.created_at} title={formatDateTime(d.created_at)}>
          {relativeTime(d.created_at)}
        </time>
      ),
      hideBelow: "lg",
    },
  ];

  const active = [state.source, state.status, state.q].filter(Boolean).length;

  return (
    <PageShell>
      <PageHeader
        {...KNOWLEDGE_HEADER}
        actions={
          <Button
            onClick={() => setAdding(true)}
            disabled={!sources.data?.length}
          >
            <Plus /> Add document
          </Button>
        }
      />
      <KnowledgeNav />
      <FilterBar activeCount={active} onClear={reset}>
        <SearchInput
          value={state.q}
          onChange={(q) => set({ q })}
          placeholder="Search documents…"
          className="w-full md:w-64"
        />
        <FilterSelect
          label="Source"
          value={state.source}
          onChange={(source) => set({ source })}
          options={(sources.data ?? []).map((s) => ({
            value: s.id,
            label: s.name,
            count: s.documents,
          }))}
        />
        <FilterSelect
          label="Status"
          value={state.status}
          onChange={(status) => set({ status })}
          options={[
            { value: "pending", label: "Pending" },
            { value: "processing", label: "Processing" },
            { value: "ready", label: "Ready" },
            { value: "failed", label: "Failed" },
          ]}
        />
      </FilterBar>
      <DataTable
        columns={columns}
        rows={documents.data}
        getRowId={(d) => d.id}
        loading={documents.isPending}
        error={documents.error}
        onRetry={() => void documents.refetch()}
        onRowClick={(d) => setOpenId(d.id)}
        caption="Knowledge documents"
        empty={
          <EmptyState
            tone="pi"
            icon={FileText}
            compact
            title={active ? "No documents match" : "No documents yet"}
            description={
              active
                ? "Try a different search or clear the filters."
                : sources.data?.length
                  ? "Add a text or Markdown document so PI can answer from it."
                  : "Create a knowledge source first, then add documents to it."
            }
            action={
              !active && sources.data?.length ? (
                <Button size="sm" onClick={() => setAdding(true)}>
                  <Plus /> Add document
                </Button>
              ) : undefined
            }
          />
        }
      />
      {sources.data && (
        <AddDocumentDialog
          open={adding}
          onOpenChange={setAdding}
          sources={sources.data}
          defaultSource={state.source}
        />
      )}
      <Dialog
        open={Boolean(openId)}
        onOpenChange={(o) => !o && setOpenId(null)}
      >
        {openId && <DocumentSheet id={openId} />}
      </Dialog>
    </PageShell>
  );
}

function DocumentSheet({ id }: { id: string }) {
  const doc = useScopedQuery(
    piKeys.document(id),
    () => piService.document(id),
    {
      refetchInterval: (q) =>
        q.state.data && ["pending", "processing"].includes(q.state.data.status)
          ? 3000
          : false,
    },
  );
  const d = doc.data;
  return (
    <SheetContent width="lg">
      <DialogHeader
        title={d?.title ?? "Document"}
        description={d ? d.source_name : undefined}
      />
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-4">
        {doc.isError ? (
          <ErrorState
            compact
            error={doc.error}
            onRetry={() => void doc.refetch()}
          />
        ) : !d ? (
          <Skeleton className="h-60" />
        ) : (
          <>
            {d.status === "failed" && (
              <Notice tone="danger" title="Processing failed">
                {humanizeError(d.error_code)}
              </Notice>
            )}
            <PropertyList
              items={[
                { label: "Status", value: <StatusBadge status={d.status} /> },
                { label: "Source", value: d.source_name },
                { label: "Type", value: d.mime_type },
                { label: "Size", value: formatBytesKb(d.byte_size) },
                { label: "Passages", value: formatNumber(d.chunk_count) },
                { label: "Added by", value: d.created_by_label },
                { label: "Added", value: formatDateTime(d.created_at) },
                {
                  label: "Processed",
                  value: d.processed_at
                    ? formatDateTime(d.processed_at)
                    : undefined,
                },
              ]}
            />
            <div>
              <h3 className="mb-1.5 text-[13px] font-semibold">
                Content preview
              </h3>
              {d.body ? (
                <pre className="scrollbar-thin max-h-[420px] overflow-auto rounded-lg border border-border bg-surface-muted/50 p-3 font-mono text-xs leading-5 whitespace-pre-wrap">
                  {d.body}
                </pre>
              ) : (
                <p className="text-[13px] text-muted-foreground">
                  No preview is available for this document.
                </p>
              )}
            </div>
          </>
        )}
      </div>
    </SheetContent>
  );
}

const MAX_BYTES = 1024 * 1024;

const schema = z.object({
  source_id: z.string().min(1, "Choose a source"),
  title: z.string().trim().min(2, "Enter a title").max(160),
  body: z
    .string()
    .refine((v) => v.trim().length > 0, "Add some text")
    .refine(
      (v) => new Blob([v]).size <= MAX_BYTES,
      "Documents are limited to 1 MB of text",
    ),
  mime_type: z.enum(["text/plain", "text/markdown"]),
});
type Values = z.infer<typeof schema>;

function AddDocumentDialog({
  open,
  onOpenChange,
  sources,
  defaultSource,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  sources: KnowledgeSource[];
  defaultSource: string;
}) {
  const [mode, setMode] = useState<"paste" | "upload">("paste");
  const [fileName, setFileName] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const activeSources = sources.filter((s) => s.status === "active");
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      source_id: defaultSource || activeSources[0]?.id || "",
      title: "",
      body: "",
      mime_type: "text/plain",
    },
  });
  const add = useScopedMutation((v: Values) => piService.addDocument(v), {
    invalidate: [
      [...piKeys.documents],
      [...piKeys.sources],
      [...piKeys.overview],
    ],
    success: (d) => `${d.title} added — processing`,
    onSuccess: () => {
      form.reset();
      setFileName(null);
      onOpenChange(false);
    },
  });

  function onFile(file: File | undefined) {
    setFileError(null);
    setFileName(null);
    if (!file) return;
    const lower = file.name.toLowerCase();
    const markdown = lower.endsWith(".md") || lower.endsWith(".markdown");
    const text = lower.endsWith(".txt");
    if (!markdown && !text) {
      setFileError("Choose a .txt or .md file.");
      return;
    }
    if (file.type && !file.type.startsWith("text/")) {
      setFileError("That file isn't plain text.");
      return;
    }
    if (file.size > MAX_BYTES) {
      setFileError("Files are limited to 1 MB.");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const content = typeof reader.result === "string" ? reader.result : "";
      if (content.includes("\u0000")) {
        setFileError(
          "That file doesn't look like text. Save it as UTF-8 text.",
        );
        return;
      }
      form.setValue("body", content, {
        shouldDirty: true,
        shouldValidate: true,
      });
      form.setValue("mime_type", markdown ? "text/markdown" : "text/plain");
      if (!form.getValues("title"))
        form.setValue("title", file.name.replace(/\.(txt|md|markdown)$/i, ""), {
          shouldValidate: true,
        });
      setFileName(file.name);
    };
    reader.onerror = () => setFileError("The file couldn't be read.");
    reader.readAsText(file);
  }

  const err = form.formState.errors;
  const body = useWatch({ control: form.control, name: "body" });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg">
        <form
          onSubmit={form.handleSubmit((v) => add.mutate(v))}
          noValidate
          className="flex min-h-0 flex-1 flex-col"
        >
          <DialogHeader
            title="Add document"
            description="Plain text or Markdown, up to 1 MB. PI splits it into searchable passages."
          />
          <DialogBody className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField
                label="Source"
                htmlFor="doc-source"
                required
                error={err.source_id}
              >
                <NativeSelect id="doc-source" {...form.register("source_id")}>
                  <option value="">Choose a source…</option>
                  {sources.map((s) => (
                    <option
                      key={s.id}
                      value={s.id}
                      disabled={s.status !== "active"}
                    >
                      {s.name}
                      {s.status !== "active" ? " (disabled)" : ""}
                    </option>
                  ))}
                </NativeSelect>
              </FormField>
              <FormField
                label="Title"
                htmlFor="doc-title"
                required
                error={err.title}
              >
                <Input
                  id="doc-title"
                  aria-invalid={Boolean(err.title)}
                  {...form.register("title")}
                />
              </FormField>
            </div>
            <Tabs
              value={mode}
              onValueChange={(v) => setMode(v as "paste" | "upload")}
            >
              <SegmentedList aria-label="Content input">
                <SegmentedTrigger value="paste">Paste text</SegmentedTrigger>
                <SegmentedTrigger value="upload">Upload file</SegmentedTrigger>
              </SegmentedList>
            </Tabs>
            {mode === "paste" ? (
              <>
                <FormField
                  label="Content"
                  htmlFor="doc-body"
                  required
                  error={err.body}
                  help={`${formatBytesKb(new Blob([body]).size)} of 1,024 KB`}
                >
                  <Textarea
                    id="doc-body"
                    rows={10}
                    className="font-mono text-[13px]"
                    aria-invalid={Boolean(err.body)}
                    {...form.register("body")}
                  />
                </FormField>
                <Controller
                  control={form.control}
                  name="mime_type"
                  render={({ field }) => (
                    <FormField label="Format" htmlFor="doc-format">
                      <NativeSelect
                        id="doc-format"
                        value={field.value}
                        onChange={(e) => field.onChange(e.target.value)}
                      >
                        <option value="text/plain">Plain text</option>
                        <option value="text/markdown">Markdown</option>
                      </NativeSelect>
                    </FormField>
                  )}
                />
              </>
            ) : (
              <FormField
                label="File"
                htmlFor="doc-file"
                required
                error={fileError ?? err.body?.message}
                help={
                  fileName
                    ? `Loaded ${fileName} (${formatBytesKb(new Blob([body]).size)})`
                    : ".txt or .md, UTF-8, up to 1 MB"
                }
              >
                <div className="flex items-center gap-2">
                  <input
                    ref={fileRef}
                    id="doc-file"
                    type="file"
                    accept=".txt,.md,.markdown,text/plain,text/markdown"
                    className="sr-only"
                    onChange={(e) => onFile(e.target.files?.[0])}
                  />
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => fileRef.current?.click()}
                  >
                    <Upload /> Choose file
                  </Button>
                  {fileName && (
                    <span className="truncate text-[13px]">{fileName}</span>
                  )}
                </div>
              </FormField>
            )}
          </DialogBody>
          <DialogFooter>
            <Button
              type="button"
              variant="secondary"
              onClick={() => onOpenChange(false)}
              disabled={add.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" loading={add.isPending}>
              Add document
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
