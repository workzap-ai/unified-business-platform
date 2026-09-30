"use client";

import { useEffect, useRef, useState } from "react";
import { ExternalLink, Phone, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge, Card, CardBody, CardHeader } from "@/components/ui/display";
import { Notice } from "@/components/app/states";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { isDemo } from "@/lib/data-mode";
import { cn } from "@/lib/utils";
import { apiRequest } from "@/services/api-client";

interface KapsoStatus {
  connection: {
    status: string;
    display_phone_number?: string | null;
    setup_url?: string | null;
    health?: { status?: string } | null;
    problem?: string | null;
  };
  provider_available: boolean;
  webhook_ready: boolean;
}
interface PoolNumber {
  id: string;
  display_phone_number: string;
  country: string;
  price_label: string;
  offered_to_you: boolean;
}

const kapsoKey = ["pi", "whatsapp", "kapso"] as const;
const poolKey = ["pi", "whatsapp", "pool"] as const;

const api = {
  status: () => apiRequest<KapsoStatus>("GET", "/pi/whatsapp/kapso", null),
  numbers: () => apiRequest<PoolNumber[]>("GET", "/pi/whatsapp/numbers", null),
  choose: (id: string) =>
    apiRequest("POST", `/pi/whatsapp/numbers/${id}/choose`, null, { body: {} }),
  setup: () =>
    apiRequest<KapsoStatus["connection"]>(
      "POST",
      "/pi/whatsapp/kapso/setup",
      null,
      {
        body: {},
      },
    ),
  health: () =>
    apiRequest("POST", "/pi/whatsapp/kapso/health", null, { body: {} }),
  disconnect: () =>
    apiRequest("POST", "/pi/whatsapp/kapso/disconnect", null, { body: {} }),
};

/**
 * WhatsApp through Kapso (recommended): take a ready number from the platform's pool, or
 * authorize your own number on Kapso's secure page. No Meta keys are pasted.
 */
export function KapsoConnect({ onChange }: { onChange?: () => void }) {
  if (isDemo) return null; // Sample-data mode has no Kapso project behind it.
  return <KapsoPanel onChange={onChange} />;
}

