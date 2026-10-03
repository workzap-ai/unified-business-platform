"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, UsersRound } from "lucide-react";

import { Card, CardSection, Switch } from "@/components/ui";
import { get, patch } from "@/lib/api";
import { useAction, useBusinessKey, useCan } from "@/lib/session";

type Settings = { whatsapp_config: Record<string, unknown> };

/** Lets the business decide whether its customers can see their own chats in PI Customer. */
export function CustomerPortalCard() {
  const can = useCan();
  const key = useBusinessKey();
  const client = useQueryClient();
  const settings = useQuery({
    queryKey: key(["settings"]),
    queryFn: () => get<Settings>("/pi/settings"),
  });
  const save = useAction(
    (on: boolean) =>
      patch<Settings>("/pi/settings/whatsapp_config", {
        value: { ...settings.data?.whatsapp_config, customer_portal: on },
      }),
    {
      success: (s) =>
        s.whatsapp_config.customer_portal === false
          ? "PI Customer is off for your chats"
          : "Customers can now see their chats in PI Customer",
      onSuccess: (s) => client.setQueryData(key(["settings"]), s),
    },
  );
  if (!settings.data) return null;
  const on = settings.data.whatsapp_config.customer_portal !== false;
  return (
    <Card>
      <CardSection className="space-y-3">
        <div className="flex items-start justify-between gap-4">
          <div className="flex gap-3">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-accent-soft text-accent-soft-foreground">
              <UsersRound className="size-5" aria-hidden />
            </span>
            <div>
              <h2 className="font-semibold">PI Customer</h2>
              <p className="text-sm text-muted-foreground">
                Your customers can sign in with their WhatsApp number to see
                their conversations with you and where each request stands. They
                never see your notes, summaries or team names.
              </p>
            </div>
          </div>
          <Switch
            id="customer-portal"
            label="Let customers see their conversations"
            checked={on}
            disabled={!can("pi.settings.manage") || save.isPending}
            onCheckedChange={(value) => save.mutate(value)}
          />
        </div>
        <a
          href="/customer"
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1.5 text-sm font-medium text-accent"
        >
          Open PI Customer
          <ExternalLink className="size-3.5" aria-hidden />
        </a>
      </CardSection>
    </Card>
  );
}
