"use client";

import { useState } from "react";
import Link from "next/link";
import {
  CheckCircle2,
  CircleAlert,
  CircleDashed,
  ShieldCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge, Card, CardBody, CardHeader } from "@/components/ui/display";
import { Input } from "@/components/ui/input";
import {
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import { ErrorState, Notice } from "@/components/app/states";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { isDemo } from "@/lib/data-mode";
import { apiRequest } from "@/services/api-client";

interface SetupItem {
  key: string;
  name: string;
  state: "connected" | "not_connected" | "needs_attention" | "platform";
  detail: string;
  required: boolean;
  href: string | null;
}
interface SetupStatus {
  items: SetupItem[];
  ready: boolean;
  connected: number;
  total: number;
}
interface TestResult {
  key: string;
  ok: boolean;
  detail: string;
}

const STATE: Record<
  SetupItem["state"],
  [string, "success" | "neutral" | "warning" | "info"]
> = {
  connected: ["Connected", "success"],
  platform: ["Provided by the Pi team", "info"],
  not_connected: ["Not connected", "neutral"],
  needs_attention: ["Needs attention", "warning"],
};

export function SetupCenterPage() {
  return (
    <RequirePermission permission="integrations.read" area="Setup">
      <PageShell width="default">
        <PageHeader
          title="Setup"
          description="Every tool PI can use: what's ready, what's missing, and where to fix it."
        />
        {isDemo ? (
          <Notice tone="info" title="Live data only">
            Setup status comes from your real connections, so it isn&apos;t
            shown with sample data.
          </Notice>
        ) : (
          <SetupCenter />
        )}
      </PageShell>
    </RequirePermission>
  );
}

function SetupCenter() {
  const status = useScopedQuery(["setup", "status"], () =>
    apiRequest<SetupStatus>("GET", "/setup/status", null),
  );
  const [results, setResults] = useState<TestResult[] | null>(null);
  const [shop, setShop] = useState("");
  const test = useScopedMutation(
    () =>
      apiRequest<{ results: TestResult[] }>("POST", "/setup/test-all", null, {
        body: {},
      }),
    {
      invalidate: [["setup", "status"]],
      onSuccess: (r) => setResults(r.results),
    },
  );
  const connect = useScopedMutation(
    (key: "google_calendar" | "shopify") =>
      apiRequest<{ authorization_url: string }>(
        "POST",
        `/pi/connectors/${key}/start`,
        null,
        {
          body: key === "shopify" ? { shop } : {},
        },
      ),
    { onSuccess: (r) => window.location.assign(r.authorization_url) },
  );
  if (status.isError)
    return (
      <Card>
        <ErrorState
          error={status.error}
          onRetry={() => void status.refetch()}
        />
      </Card>
    );
  const s = status.data;
  if (!s) return null;
  return (
    <div className="space-y-4">
      <Card>
        <CardBody className="flex flex-wrap items-center gap-3">
          <ShieldCheck
            className={s.ready ? "size-6 text-success" : "size-6 text-warning"}
            aria-hidden
          />
          <div className="min-w-0 flex-1">
            <p className="font-semibold">
              {s.ready
                ? "PI has everything it needs"
                : "A few things are missing"}
            </p>
            <p className="text-sm text-muted-foreground">
              {s.connected} of {s.total} tools ready.
            </p>
          </div>
          <Button
            variant="secondary"
            loading={test.isPending}
            onClick={() => test.mutate(undefined)}
          >
            Test all
          </Button>
        </CardBody>
      </Card>
      {results ? (
        <Notice
          tone={results.every((r) => r.ok) ? "success" : "warning"}
          title="Test results"
        >
          <ul className="space-y-1">
            {results.map((r) => (
              <li key={r.key}>
                {r.ok ? "✓" : "✗"} {r.key.replace(/_/g, " ")}: {r.detail}
              </li>
            ))}
            {!results.length ? <li>Nothing connected to test yet.</li> : null}
          </ul>
        </Notice>
      ) : null}
      <Card>
        <CardHeader title="Tools" />
        <ul className="divide-y divide-border">
          {s.items.map((item) => {
            const [label, tone] = STATE[item.state];
            const Icon =
              item.state === "connected" || item.state === "platform"
                ? CheckCircle2
                : item.state === "needs_attention"
                  ? CircleAlert
                  : CircleDashed;
            const oauth =
              item.key === "google_calendar" || item.key === "shopify";
            return (
              <li
                key={item.key}
                className="flex flex-wrap items-center gap-3 px-4 py-3"
              >
                <Icon
                  className={
                    item.state === "needs_attention"
                      ? "size-5 text-warning"
                      : item.state === "not_connected"
                        ? "size-5 text-muted-foreground"
                        : "size-5 text-success"
                  }
                  aria-hidden
                />
                <div className="min-w-0 flex-1">
                  <p className="text-[14px] font-medium">
                    {item.name}
                    {item.required ? (
                      <span className="ms-2 text-xs font-normal text-muted-foreground">
                        Required
                      </span>
                    ) : null}
                  </p>
                  <p className="text-[13px] text-muted-foreground">
                    {item.detail}
                  </p>
                </div>
                <Badge tone={tone}>{label}</Badge>
                {oauth && item.state !== "connected" ? (
                  <div className="flex items-center gap-2">
                    {item.key === "shopify" ? (
                      <Input
                        aria-label="Shopify store address"
                        placeholder="your-store.myshopify.com"
                        className="h-8 w-52"
                        value={shop}
                        onChange={(e) => setShop(e.target.value)}
                      />
                    ) : null}
                    <Button
                      size="sm"
                      variant="secondary"
                      loading={connect.isPending}
                      disabled={
                        item.key === "shopify" && shop.trim().length < 3
                      }
                      onClick={() =>
                        connect.mutate(
                          item.key as "google_calendar" | "shopify",
                        )
                      }
                    >
                      Connect
                    </Button>
                  </div>
                ) : item.href && item.state !== "platform" ? (
                  <Link
                    href={item.href}
                    className="text-sm font-medium text-primary underline"
                  >
                    {item.state === "connected" ? "Manage" : "Set up"}
                  </Link>
                ) : null}
              </li>
            );
          })}
        </ul>
      </Card>
    </div>
  );
}
