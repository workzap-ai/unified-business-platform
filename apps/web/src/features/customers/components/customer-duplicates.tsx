"use client";

import { useState } from "react";
import { z } from "zod";
import { Users } from "lucide-react";
import { apiRequest } from "@/services/api-client";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/display";
import { ConfirmDialog } from "@/components/app/forms";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";

/** Backend: apps/api/app/modules/customers/merge.py. */
const duplicateSchema = z.object({
  customer: z.object({
    id: z.string(),
    name: z.string(),
    company: z.string().nullable(),
    phone: z.string().nullable(),
    email: z.string().nullable(),
    source: z.string(),
  }),
  reason: z.string(),
});
type Duplicate = z.infer<typeof duplicateSchema>;

/** "This may be the same person": other records that look like this customer, each
 * with a Merge button that moves everything into this one. Hidden when there are none. */
export function CustomerDuplicates({
  customerId,
  name,
}: {
  customerId: string;
  name: string;
}) {
  const { can } = useSession();
  const [merging, setMerging] = useState<Duplicate | null>(null);
  const found = useScopedQuery(["customers", customerId, "duplicates"], () =>
    apiRequest(
      "GET",
      `/customers/${customerId}/duplicates`,
      z.array(duplicateSchema),
    ),
  );
  const merge = useScopedMutation(
    (duplicateId: string) =>
      apiRequest("POST", `/customers/${customerId}/merge`, z.unknown(), {
        body: { duplicate_id: duplicateId },
      }),
    {
      invalidate: [["customers"], ["pi"], ["orders"], ["quotes"], ["invoices"]],
      success: "Customers merged into one",
      onSuccess: () => setMerging(null),
    },
  );
  const items = found.data ?? [];
  if (!items.length) return null;
  return (
    <Card className="border-warning/40">
      <CardHeader
        title="This may be the same person"
        description="Merge to keep one record: chats, deals, proposals, invoices and notes all move here."
      />
      <CardBody className="space-y-2">
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
                <p className="truncate text-sm font-medium">
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
            {can("customers.write") && (
              <Button size="sm" onClick={() => setMerging(d)}>
                Merge into {name}
              </Button>
            )}
          </div>
        ))}
      </CardBody>
      <ConfirmDialog
        open={merging !== null}
        onOpenChange={(open) => !merge.isPending && !open && setMerging(null)}
        title={`Merge ${merging?.customer.name ?? ""} into ${name}?`}
        description="One customer record remains. Fields this record is missing (company, email) are filled in from the other."
        consequences={[
          `${merging?.customer.name ?? "The other record"}'s chats, deals, proposals, orders, invoices, notes and files move to ${name}.`,
          `${merging?.customer.name ?? "The other record"} is then removed.`,
        ]}
        confirmLabel="Merge"
        loading={merge.isPending}
        onConfirm={() => merging && merge.mutate(merging.customer.id)}
      />
    </Card>
  );
}
