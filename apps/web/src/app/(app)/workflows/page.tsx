"use client";

import { useState } from "react";
import Link from "next/link";
import { z } from "zod";
import { apiRequest } from "@/services/api-client";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { PageShell, PageHeader } from "@/components/app/page";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/display";
import { ErrorState } from "@/components/app/states";
import { humanize } from "@/lib/format";
import { WorkflowActions } from "@/features/workflows/workflow-actions";
import { isDemo } from "@/lib/data-mode";
import { useSession } from "@/features/auth/session-provider";

const runSchema = z.object({
  id: z.string(),
  tool_key: z.string(),
  action_class: z.string(),
  status: z.string(),
  result: z.record(z.string(), z.unknown()),
  error_code: z.string().nullable(),
  expires_at: z.string(),
});
type Run = z.infer<typeof runSchema>;
const choices = [
  [
    "overview.summary",
    "Business overview",
    "Review activity across your workspace.",
  ],
  ["sales.pipeline", "Sales pipeline", "Review opportunities by stage."],
  [
    "quotes.pending",
    "Quotes to review",
    "Find quotations that need attention.",
  ],
  ["reports.revenue", "Revenue report", "Review recorded revenue."],
  ["finance.summary", "Finance summary", "Review the last 30 days."],
  ["hr.headcount", "Team headcount", "Review your team by department."],
  ["inventory.low_stock", "Low stock", "Review tracked physical inventory."],
  [
    "administration.settings",
    "Business settings",
    "Review your operating policies.",
  ],
] as const;

function Result({ value }: { value: unknown }) {
  if (value === null || value === undefined)
    return <span className="text-muted-foreground">—</span>;
  if (Array.isArray(value))
    return (
      <div className="space-y-3">
        {value.length
          ? value.map((item, i) => (
              <div key={i} className="rounded border p-3">
                <Result value={item} />
              </div>
            ))
          : "No records"}
      </div>
    );
  if (typeof value === "object")
    return (
      <dl className="grid gap-3 sm:grid-cols-2">
        {Object.entries(value)
          .filter(([key]) => !key.endsWith("_id") && key !== "id")
          .map(([key, item]) => (
            <div key={key} className="min-w-0">
              <dt className="mb-1 text-xs text-muted-foreground">
                {humanize(key)}
              </dt>
              <dd className="break-words text-sm">
                <Result value={item} />
              </dd>
            </div>
          ))}
      </dl>
    );
  return (
    <span>
      {typeof value === "boolean" ? (value ? "Yes" : "No") : String(value)}
    </span>
  );
}

export default function WorkflowsPage() {
  const { scopeKey } = useSession();
  return <WorkspaceWorkflows key={scopeKey.join(":")} />;
}

function WorkspaceWorkflows() {
  const [result, setResult] = useState<Run | null>(null);
  const tools = useScopedQuery(
    ["workflows", "tools"],
    () =>
      apiRequest(
        "GET",
        "/workflows/tools",
        z.array(z.object({ key: z.string() })),
      ),
    { enabled: !isDemo },
  );
  const run = useScopedMutation(
    (tool: string) =>
      apiRequest("POST", "/workflows", runSchema, {
        body: { tool, arguments: {}, idempotency_key: crypto.randomUUID() },
      }),
    { onSuccess: setResult, invalidate: [["workflows"]] },
  );
  return (
    <PageShell>
      <PageHeader
        title="Business workflows"
        description="Review live business records through the same controlled services used by your team."
        actions={
          <Button asChild variant="outline">
            <Link href="/">Overview</Link>
          </Button>
        }
      />
      {tools.error ? (
        <ErrorState error={tools.error} onRetry={() => void tools.refetch()} />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {choices
            .filter(([key]) => tools.data?.some((t) => t.key === key))
            .map(([key, title, description]) => (
              <Card key={key} className="p-5">
                <h2 className="font-medium">{title}</h2>
                <p className="my-3 text-sm text-muted-foreground">
                  {description}
                </p>
                <Button
                  disabled={run.isPending}
                  onClick={() => run.mutate(key)}
                >
                  Run review
                </Button>
              </Card>
            ))}
        </div>
      )}
      {isDemo && <p>Use live mode to save and approve business workflows.</p>}
      {!isDemo && tools.isPending && (
        <p role="status">Loading available workflows…</p>
      )}
      {!isDemo && <WorkflowActions />}
      {run.isPending && (
        <p className="mt-6" role="status">
          Reviewing workspace records…
        </p>
      )}
      {result && (
        <Card className="mt-6 p-5">
          <h2 className="mb-4 font-medium">
            {humanize(result.tool_key.replaceAll(".", "_"))} ·{" "}
            {humanize(result.status)}
          </h2>
          {result.status === "failed" ? (
            <p>
              The workflow could not finish. Open the relevant business record
              to review it.
            </p>
          ) : (
            <Result value={result.result} />
          )}
        </Card>
      )}
    </PageShell>
  );
}
