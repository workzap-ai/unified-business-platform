"use client";

import { Check, Copy, MessageCircle } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { Button, Card, CardSection } from "@/components/ui";

/** wa.me needs the number as digits only, with the country code. */
export function waLink(number: string, text = "Salam") {
  const digits = number.replace(/\D/g, "");
  return `https://wa.me/${digits}?text=${encodeURIComponent(text)}`;
}

/** Shown once a number is connected: open a chat with it and test Pi. */
export function WhatsAppLiveCard({
  number,
  live,
}: {
  number: string;
  /** Pi is launched and answering (otherwise messages wait for the team). */
  live: boolean;
}) {
  const [copied, setCopied] = React.useState(false);
  return (
    <Card className="border-accent/40 bg-accent-soft">
      <CardSection className="space-y-3">
        <div className="flex items-center gap-2">
          <MessageCircle className="size-5 text-accent" aria-hidden />
          <h2 className="font-semibold">
            {live ? "WhatsApp is live" : "Your WhatsApp number is connected"}
          </h2>
        </div>
        <p className="text-sm text-muted-foreground">
          Customers can message{" "}
          <span className="font-medium tabular-nums text-foreground">
            {number}
          </span>{" "}
          now.{" "}
          {live
            ? "Pi answers them. To test it, send “Salam” from a different phone."
            : "Their messages wait in your inbox until you launch Pi."}
        </p>
        <div className="flex flex-wrap gap-2">
          <Button asChild>
            <a href={waLink(number)} target="_blank" rel="noreferrer">
              <MessageCircle className="size-4" aria-hidden />
              Open WhatsApp chat
            </a>
          </Button>
          {!live ? (
            <Button asChild variant="secondary">
              <Link href="/setup">Launch Pi</Link>
            </Button>
          ) : null}
          <Button
            variant="secondary"
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(number);
                setCopied(true);
                window.setTimeout(() => setCopied(false), 2000);
              } catch {
                setCopied(false);
              }
            }}
          >
            {copied ? (
              <Check className="size-4" aria-hidden />
            ) : (
              <Copy className="size-4" aria-hidden />
            )}
            {copied ? "Copied" : "Copy number"}
          </Button>
        </div>
      </CardSection>
    </Card>
  );
}
