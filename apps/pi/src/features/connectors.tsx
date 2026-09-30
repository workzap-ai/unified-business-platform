"use client";

/**
 * Tools → "Your accounts": Google Calendar and Shopify, each authorized by the business
 * itself. The status comes from the server (never assumed); tokens and account ids are
 * never shown. Connecting leaves the app for Google/Shopify and returns to this page.
 */

import { useQuery } from "@tanstack/react-query";
import { CalendarDays, ShoppingBag } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import {
  Badge,
  Button,
  Card,
  CardSection,
  ErrorState,
  Field,
  Input,
  LoadingBlock,
} from "@/components/ui";
import { del, errorText, get, post } from "@/lib/api";
import { date } from "@/lib/format";
import { useAction, useBusinessKey, useCan } from "@/lib/session";

export type Connector = {
  key: "google_calendar" | "shopify";
  name: string;
  description: string;
  available: boolean;
  state: "not_connected" | "connecting" | "connected" | "action_required";
  detail: string;
  health: string;
  last_checked_at: string | null;
  problem: string;
};

const ICON = { google_calendar: CalendarDays, shopify: ShoppingBag };
const RETURNED: Record<string, string> = {
  connected: "is connected. Pi will use it from now on.",
  failed: "wasn't connected. Nothing was changed; you can try again.",
};

export function useConnectors() {
  const key = useBusinessKey();
  const can = useCan();
  return useQuery({
    queryKey: key(["connectors"]),
    queryFn: () => get<Connector[]>("/pi/connectors"),
    enabled: can("integrations.read"),
  });
}

/** Shows the result of the Google/Shopify redirect once, then cleans the address bar. */
function useReturnNotice(items: Connector[] | undefined) {
  React.useEffect(() => {
    if (!items) return;
    const params = new URLSearchParams(window.location.search);
    let changed = false;
    for (const item of items) {
      const outcome = params.get(item.key);
      if (!outcome || !(outcome in RETURNED)) continue;
      const text = `${item.name} ${RETURNED[outcome]}`;
      if (outcome === "connected") toast.success(text);
      else toast.error(text);
      params.delete(item.key);
      changed = true;
    }
    if (changed) {
      const query = params.toString();
      window.history.replaceState(
        null,
        "",
        window.location.pathname + (query ? `?${query}` : ""),
      );
    }
  }, [items]);
}

function StateBadge({ item }: { item: Connector }) {
  if (!item.available) return <Badge>Not available yet</Badge>;
  if (item.state === "connected")
    return <Badge tone="success">Connected</Badge>;
  if (item.state === "action_required")
    return <Badge tone="warning">Needs attention</Badge>;
  if (item.state === "connecting")
    return <Badge tone="info">Not finished</Badge>;
  return <Badge>Not connected</Badge>;
}

