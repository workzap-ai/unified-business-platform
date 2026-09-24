"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, Skeleton } from "@/components/ui/display";
import {
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import { EmptyState, ErrorState } from "@/components/app/states";
import { useBreadcrumbs } from "@/components/shell/breadcrumbs";
import { useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import { customersService } from "@/features/customers/service";
import type { QuoteDetail } from "@/features/business/types";
import { DocumentBuilder } from "./document-builder";
import { useQuote } from "./hooks";
import { fromDocumentLines } from "./schema";

function BuilderSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-8 w-80" />
      <Skeleton className="h-64 rounded-xl" />
    </div>
  );
}

/** Reads `?customer=` and resolves it so the builder can start on the Items step. */
function usePrefillCustomer() {
  const params = useSearchParams();
  const { can } = useSession();
  const id = params.get("customer");
  const enabled = Boolean(id) && can("customers.read");
  const query = useScopedQuery(
    ["customers", "detail", id],
    () => customersService.get(id!),
    { enabled, retry: false },
  );
  return {
    loading: enabled && query.isPending,
    customer: enabled && query.data ? query.data : null,
  };
}

export function NewQuotePage() {
  return (
    <RequirePermission permission="quotes.write" area="quote creation">
      <NewDocument kind="quote" />
    </RequirePermission>
  );
}

export function NewOrderPage() {
  return (
    <RequirePermission permission="orders.write" area="order creation">
      <NewDocument kind="order" />
    </RequirePermission>
  );
}

function NewDocument({ kind }: { kind: "quote" | "order" }) {
  const { loading, customer } = usePrefillCustomer();
  return (
    <PageShell width="wide">
      <PageHeader
        title={kind === "quote" ? "New quote" : "New order"}
        description={
          kind === "quote"
            ? "Choose a customer, add items at catalog prices, then review. It's saved as a draft."
            : "Choose a customer and catalog items. It's saved as a draft; confirming it deducts stock."
        }
      />
      {loading ? (
        <BuilderSkeleton />
      ) : (
        <DocumentBuilder
          kind={kind}
          initial={{
            customer: customer
              ? {
                  id: customer.id,
                  name: customer.name,
                  email: customer.email,
                  phone: customer.phone,
                  company: customer.company,
                }
              : null,
            lines: [],
            notes: "",
          }}
        />
      )}
    </PageShell>
  );
}

export function EditQuotePage({ id }: { id: string }) {
  return (
    <RequirePermission permission="quotes.write" area="quote editing">
      <EditQuote id={id} />
    </RequirePermission>
  );
}

function EditQuote({ id }: { id: string }) {
  const quote = useQuote(id);
  useBreadcrumbs(
    quote.data
      ? [{ label: quote.data.number, href: `/quotes/${id}` }, { label: "Edit" }]
      : [{ label: "Quote" }, { label: "Edit" }],
  );
  if (quote.isError) {
    return (
      <PageShell>
        <Card>
          <ErrorState
            error={quote.error}
            onRetry={() => void quote.refetch()}
          />
        </Card>
      </PageShell>
    );
  }
  if (quote.isPending) {
    return (
      <PageShell>
        <BuilderSkeleton />
      </PageShell>
    );
  }
  const q: QuoteDetail = quote.data;
  if (q.status !== "draft") {
    return (
      <PageShell width="narrow">
        <Card>
          <EmptyState
            icon={Lock}
            title={`${q.number} can't be edited`}
            description="Only draft quotes can be edited. Return it to draft first if you need to change lines."
            action={
              <Button size="sm" variant="secondary" asChild>
                <Link href={`/quotes/${q.id}`}>Back to quote</Link>
              </Button>
            }
          />
        </Card>
      </PageShell>
    );
  }
  return (
    <PageShell width="wide">
      <PageHeader
        title={`Edit ${q.number}`}
        description="Update items, validity and notes on this draft."
      />
      <DocumentBuilder
        kind="quote"
        initial={{
          documentId: q.id,
          number: q.number,
          source: q.source,
          currency: q.currency,
          customer: { id: q.customer_id, name: q.customer_name ?? "Customer" },
          lines: fromDocumentLines(q.lines),
          valid_until: q.valid_until,
          notes: q.notes,
        }}
      />
    </PageShell>
  );
}
