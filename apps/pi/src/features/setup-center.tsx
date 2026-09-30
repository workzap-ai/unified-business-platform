"use client";

import { useQuery } from "@tanstack/react-query";
import {
  CheckCircle2,
  CircleAlert,
  CircleDashed,
  ShieldCheck,
} from "lucide-react";
import Link from "next/link";
import * as React from "react";

import {
  Badge,
  Button,
  Card,
  CardSection,
  LoadingBlock,
  Notice,
} from "@/components/ui";
import { errorText, get, post } from "@/lib/api";
import { useAction, useBusinessKey, useCan } from "@/lib/session";

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
  platform: ["Provided by Pi", "info"],
  not_connected: ["Not connected", "neutral"],
  needs_attention: ["Needs attention", "warning"],
};

/** Every tool Pi can use, in one list: what's ready, what's missing, where to fix it. */
export function SetupCenter() {
  const key = useBusinessKey();
  const can = useCan();
  const status = useQuery({
    queryKey: key(["setup-status"]),
    queryFn: () => get<SetupStatus>("/setup/status"),
    enabled: can("integrations.read"),
  });
  const [results, setResults] = React.useState<TestResult[] | null>(null);
  const test = useAction(
    () => post<{ results: TestResult[] }>("/setup/test-all"),
    {
      invalidate: [["setup-status"]],
      onSuccess: (r) => setResults(r.results),
    },
  );
  if (!can("integrations.read"))
    return (
      <Notice tone="info">Ask your business owner to set up tools.</Notice>
    );
  if (status.isPending) return <LoadingBlock rows={4} />;
  if (status.isError)
    return <Notice tone="danger">{errorText(status.error)}</Notice>;
  const s = status.data;
  return (
    <div className="space-y-4">
      <Card>
        <CardSection className="flex flex-wrap items-center gap-3">
          <ShieldCheck
            className={s.ready ? "size-6 text-success" : "size-6 text-warning"}
            aria-hidden
          />
          <div className="min-w-0 flex-1">
            <p className="font-semibold">
              {s.ready
                ? "Pi has everything it needs"
                : "A few things are missing"}
            </p>
            <p className="text-sm text-muted-foreground">
              {s.connected} of {s.total} tools ready. Optional tools add more
              things Pi can do.
            </p>
          </div>
          {can("integrations.operate") ? (
            <Button
              variant="secondary"
              loading={test.isPending}
              onClick={() => test.mutate(undefined)}
            >
              Test all
            </Button>
          ) : null}
        </CardSection>
      </Card>
      {results ? (
        <Notice
          tone={results.every((r) => r.ok) ? "success" : "warning"}
          title={results.length ? "Test results" : "Nothing to test yet"}
        >
          <ul className="space-y-1">
            {results.map((r) => (
              <li key={r.key}>
                {r.ok ? "✓" : "✗"} {r.key.replace(/_/g, " ")}: {r.detail}
              </li>
            ))}
          </ul>
        </Notice>
      ) : null}
      <Card>
        <ul className="divide-y divide-border">
          {s.items.map((item) => {
            const [label, tone] = STATE[item.state];
            const Icon =
              item.state === "connected" || item.state === "platform"
                ? CheckCircle2
                : item.state === "needs_attention"
                  ? CircleAlert
                  : CircleDashed;
            return (
              <li
                key={item.key}
                className="flex flex-wrap items-center gap-3 p-4"
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
                  <p className="font-medium">
                    {item.name}
                    {item.required ? (
                      <span className="ms-2 text-xs font-normal text-muted-foreground">
                        Required
                      </span>
                    ) : null}
                  </p>
                  <p className="text-sm text-muted-foreground" data-user-text>
                    {item.detail}
                  </p>
                </div>
                <Badge tone={tone}>{label}</Badge>
                {item.href && item.state !== "platform" ? (
                  <Link
                    href={item.href}
                    className="text-sm font-medium text-accent underline"
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
