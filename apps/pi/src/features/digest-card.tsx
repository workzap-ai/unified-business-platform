"use client";

import { useQuery } from "@tanstack/react-query";
import { CalendarDays } from "lucide-react";
import * as React from "react";

import { Card, CardSection, Switch } from "@/components/ui";
import { get, put } from "@/lib/api";
import { date } from "@/lib/format";
import { useAction, useBusinessKey, useCan } from "@/lib/session";

interface Digest {
  id: string;
  period_start: string;
  period_end: string;
  text: string;
  delivery: { email?: string };
}

const EMAIL_NOTE: Record<string, string> = {
  queued: "Emailed to you.",
  integration_not_configured:
    "Not emailed: no email service is connected for your business yet.",
  no_owner: "Not emailed: no owner email address.",
};

/** Last week's summary on Home, with the owner's "email me" switch. */
export function DigestCard() {
  const key = useBusinessKey();
  const can = useCan();
  const allowed = can("pi.analytics.read");
  const list = useQuery({
    queryKey: key(["digests"]),
    queryFn: () => get<Digest[]>("/digests"),
    enabled: allowed,
  });
  const settings = useQuery({
    queryKey: key(["digest-settings"]),
    queryFn: () => get<{ email: boolean }>("/digests/settings"),
    enabled: allowed,
  });
  const save = useAction(
    (email: boolean) => put<{ email: boolean }>("/digests/settings", { email }),
    {
      invalidate: [["digest-settings"]],
      success: (r) =>
        r.email
          ? "You'll get this summary by email every Monday."
          : "Email summaries turned off.",
    },
  );
  if (!allowed) return null;
  const latest = list.data?.[0];
  return (
    <Card>
      <CardSection className="space-y-3">
        <h2 className="flex items-center gap-2 font-semibold">
          <CalendarDays className="size-4 text-accent" aria-hidden /> Your week
          with Pi
        </h2>
        {latest ? (
          <>
            <p className="text-xs text-muted-foreground">
              {date(latest.period_start)} to {date(latest.period_end)}
            </p>
            <p className="whitespace-pre-line text-sm" data-user-text>
              {latest.text}
            </p>
            {latest.delivery.email ? (
              <p className="text-xs text-muted-foreground">
                {EMAIL_NOTE[latest.delivery.email] ?? ""}
              </p>
            ) : null}
          </>
        ) : (
          <p className="text-sm text-muted-foreground">
            Every Monday morning Pi sums up your week here: customers, replies,
            bookings and payments.
          </p>
        )}
        {can("pi.settings.manage") && settings.data ? (
          <div className="flex items-center justify-between gap-3 border-t border-border pt-3">
            <span className="text-sm">Also email it to me</span>
            <Switch
              id="digest-email"
              label="Email me the weekly summary"
              checked={settings.data.email}
              disabled={save.isPending}
              onCheckedChange={(v) => save.mutate(v)}
            />
          </div>
        ) : null}
      </CardSection>
    </Card>
  );
}
