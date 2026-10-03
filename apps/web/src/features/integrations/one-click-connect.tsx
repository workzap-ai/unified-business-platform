"use client";

import { useState } from "react";
import { z } from "zod";
import { CalendarDays, Lock, ShoppingBag } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/overlays";
import { FormField } from "@/components/app/forms";
import { InlineError } from "@/components/app/states";
import { ApiError, apiRequest, errorMessage } from "@/services/api-client";
import { integrationsService } from "./service";
import type { IntegrationDefinition } from "./types";

/** Providers connected with one button through the same flow Pi uses, so the one
 * connection serves Owner OS and Pi (bookings, order status) alike. */
export const ONE_CLICK = new Set(["google_calendar", "shopify"]);

const Started = z.object({ authorization_url: z.string().url() });

const COPY: Record<
  string,
  { icon: typeof CalendarDays; title: string; body: string; button: string }
> = {
  google_calendar: {
    icon: CalendarDays,
    title: "Connect Google Calendar",
    body: "You'll sign in with Google and approve access to your calendar. Pi then books customers only into free times and adds the events to your calendar.",
    button: "Continue to Google",
  },
  shopify: {
    icon: ShoppingBag,
    title: "Connect Shopify",
    body: "You'll approve read-only access to orders in your Shopify admin. Pi can then tell customers where their own orders are.",
    button: "Continue to Shopify",
  },
};

function shopDomain(value: string) {
  const v = value
    .trim()
    .toLowerCase()
    .replace(/^https?:\/\//, "")
    .replace(/\/.*$/, "");
  if (!v) return "";
  return v.includes(".") ? v : `${v}.myshopify.com`;
}

export function OneClickConnect({
  definition,
  onClose,
}: {
  definition: IntegrationDefinition;
  onClose: () => void;
}) {
  const copy = COPY[definition.key];
  const shopify = definition.key === "shopify";
  const [shop, setShop] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const Icon = copy.icon;

  async function connect() {
    setError(null);
    setBusy(true);
    try {
      const { authorization_url } = await apiRequest(
        "POST",
        `/pi/connectors/${definition.key}/start`,
        Started,
        { body: shopify ? { shop: shopDomain(shop) } : {} },
      );
      window.location.assign(authorization_url);
    } catch (err) {
      // Without Pi in this workspace, Google falls back to the general flow.
      if (
        !shopify &&
        err instanceof ApiError &&
        [403, 404].includes(err.status)
      ) {
        try {
          const connection = await integrationsService.createConnection({
            integration_key: definition.key,
            display_name: definition.name,
            mode: "production",
            config: {},
            credentials: {},
          });
          const { authorization_url } = await integrationsService.startOAuth(
            connection.id,
          );
          window.location.assign(authorization_url);
          return;
        } catch (inner) {
          setError(errorMessage(inner, "Google couldn't be reached."));
        }
      } else {
        setError(
          errorMessage(err, `${definition.name} couldn't be connected.`),
        );
      }
      setBusy(false);
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && !busy && onClose()}>
      <DialogContent size="md">
        <DialogHeader title={copy.title} description={copy.body} />
        <DialogBody className="space-y-4">
          <div className="flex items-center gap-3 rounded-lg border border-border bg-surface-muted/50 p-3">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary-soft text-primary">
              <Icon className="size-5" aria-hidden="true" />
            </span>
            <p className="text-[13px] text-muted-foreground">
              No keys to copy. You approve access on {definition.provider}
              &apos;s own page and can remove it any time, here or in your{" "}
              {definition.provider} account.
            </p>
          </div>
          {shopify && (
            <FormField
              label="Your store address"
              htmlFor="shop-domain"
              required
              help="For example mystore.myshopify.com"
            >
              <Input
                id="shop-domain"
                autoComplete="off"
                placeholder="mystore.myshopify.com"
                value={shop}
                disabled={busy}
                onChange={(e) => setShop(e.target.value)}
              />
            </FormField>
          )}
          {definition.required_scopes.length > 0 && (
            <div>
              <p className="flex items-center gap-1.5 text-[13px] font-medium">
                <Lock className="size-3.5" aria-hidden="true" />
                Access you&apos;ll approve
              </p>
              <ul className="mt-1.5 list-disc space-y-0.5 pl-5 text-xs text-muted-foreground">
                {definition.required_scopes.map((s) => (
                  <li key={s} className="break-all">
                    {s}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {error && <InlineError message={error} />}
        </DialogBody>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button
            onClick={connect}
            loading={busy}
            disabled={shopify && !shopDomain(shop)}
          >
            {copy.button}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
