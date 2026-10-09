import { CircleCheck, CircleX, Lock } from "lucide-react";

import { Wordmark } from "@/components/brand";
import { Card, CardSection } from "@/components/ui";

export const metadata = { title: "Payment" };

/**
 * Where Stripe Checkout sends the customer back. "?payment=returned" means they
 * finished paying; without it they cancelled. The invoice itself is updated by
 * Stripe's verified webhook, never by this page.
 */
export default async function Page(props: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await props.searchParams;
  const paid = params.payment === "returned";
  const invoice = typeof params.invoice === "string" ? params.invoice : "";
  return (
    <div className="mx-auto flex min-h-dvh max-w-md flex-col gap-6 px-4 py-10 sm:py-14">
      <div className="flex items-center justify-between">
        <Wordmark className="text-xl" />
        <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
          <Lock className="size-3.5" aria-hidden />
          Secure payment
        </span>
      </div>
      <Card>
        <CardSection className="space-y-3 text-center">
          {paid ? (
            <CircleCheck className="mx-auto size-10 text-success" aria-hidden />
          ) : (
            <CircleX
              className="mx-auto size-10 text-muted-foreground"
              aria-hidden
            />
          )}
          <h1 className="text-lg font-semibold">
            {paid ? "Thank you, payment received" : "Payment not completed"}
          </h1>
          <p className="text-sm text-muted-foreground">
            {paid
              ? `Your payment${invoice ? ` for invoice ${invoice}` : ""} went through. The business gets confirmation automatically. You can close this page.`
              : "Nothing was charged. Open the payment link again whenever you're ready."}
          </p>
        </CardSection>
      </Card>
    </div>
  );
}
