"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { z } from "zod";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import { apiRequest, pageSchema } from "@/services/api-client";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/display";
import { Input, NativeSelect } from "@/components/ui/input";
import { ErrorState } from "@/components/app/states";
import { humanize, formatDateTime, formatMoney } from "@/lib/format";

const runSchema = z.object({
  id: z.string(),
  tool_key: z.string(),
  status: z.string(),
  result: z.record(z.string(), z.unknown()),
  arguments: z.record(z.string(), z.unknown()),
  error_code: z.string().nullable(),
  created_at: z.string(),
  expires_at: z.string(),
});
const recordSchema = z.object({
  id: z.string(),
  number: z.string(),
  status: z.string(),
  customer_name: z.string().nullable().optional(),
});
const modules = [
  {
    key: "quotes",
    title: "Quotes",
    path: "/quotes",
    permission: "quotes.read",
  },
  {
    key: "orders",
    title: "Orders",
    path: "/orders",
    permission: "orders.read",
  },
  {
    key: "billing",
    title: "Invoices",
    path: "/billing/invoices",
    permission: "billing.read",
  },
];
const previewSchema = z.object({
  number: z.string(),
  status: z.string(),
  customer_name: z.string().nullable().optional(),
  currency: z.string(),
  total: z.string(),
  notes: z.string().optional(),
  lines: z.array(
    z.object({
      description: z.string(),
      quantity: z.union([z.string(), z.number()]),
      line_total: z.string(),
    }),
  ),
});

export function WorkflowActions() {
  const { scopeKey } = useSession();
  return <WorkspaceActions key={scopeKey.join(":")} />;
}