function ConnectorCard({ item }: { item: Connector }) {
  const can = useCan();
  const manage = can("integrations.manage");
  const [shop, setShop] = React.useState(item.detail);
  const [confirming, setConfirming] = React.useState(false);
  const Icon = ICON[item.key];
  const connect = useAction(
    () =>
      post<{ authorization_url: string }>(
        `/pi/connectors/${item.key}/start`,
        item.key === "shopify" ? { shop } : undefined,
      ),
    {
      // Leave for the provider's consent screen; it returns to this page.
      onSuccess: (result) => window.location.assign(result.authorization_url),
    },
  );
  const test = useAction(
    () =>
      post<{ ok: boolean; message: string }>(`/pi/connectors/${item.key}/test`),
    { invalidate: [["connectors"]] },
  );
  const disconnect = useAction(() => del(`/pi/connectors/${item.key}`), {
    invalidate: [["connectors"]],
    success: `${item.name} disconnected`,
    onSuccess: () => setConfirming(false),
  });
  const result = test.data;
  const connected = item.state === "connected";
  const shopValid = /^[a-z0-9][a-z0-9-]*\.myshopify\.com$/i.test(shop.trim());

  return (
    <Card>
      <CardSection className="space-y-3">
        <div className="flex items-center gap-2">
          <Icon className="size-5 text-accent" aria-hidden />
          <h3 className="font-semibold">{item.name}</h3>
          <span className="ms-auto">
            <StateBadge item={item} />
          </span>
        </div>
        <p className="text-sm text-muted-foreground">{item.description}</p>
        {!item.available ? (
          <p className="text-sm text-muted-foreground">
            {item.name} can&apos;t be connected on this Pi server yet. Pi keeps
            working without it
            {item.key === "google_calendar"
              ? " and offers times from your working hours."
              : " and hands store questions to your team."}
          </p>
        ) : null}
        {item.available && connected && item.detail ? (
          <p className="text-sm">
            Store: <span className="font-medium">{item.detail}</span>
          </p>
        ) : null}
        {item.available && item.state === "action_required" ? (
          <p className="text-sm text-warning" role="status">
            {item.problem ||
              "This connection stopped working. Reconnect it to continue."}
          </p>
        ) : null}
        {connected && item.last_checked_at ? (
          <p className="text-xs text-muted-foreground">
            Last checked {date(item.last_checked_at)}
          </p>
        ) : null}
        {result ? (
          <p
            className={
              result.ok ? "text-sm text-success" : "text-sm text-warning"
            }
            role="status"
          >
            {result.ok ? "Connection works." : result.message}
          </p>
        ) : null}

        {item.available && manage ? (
          <div className="space-y-3">
            {item.key === "shopify" && !connected ? (
              <Field
                label="Your store address"
                htmlFor="shopify-shop"
                hint="Find it in Shopify under Settings → Domains, e.g. your-store.myshopify.com"
              >
                <Input
                  id="shopify-shop"
                  value={shop}
                  onChange={(e) => setShop(e.target.value)}
                  placeholder="your-store.myshopify.com"
                  autoComplete="off"
                  inputMode="url"
                  maxLength={200}
                />
              </Field>
            ) : null}
            <div className="flex flex-wrap gap-2">
              {!connected ? (
                <Button
                  loading={connect.isPending}
                  disabled={item.key === "shopify" && !shopValid}
                  onClick={() => connect.mutate(undefined)}
                >
                  {item.state === "not_connected"
                    ? `Connect ${item.name}`
                    : "Reconnect"}
                </Button>
              ) : (
                <Button
                  variant="secondary"
                  loading={test.isPending}
                  onClick={() => test.mutate(undefined)}
                >
                  Test connection
                </Button>
              )}
              {item.state !== "not_connected" && !confirming ? (
                <Button variant="ghost" onClick={() => setConfirming(true)}>
                  Disconnect
                </Button>
              ) : null}
            </div>
            {confirming ? (
              <div
                className="space-y-2 rounded-lg border border-border p-3 text-sm"
                role="group"
                aria-label={`Disconnect ${item.name}`}
              >
                <p>
                  Pi will stop using {item.name}.{" "}
                  {item.key === "shopify"
                    ? "To remove access completely, also uninstall the app in your Shopify admin."
                    : "Existing calendar events stay in your calendar."}
                </p>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="danger"
                    loading={disconnect.isPending}
                    onClick={() => disconnect.mutate(undefined)}
                  >
                    Disconnect
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setConfirming(false)}
                  >
                    Keep connected
                  </Button>
                </div>
              </div>
            ) : null}
          </div>
        ) : item.available && !manage ? (
          <p className="text-xs text-muted-foreground">
            Ask the business owner or an admin to change this connection.
          </p>
        ) : null}
      </CardSection>
    </Card>
  );
}

export function ConnectorsSection() {
  const can = useCan();
  const connectors = useConnectors();
  useReturnNotice(connectors.data);
  if (!can("integrations.read")) return null;
  return (
    <section className="space-y-3 md:col-span-2" aria-labelledby="accounts">
      <div>
        <h2 id="accounts" className="font-semibold">
          Your accounts
        </h2>
        <p className="text-sm text-muted-foreground">
          Connect your own calendar and store. Each account is authorized by
          you, and you can disconnect it at any time.
        </p>
      </div>
      {connectors.isPending ? (
        <LoadingBlock rows={2} />
      ) : connectors.isError ? (
        <ErrorState
          message={errorText(connectors.error)}
          onRetry={() => connectors.refetch()}
        />
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {connectors.data.map((item) => (
            <ConnectorCard key={item.key} item={item} />
          ))}
        </div>
      )}
    </section>
  );
}
