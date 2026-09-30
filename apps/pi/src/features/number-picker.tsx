"use client";

import { useQuery } from "@tanstack/react-query";
import { Phone } from "lucide-react";
import * as React from "react";

import { Badge, Button, LoadingBlock, Notice } from "@/components/ui";
import { errorText, get, post } from "@/lib/api";
import { useAction, useBusinessKey } from "@/lib/session";

export interface PoolNumber {
  id: string;
  display_phone_number: string;
  country: string;
  price_label: string;
  coexistence: boolean;
  display_name_status: string;
  offered_to_you: boolean;
  held_until?: string | null;
}

/**
 * Numbers from the platform's pool. Choosing one connects it at once; an operator may
 * also have set one aside for this business ("Offered to you").
 */
export function PoolNumberPicker({
  environment = "production",
  onChosen,
  fallback,
}: {
  environment?: "production" | "test";
  onChosen?: () => void;
  fallback?: React.ReactNode;
}) {
  const key = useBusinessKey();
  const [picked, setPicked] = React.useState<string | null>(null);
  const numbers = useQuery({
    queryKey: key(["pool-numbers", environment]),
    queryFn: () =>
      get<PoolNumber[]>(`/whatsapp/numbers?environment=${environment}`),
  });
  const choose = useAction(
    (id: string) =>
      post<{ state: "connected" | "held" }>(`/whatsapp/numbers/${id}/choose`, {
        environment,
      }),
    {
      invalidate: [
        ["whatsapp"],
        ["account"],
        ["pool-numbers"],
        ["whatsapp-access"],
        ["notifications"],
      ],
      success: (result) =>
        result.state === "held"
          ? "Number held for you. It connects once your business is approved and your plan is active."
          : "Your WhatsApp number is connected.",
      onSuccess: (result) => {
        if (result.state === "connected") onChosen?.();
      },
    },
  );
  if (numbers.isPending) return <LoadingBlock rows={2} />;
  if (numbers.isError)
    return <Notice tone="danger">{errorText(numbers.error)}</Notice>;
  if (!numbers.data.length) {
    return (
      <div className="space-y-3">
        <Notice tone="info" title="No numbers ready right now">
          We&apos;re adding more numbers. Request one below and we&apos;ll show
          you the price before anything is bought.
        </Notice>
        {fallback}
      </div>
    );
  }
  const selected =
    picked ??
    numbers.data.find((n) => n.held_until)?.id ??
    numbers.data.find((n) => n.offered_to_you)?.id;
  return (
    <div className="space-y-3">
      <ul className="grid gap-2 sm:grid-cols-2" aria-label="Available numbers">
        {numbers.data.map((n) => (
          <li key={n.id}>
            <label
              className={
                "flex cursor-pointer items-start gap-3 rounded-lg border p-3 has-focus-visible:outline-2 has-focus-visible:outline-ring " +
                (selected === n.id
                  ? "border-accent bg-accent-soft"
                  : "border-border bg-surface hover:bg-surface-muted")
              }
            >
              <input
                type="radio"
                name="pool-number"
                className="sr-only"
                checked={selected === n.id}
                onChange={() => setPicked(n.id)}
              />
              <Phone className="mt-0.5 size-4 text-accent" aria-hidden />
              <span className="min-w-0 flex-1">
                <span className="block font-medium tabular-nums">
                  {n.display_phone_number}
                </span>
                <span className="block text-xs text-muted-foreground">
                  {[n.country, n.price_label].filter(Boolean).join(" · ") ||
                    "Ready to use"}
                </span>
              </span>
              {n.held_until ? (
                <Badge tone="accent">Held for you</Badge>
              ) : n.offered_to_you ? (
                <Badge tone="accent">Offered to you</Badge>
              ) : null}
            </label>
          </li>
        ))}
      </ul>
      <p className="text-xs text-muted-foreground">
        The number is provided and paid for by us (WhatsApp fees are included in
        your plan). Meta reviews the display name shown to your customers.
      </p>
      <Button
        disabled={!selected}
        loading={choose.isPending}
        onClick={() => selected && choose.mutate(selected)}
      >
        Use this number
      </Button>
    </div>
  );
}
