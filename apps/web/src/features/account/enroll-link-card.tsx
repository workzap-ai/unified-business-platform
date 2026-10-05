"use client";

import { useState } from "react";
import { Copy, Link2, MessageCircle, Users } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/display";
import { Notice } from "@/components/app/states";
import { isDemo } from "@/lib/data-mode";
import { apiRequest, errorMessage } from "@/services/api-client";

/**
 * Add someone else's face or phone lock to this account: a one-time link (30 minutes)
 * that asks only for this account's email and password, then scans their face or uses
 * their phone's fingerprint.
 */
export function EnrollLinkCard() {
  const [link, setLink] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function create() {
    setBusy(true);
    try {
      const made = await apiRequest<{ link: string }>(
        "POST",
        "/auth/enroll-links",
        null,
        { body: {} },
      );
      setLink(made.link);
    } catch (e) {
      toast.error(errorMessage(e, "Couldn't make the link"));
    } finally {
      setBusy(false);
    }
  }

  const message = link
    ? `Open this link to add your face or phone lock to our Owner OS account (works once, for 30 minutes): ${link}`
    : "";

  return (
    <Card>
      <CardHeader
        title="Add someone else, or another phone"
        description="Make a one-time link. Whoever opens it enters this account's email and password, then scans their face or uses their phone's fingerprint."
      />
      <CardBody className="space-y-3">
        {isDemo ? (
          <Notice tone="info">Links need a live API connection.</Notice>
        ) : link ? (
          <>
            <div className="flex min-w-0 items-center gap-2 rounded-lg border border-border bg-surface-muted px-3 py-2">
              <Link2
                className="size-4 shrink-0 text-muted-foreground"
                aria-hidden
              />
              <code className="min-w-0 flex-1 truncate text-[12px]">
                {link}
              </code>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                variant="secondary"
                onClick={() =>
                  void navigator.clipboard
                    .writeText(link)
                    .then(() => toast.success("Link copied"))
                }
              >
                <Copy aria-hidden /> Copy link
              </Button>
              <Button variant="secondary" asChild>
                <a
                  href={`https://wa.me/?text=${encodeURIComponent(message)}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  <MessageCircle aria-hidden /> Share on WhatsApp
                </a>
              </Button>
              <Button
                variant="ghost"
                onClick={() => void create()}
                loading={busy}
              >
                New link
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Works once and for 30 minutes. Only share it with someone you
              trust: they will be able to sign in to this account.
            </p>
          </>
        ) : (
          <Button onClick={() => void create()} loading={busy}>
            <Users aria-hidden /> Make a link
          </Button>
        )}
      </CardBody>
    </Card>
  );
}
