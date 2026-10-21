"use client";

import { z } from "zod";
import { Download, Receipt } from "lucide-react";
import { formatDateTime, relativeTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/display";
import { useScopedQuery } from "@/hooks/use-scoped";
import { apiRequest } from "@/services/api-client";
import {
  customerFileSchema,
  customerFilesService,
  fileSize,
} from "@/features/customers/files-service";

/** "Receipts": the PDF receipt made for each payment on this invoice. */
export function InvoiceReceipts({ invoiceId }: { invoiceId: string }) {
  const receipts = useScopedQuery(["invoices", invoiceId, "receipts"], () =>
    apiRequest(
      "GET",
      `/billing/invoices/${invoiceId}/receipts`,
      z.array(customerFileSchema),
    ),
  );
  if (receipts.isError || !receipts.data?.length) return null;
  return (
    <Card>
      <CardHeader
        title="Receipts"
        icon={<Receipt />}
        description="One for each payment, also sent to the customer"
      />
      <CardBody>
        <ul className="divide-y divide-border">
          {receipts.data.map((r) => (
            <li
              key={r.id}
              className="flex items-center gap-3 py-2 first:pt-0 last:pb-0"
            >
              <div className="min-w-0 flex-1">
                <a
                  href={customerFilesService.downloadUrl(r.id)}
                  className="block truncate text-[13px] font-medium text-primary hover:underline"
                >
                  {r.name.replace(/\.pdf$/, "")}
                </a>
                <p
                  className="text-xs text-muted-foreground"
                  title={formatDateTime(r.created_at)}
                >
                  {fileSize(r.size)} · {relativeTime(r.created_at)}
                </p>
              </div>
              <Button size="icon-sm" variant="ghost" asChild>
                <a
                  href={customerFilesService.downloadUrl(r.id)}
                  aria-label={`Download ${r.name}`}
                >
                  <Download />
                </a>
              </Button>
            </li>
          ))}
        </ul>
      </CardBody>
    </Card>
  );
}
