"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { CheckCircle2, XCircle } from "lucide-react";
import { Notice } from "@/components/app/states";
import { errorMessage } from "@/services/api-client";
import { useSession } from "./session-provider";
import { authService } from "./service";

export function VerifyEmailForm() {
  const params = useSearchParams();
  const token = params.get("token") ?? "";
  const { session, retry } = useSession();
  const [state, setState] = useState<"checking" | "done" | "error">(
    token ? "checking" : "error",
  );
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    let active = true;
    authService
      .verifyEmail(token)
      .then(() => {
        if (!active) return;
        setState("done");
        retry(); // Clears the "verify your email" banner if this browser is signed in.
      })
      .catch((err) => {
        if (!active) return;
        setState("error");
        setError(errorMessage(err, "This link is invalid or has expired."));
      });
    return () => {
      active = false;
    };
    // Runs once for the token this page loaded with.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">
        Confirm your email
      </h1>
      <div className="mt-6">
        {state === "checking" && (
          <Notice tone="info">Confirming your email address…</Notice>
        )}
        {state === "done" && (
          <Notice tone="success" icon={CheckCircle2}>
            Your email address is confirmed.
          </Notice>
        )}
        {state === "error" && (
          <Notice tone="danger" icon={XCircle}>
            {error ?? "This link is missing its token."}
          </Notice>
        )}
      </div>
      <p className="mt-6 text-center text-sm text-muted-foreground">
        <Link
          href={session ? "/" : "/login"}
          className="font-medium text-primary hover:underline"
        >
          {session ? "Continue to your workspace" : "Go to sign in"}
        </Link>
      </p>
    </div>
  );
}
