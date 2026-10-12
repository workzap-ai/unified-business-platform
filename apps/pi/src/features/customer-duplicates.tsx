"use client";

/** "This may be the same person": other customer records that look like this one, with
 * a Merge button that moves everything (chats, deals, proposals, invoices, notes) into
 * this customer and removes the other. Backend: apps/api/app/modules/customers/merge.py. */

import { useQuery } from "@tanstack/react-query";
import { Users } from "lucide-react";
import * as React from "react";
import { Button, Card, CardSection } from "@/components/ui";
import { get, post } from "@/lib/api";
import { useAction, useBusinessKey, useCan } from "@/lib/session";

type Duplicate = {
  customer: {
    id: string;
    name: string;
    company: string | null;
    phone: string | null;
    email: string | null;
    source: string;
  };
  reason: string;
};

export function CustomerDuplicates({ id, name }: { id: string; name: string }) {
  const key = useBusinessKey();
  const can = useCan();
  const [confirming, setConfirming] = React.useState<string | null>(null);
  const query = useQuery({
    queryKey: key(["customer-duplicates", id]),
    queryFn: () => get<Duplicate[]>(`/customers/${id}/duplicates`),
  });
  const merge = useAction(
    (duplicateId: string) =>
      post<unknown>(`/customers/${id}/merge`, { duplicate_id: duplicateId }),
    {
      invalidate: [["customer-duplicates", id], ["customers"], ["profile", id]],
      success: "Merged into one customer",
      onSuccess: () => setConfirming(null),
    },
  );
  const items = query.data ?? [];
  if (!items.length) return null;
  return (
    <Card>
      <CardSection className="space-y-3">
        <div>
          <h2 className="font-semibold">This may be the same person</h2>
          <p className="text-sm text-muted-foreground">
            Merge to keep one record: chats, deals, proposals, invoices and
            notes all move here, and missing details (company, email) are filled
            in.
          </p>
        </div>
        {items.map((d) => (
          <div
            key={d.customer.id}
            className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border px-3 py-2"
          >
            <div className="flex min-w-0 items-center gap-2">
              <Users
                className="size-4 shrink-0 text-muted-foreground"
                aria-hidden="true"
              />
              <div className="min-w-0">
                <p className="truncate text-sm font-medium" data-user-text>
                  {d.customer.name}
                  {d.customer.company ? ` · ${d.customer.company}` : ""}
                </p>
                <p className="text-xs text-muted-foreground">
                  {d.reason} ·{" "}
                  {d.customer.phone || d.customer.email || "no phone or email"}{" "}
                  ·{" "}
                  {d.customer.source === "whatsapp"
                    ? "WhatsApp"
                    : "Added by hand"}
                </p>
              </div>
            </div>
            {can("customers.write") &&
              (confirming === d.customer.id ? (
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={merge.isPending}
                    onClick={() => setConfirming(null)}
                  >
                    Cancel
                  </Button>
                  <Button
                    size="sm"
                    loading={merge.isPending}
                    onClick={() => merge.mutate(d.customer.id)}
                  >
                    Yes, merge
                  </Button>
                </div>
              ) : (
                <Button size="sm" onClick={() => setConfirming(d.customer.id)}>
                  Merge into {name}
                </Button>
              ))}
          </div>
        ))}
      </CardSection>
    </Card>
  );
}
