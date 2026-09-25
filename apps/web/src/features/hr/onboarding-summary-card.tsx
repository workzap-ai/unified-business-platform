"use client";

import Link from "next/link";
import { ChevronRight, Link2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, Skeleton } from "@/components/ui/display";
import { StatusBadge } from "@/components/app/status-badge";
import { useScopedQuery } from "@/hooks/use-scoped";
import { formatDay } from "@/features/billing/utils";
import { onboardingService } from "./onboarding-service";

/** HR overview: submissions waiting for review and links still out with employees. */
export function OnboardingSummaryCard() {
  const submitted = useScopedQuery(
    ["onboarding", { status: "submitted", pageSize: 5 }],
    () => onboardingService.list({ status: "submitted", pageSize: 5 }),
  );
  const pending = useScopedQuery(
    ["onboarding", { status: "pending", pageSize: 1 }],
    () => onboardingService.list({ status: "pending", pageSize: 1 }),
  );
  const waiting = submitted.data?.total ?? 0;
  return (
    <Card className="mb-4">
      <CardHeader
        title="Onboarding"
        description={
          submitted.isPending || pending.isPending
            ? "Loading…"
            : `${waiting} ready for review · ${pending.data?.total ?? 0} waiting for the employee`
        }
        icon={<Link2 />}
        actions={
          <Button variant="secondary" size="sm" asChild>
            <Link href="/hr/onboarding?create=1">Send link</Link>
          </Button>
        }
      />
      <div className="px-4 pb-3">
        {submitted.isPending ? (
          <Skeleton className="h-10 w-full" />
        ) : waiting === 0 ? (
          <p className="text-[13px] text-muted-foreground">
            Nothing to review. Share an onboarding link with a new employee to
            collect their CNIC, contact, emergency and bank details.
          </p>
        ) : (
          <ul className="divide-y divide-border">
            {submitted.data?.items.map((o) => (
              <li key={o.id}>
                <Link
                  href={`/hr/onboarding/${o.id}`}
                  className="flex items-center gap-3 py-2 hover:text-primary"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">
                      {o.full_name}
                    </span>
                    <span className="block truncate text-xs text-muted-foreground">
                      {o.designation}
                      {o.date_of_joining
                        ? ` · joins ${formatDay(o.date_of_joining)}`
                        : ""}
                    </span>
                  </span>
                  <StatusBadge status="submitted" label="Review" />
                  <ChevronRight
                    className="size-4 text-muted-foreground"
                    aria-hidden="true"
                  />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}
