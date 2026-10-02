"use client";

import { useState } from "react";
import { MailWarning } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/services/api-client";
import { useSession } from "./session-provider";
import { authService } from "./service";

export function VerifyEmailBanner() {
  const { session } = useSession();
  const [state, setState] = useState<"idle" | "sending" | "sent">("idle");
  const [error, setError] = useState<string | null>(null);
  const [dismissed, setDismissed] = useState(false);
  if (!session || session.user.email_verified || dismissed) return null;

  async function resend() {
    setState("sending");
    setError(null);
    try {
      await authService.resendVerification();
      setState("sent");
    } catch (err) {
      setState("idle");
      setError(errorMessage(err, "Couldn't send it. Try again shortly."));
    }
  }

  return (
    <div className="flex items-center gap-2 border-b border-warning/25 bg-warning-soft px-3 py-2 text-[13px] text-warning sm:px-5">
      <MailWarning className="size-4 shrink-0" aria-hidden="true" />
      <span className="min-w-0 flex-1 truncate">
        {state === "sent"
          ? `We sent a new link to ${session.user.email}.`
          : `Confirm your email address (${session.user.email}) to secure your account.`}
      </span>
      {state !== "sent" && (
        <Button
          variant="ghost"
          size="sm"
          className="h-6 shrink-0 px-2 text-warning hover:bg-warning/15 hover:text-warning"
          onClick={resend}
          loading={state === "sending"}
        >
          Resend email
        </Button>
      )}
      {error && <span className="shrink-0 text-xs">{error}</span>}
      <button
        type="button"
        className="shrink-0 text-xs font-medium underline-offset-2 hover:underline"
        onClick={() => setDismissed(true)}
      >
        Dismiss
      </button>
    </div>
  );
}
