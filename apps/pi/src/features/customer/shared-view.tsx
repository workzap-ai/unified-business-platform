"use client";

import { useQuery } from "@tanstack/react-query";
import { Eye } from "lucide-react";

import { errorText } from "@/lib/api";
import { customerGet, type SharedView } from "@/lib/customer-api";
import { cn } from "@/lib/cn";
import { Badge, Card, ErrorState, Skeleton } from "@/components/ui";
import { Avatar, CATEGORY, STAGE, TURN, shortDay } from "./shared";

/** What a forwarded link shows: requests, whose turn and next steps. Never the chat,
 * files, prices or the customer's number. */
export function SharedRequests({ token }: { token: string }) {
  const view = useQuery({
    queryKey: ["pi-customer", "shared", token],
    queryFn: () =>
      customerGet<SharedView>(`/shared/${encodeURIComponent(token)}`),
    retry: false,
  });
  if (view.isPending)
    return (
      <div
        className="mx-auto max-w-3xl space-y-3"
        role="status"
        aria-label="Loading"
      >
        <Skeleton className="h-16 w-full rounded-2xl" />
        <Skeleton className="h-40 w-full rounded-2xl" />
      </div>
    );
  if (view.isError)
    return (
      <div className="mx-auto max-w-xl">
        <ErrorState message={errorText(view.error)} />
      </div>
    );
  const data = view.data;
  return (
    <div className="mx-auto w-full max-w-3xl space-y-5">
      <Card className="flex items-start gap-3 p-4 sm:p-5">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-accent-soft text-accent-soft-foreground">
          <Eye className="size-4" aria-hidden />
        </span>
        <div>
          <h1 className="text-lg font-semibold">Shared requests</h1>
          <p className="text-sm text-muted-foreground">
            View only: requests and next steps, without the chat. This link
            stops working on {shortDay(data.expires_at)}.
          </p>
        </div>
      </Card>
      {data.businesses.length === 0 ? (
        <Card className="p-5 text-sm text-muted-foreground">
          No requests to show yet.
        </Card>
      ) : (
        data.businesses.map((b) => (
          <section key={b.business} className="space-y-2.5">
            <h2 className="flex items-center gap-2.5 font-semibold">
              <Avatar name={b.business} />
              {b.business}
            </h2>
            <ul className="space-y-2.5">
              {b.issues.map((issue, i) => {
                const stage = STAGE[issue.stage];
                const Icon = CATEGORY[issue.category].icon;
                const turn = ["live", "closed", "paused"].includes(issue.stage)
                  ? "done"
                  : issue.waiting_on_other_until
                    ? "other"
                    : issue.ball_with === "client"
                      ? "you"
                      : "us";
                const next =
                  turn === "you" && issue.open_question
                    ? issue.open_question
                    : turn === "us" && issue.next_update_by
                      ? `${issue.next_step} Update by ${shortDay(issue.next_update_by)}.`
                      : issue.next_step;
                return (
                  <li
                    key={i}
                    className={cn(
                      "rounded-2xl border border-border border-l-4 bg-surface p-3.5 sm:p-4",
                      stage.bar,
                    )}
                  >
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Icon
                        className="size-4 text-muted-foreground"
                        aria-hidden
                      />
                      <p className="font-semibold">{issue.title}</p>
                      <Badge tone={stage.tone}>
                        <span
                          className={cn("size-2 rounded-full", stage.dot)}
                          aria-hidden
                        />
                        {stage.en}
                      </Badge>
                      <Badge tone={TURN[turn].tone}>{TURN[turn].en}</Badge>
                    </div>
                    {issue.summary && (
                      <p className="mt-1.5 text-sm text-foreground-secondary">
                        {issue.summary}
                      </p>
                    )}
                    {next && turn !== "done" && (
                      <p className="mt-2 rounded-lg bg-surface-muted px-3 py-2 text-[13px]">
                        <span className="font-medium">Next: </span>
                        {next}
                      </p>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        ))
      )}
    </div>
  );
}