function KapsoPanel({ onChange }: { onChange?: () => void }) {
  const status = useScopedQuery(kapsoKey, api.status);
  const numbers = useScopedQuery(poolKey, api.numbers);
  const [picked, setPicked] = useState<string | null>(null);
  const invalidate = [[...kapsoKey], [...poolKey], ["pi"]];
  const choose = useScopedMutation((id: string) => api.choose(id), {
    invalidate,
    success: "WhatsApp number connected",
    onSuccess: () => onChange?.(),
  });
  const setup = useScopedMutation(() => api.setup(), {
    onSuccess: (row) => {
      if (row.setup_url) window.location.assign(row.setup_url);
    },
  });
  const health = useScopedMutation(() => api.health(), {
    invalidate,
    success: "Health checked",
  });
  const disconnect = useScopedMutation(() => api.disconnect(), {
    invalidate,
    success: "Number disconnected",
    onSuccess: () => onChange?.(),
  });
  const s = status.data;
  if (!s) return null;
  const c = s.connection;
  if (c.status === "connected") {
    return (
      <Card className="mb-4">
        <CardHeader title="Connected through Kapso" />
        <CardBody className="flex flex-wrap items-center gap-3">
          <ShieldCheck className="size-5 text-success" aria-hidden />
          <span className="font-medium tabular-nums">
            {c.display_phone_number}
          </span>
          {c.health?.status ? (
            <Badge tone="outline">{c.health.status}</Badge>
          ) : null}
          <span className="flex-1" />
          <Button
            variant="secondary"
            size="sm"
            loading={health.isPending}
            onClick={() => health.mutate(undefined)}
          >
            Check health
          </Button>
          <Button
            variant="danger-outline"
            size="sm"
            loading={disconnect.isPending}
            onClick={() => disconnect.mutate(undefined)}
          >
            Disconnect
          </Button>
        </CardBody>
      </Card>
    );
  }
  const pool = numbers.data ?? [];
  const selected = picked ?? pool.find((n) => n.offered_to_you)?.id ?? null;
  return (
    <Card className="mb-4">
      <CardHeader
        title="Connect WhatsApp (recommended)"
        description="Take a ready number from us, or connect the number you already use. No Meta keys needed."
      />
      <CardBody className="space-y-5">
        {!s.provider_available ? (
          <Notice
            tone="warning"
            title="Kapso isn't switched on for this server yet"
          >
            Ask the Pi team to add the Kapso project key. Until then you can use
            the advanced Meta setup below.
          </Notice>
        ) : null}
        {c.status === "action_required" || c.status === "disconnected" ? (
          <Notice tone="danger" title="Your number needs attention">
            {c.problem ?? "Reconnect it below. Your conversations are kept."}
          </Notice>
        ) : null}
        <section aria-labelledby="pool-title" className="space-y-3">
          <h3 id="pool-title" className="text-sm font-semibold">
            Choose a number from us
          </h3>
          {pool.length ? (
            <>
              <ul className="grid gap-2 sm:grid-cols-2">
                {pool.map((n) => (
                  <li key={n.id}>
                    <label
                      className={cn(
                        "flex cursor-pointer items-start gap-3 rounded-lg border p-3",
                        selected === n.id
                          ? "border-primary bg-primary-soft"
                          : "border-border hover:bg-surface-muted",
                      )}
                    >
                      <input
                        type="radio"
                        name="pool-number"
                        className="sr-only"
                        checked={selected === n.id}
                        onChange={() => setPicked(n.id)}
                      />
                      <Phone
                        className="mt-0.5 size-4 text-primary"
                        aria-hidden
                      />
                      <span className="min-w-0 flex-1">
                        <span className="block font-medium tabular-nums">
                          {n.display_phone_number}
                        </span>
                        <span className="block text-xs text-muted-foreground">
                          {[n.country, n.price_label]
                            .filter(Boolean)
                            .join(" · ") || "Ready to use"}
                        </span>
                      </span>
                      {n.offered_to_you ? (
                        <Badge tone="primary">Offered to you</Badge>
                      ) : null}
                    </label>
                  </li>
                ))}
              </ul>
              <Button
                disabled={!selected}
                loading={choose.isPending}
                onClick={() => selected && choose.mutate(selected)}
              >
                Use this number
              </Button>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">
              No numbers are ready right now. The Pi team can add one for you,
              or connect your own number below.
            </p>
          )}
        </section>
        <section
          aria-labelledby="own-title"
          className="space-y-2 border-t border-border pt-4"
        >
          <h3 id="own-title" className="text-sm font-semibold">
            Use my own number
          </h3>
          <p className="text-sm text-muted-foreground">
            Sign in with Facebook/Meta on Kapso&apos;s secure page to confirm
            you own the number. You can keep the WhatsApp Business app on your
            phone.
          </p>
          {c.status === "setup_pending" && c.setup_url ? (
            <Button asChild variant="secondary">
              <a href={c.setup_url}>
                Continue connecting <ExternalLink aria-hidden />
              </a>
            </Button>
          ) : (
            <Button
              variant="secondary"
              disabled={!s.provider_available}
              loading={setup.isPending}
              onClick={() => setup.mutate(undefined)}
            >
              Connect my own number
            </Button>
          )}
        </section>
      </CardBody>
    </Card>
  );
}

/** Kapso's setup page sends people back here; confirm the number with the provider. */
export function KapsoConnectedPage() {
  const [state, setState] = useState<"checking" | "done" | "failed">(
    "checking",
  );
  const confirm = useScopedMutation(
    () =>
      apiRequest<KapsoStatus["connection"]>(
        "POST",
        "/pi/whatsapp/kapso/confirm",
        null,
        { body: {} },
      ),
    {
      onSuccess: (row) => {
        setState(row.status === "connected" ? "done" : "failed");
        if (row.status === "connected") window.location.replace("/pi/whatsapp");
      },
    },
  );
  const started = useRef(false);
  const run = confirm.mutate;
  useEffect(() => {
    if (started.current || isDemo) return;
    started.current = true;
    run(undefined);
  }, [run]);
  return (
    <div className="mx-auto max-w-lg p-6">
      <Notice
        tone={state === "failed" ? "warning" : "info"}
        title={
          state === "failed"
            ? "Still finishing on WhatsApp's side"
            : "Checking your number…"
        }
      >
        {state === "failed"
          ? "Kapso hasn't confirmed the number yet. Try again in a minute from the WhatsApp page."
          : "One moment while we confirm the connection."}
      </Notice>
    </div>
  );
}