function WorkspaceActions() {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(timer);
  }, []);
  const { can } = useSession();
  const params = useSearchParams();
  const [selectedId, setSelectedId] = useState(params.get("run") ?? "");
  const [moduleKey, setModuleKey] = useState(
    modules.find((m) => can(m.permission))?.key ?? "quotes",
  );
  const [recordId, setRecordId] = useState("");
  const [search, setSearch] = useState("");
  const [action, setAction] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const selectedModule = modules.find((m) => m.key === moduleKey)!;
  const tools = useScopedQuery(["workflows", "tools"], () =>
    apiRequest(
      "GET",
      "/workflows/tools",
      z.array(z.object({ key: z.string() })),
    ),
  );
  const history = useScopedQuery(["workflows", "history", status, page], () =>
    apiRequest("GET", "/workflows", pageSchema(runSchema), {
      query: { status, page, page_size: 10 },
    }),
  );
  const selected = useScopedQuery(
    ["workflows", "detail", selectedId],
    () => apiRequest("GET", `/workflows/${selectedId}`, runSchema),
    { enabled: Boolean(selectedId) },
  );
  const records = useScopedQuery(
    ["workflow-records", moduleKey, search],
    () =>
      apiRequest("GET", selectedModule.path, pageSchema(recordSchema), {
        query: { search, page_size: 50 },
      }),
    { enabled: can(selectedModule.permission) },
  );
  const record = useScopedQuery(
    ["workflow-records", moduleKey, recordId],
    () =>
      apiRequest(
        "GET",
        `${selectedModule.path}/${recordId}`,
        z.object({ next_actions: z.array(z.string()) }),
      ),
    { enabled: Boolean(recordId) && can(selectedModule.permission) },
  );
  const actions = (record.data?.next_actions ?? [])
    .map((a) => ({
      title: humanize(a),
      key: `${moduleKey}.${a === "convert_to_order" ? "convert" : a}`,
    }))
    .filter((a) => tools.data?.some((t) => t.key === a.key));
  const invalidate = [
    ["workflows"],
    ["workflow-records"],
    ["orders"],
    ["quotes"],
    ["invoices"],
    ["billing"],
    ["overview"],
    ["notifications"],
  ];
  const prepare = useScopedMutation(
    () =>
      apiRequest("POST", "/workflows", runSchema, {
        body: {
          tool: action,
          arguments: { id: recordId },
          idempotency_key: crypto.randomUUID(),
        },
      }),
    { invalidate, onSuccess: (data) => setSelectedId(data.id) },
  );
  const decide = useScopedMutation(
    (decision: "approve" | "reject") =>
      apiRequest("POST", `/workflows/${selectedId}/${decision}`, runSchema, {
        body: {},
      }),
    { invalidate },
  );
  const result = selected.data;
  const preview = previewSchema.safeParse(result?.result);
  const resultModule = modules.find((m) =>
    result?.tool_key.startsWith(`${m.key}.`),
  );
  // Quote conversion returns an order. Keep the link aligned with the actual result.
  const resultPath =
    result?.tool_key === "quotes.convert" && result.status === "completed"
      ? "/orders"
      : resultModule?.path;
  const resultId =
    result?.status === "completed" ? result.result.id : result?.arguments.id;
  return (
    <>
      <Card className="my-6 p-5">
        <h2 className="font-medium">Prepare an action</h2>
        <p className="mt-2 mb-4 text-sm text-muted-foreground">
          Choose a quote, order, or invoice. Review the proposal before applying
          the action.
        </p>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <label className="space-y-2 text-sm">
            Record type
            <NativeSelect
              value={moduleKey}
              onChange={(e) => {
                setModuleKey(e.target.value);
                setRecordId("");
                setAction("");
                setSearch("");
              }}
            >
              {modules
                .filter((m) => can(m.permission))
                .map((m) => (
                  <option key={m.key} value={m.key}>
                    {m.title}
                  </option>
                ))}
            </NativeSelect>
          </label>
          <label className="space-y-2 text-sm">
            Search record number
            <Input
              value={search}
              maxLength={40}
              onChange={(e) => {
                setSearch(e.target.value);
                setRecordId("");
                setAction("");
              }}
            />
          </label>
          <label className="space-y-2 text-sm">
            Business record
            <NativeSelect
              value={recordId}
              disabled={records.isPending || !can(selectedModule.permission)}
              onChange={(e) => {
                setRecordId(e.target.value);
                setAction("");
              }}
            >
              <option value="">Choose a record</option>
              {records.data?.items.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.number} · {r.customer_name ?? "Customer"} ·{" "}
                  {humanize(r.status)}
                </option>
              ))}
            </NativeSelect>
          </label>
          <label className="space-y-2 text-sm">
            Action
            <NativeSelect
              value={action}
              onChange={(e) => setAction(e.target.value)}
              disabled={!recordId || record.isPending}
            >
              <option value="">Choose an action</option>
              {actions.map((a) => (
                <option key={a.key} value={a.key}>
                  {a.title}
                </option>
              ))}
            </NativeSelect>
          </label>
        </div>
        {records.error && (
          <ErrorState
            error={records.error}
            onRetry={() => void records.refetch()}
          />
        )}
        {record.error && (
          <ErrorState
            error={record.error}
            onRetry={() => void record.refetch()}
          />
        )}
        <Button
          className="mt-4"
          disabled={
            !recordId ||
            !actions.some((a) => a.key === action) ||
            prepare.isPending
          }
          onClick={() => prepare.mutate()}
        >
          Prepare review
        </Button>
      </Card>
      {selectedId && selected.isPending && (
        <p role="status">Loading workflow…</p>
      )}
      {selected.error && (
        <ErrorState
          error={selected.error}
          onRetry={() => void selected.refetch()}
        />
      )}
      {result && (
        <Card className="my-6 p-5">
          <h2 className="font-medium">
            {humanize(result.tool_key.replaceAll(".", "_"))} ·{" "}
            {humanize(result.status)}
          </h2>
          {preview.success && (
            <div className="my-4 space-y-2 text-sm">
              <p>
                {preview.data.number} · {preview.data.customer_name} ·{" "}
                {humanize(preview.data.status)}
              </p>
              {preview.data.lines.map((line, i) => (
                <p key={i}>
                  {line.description} × {line.quantity} ·{" "}
                  {formatMoney(line.line_total, preview.data.currency)}
                </p>
              ))}
              <p className="font-semibold">
                Total {formatMoney(preview.data.total, preview.data.currency)}
              </p>
              {preview.data.notes && (
                <p className="whitespace-pre-wrap">{preview.data.notes}</p>
              )}
            </div>
          )}
          {result.error_code && (
            <p role="alert" className="my-3 text-sm">
              {humanize(result.error_code)}. Open the record to resolve this
              before preparing another review.
            </p>
          )}
          {resultPath && typeof resultId === "string" && (
            <Link
              className="text-sm text-primary underline"
              href={`${resultPath}/${resultId}`}
            >
              Open business record
            </Link>
          )}
          {result.status === "pending_approval" && (
            <div className="mt-4 space-y-3">
              <p className="text-sm text-muted-foreground">
                {Date.parse(result.expires_at) <= now
                  ? "This review expired. Reject it and prepare a fresh proposal."
                  : "Approval applies the action to this record. If the record changes, prepare a fresh review."}
              </p>
              <div className="flex flex-wrap gap-2">
                <Button
                  disabled={
                    Date.parse(result.expires_at) <= now || decide.isPending
                  }
                  onClick={() => decide.mutate("approve")}
                >
                  Approve and run
                </Button>
                <Button
                  variant="outline"
                  disabled={decide.isPending}
                  onClick={() => decide.mutate("reject")}
                >
                  Reject proposal
                </Button>
              </div>
            </div>
          )}
        </Card>
      )}
      <section className="my-6">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-medium">Your workflow history</h2>
          <NativeSelect
            aria-label="Workflow status"
            className="w-48"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(1);
            }}
          >
            <option value="">All statuses</option>
            {["pending_approval", "completed", "failed", "rejected"].map(
              (s) => (
                <option key={s} value={s}>
                  {humanize(s)}
                </option>
              ),
            )}
          </NativeSelect>
        </div>
        {history.error ? (
          <ErrorState
            error={history.error}
            onRetry={() => void history.refetch()}
          />
        ) : history.isPending ? (
          <p role="status">Loading workflow history…</p>
        ) : !history.data.items.length ? (
          <p className="text-sm text-muted-foreground">
            No workflows match this view.
          </p>
        ) : (
          <div className="space-y-2">
            {history.data.items.map((item) => (
              <button
                type="button"
                key={item.id}
                onClick={() => setSelectedId(item.id)}
                className="flex w-full flex-wrap justify-between gap-2 rounded-lg border bg-surface p-3 text-left text-sm hover:bg-surface-muted"
              >
                <span>
                  {humanize(item.tool_key.replaceAll(".", "_"))} ·{" "}
                  {humanize(item.status)}
                </span>
                <span className="text-xs text-muted-foreground">
                  {formatDateTime(item.created_at)}
                </span>
              </button>
            ))}
          </div>
        )}
        <div className="mt-3 flex items-center gap-3">
          <Button
            variant="outline"
            disabled={page === 1 || history.isFetching}
            onClick={() => setPage(page - 1)}
          >
            Previous
          </Button>
          <span className="text-sm">Page {page}</span>
          <Button
            variant="outline"
            disabled={
              !history.data ||
              page * 10 >= history.data.total ||
              history.isFetching
            }
            onClick={() => setPage(page + 1)}
          >
            Next
          </Button>
        </div>
      </section>
    </>
  );
}
