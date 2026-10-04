"use client";

import Link from "next/link";
import { useEffect } from "react";
import type { ReactNode } from "react";
import { PI } from "./config";
import { track } from "./track";

function waUrl(): string | null {
  if (!PI.whatsappNumber) return null;
  return `https://wa.me/${PI.whatsappNumber}?text=${encodeURIComponent(PI.whatsappText)}`;
}

function isPhone(): boolean {
  return /android|iphone|ipad|ipod/i.test(navigator.userAgent);
}

/**
 * The one WhatsApp button used everywhere. On a phone it opens WhatsApp with
 * "Hi pi" ready to send; on a computer it opens the start page with the QR code.
 */
export function WhatsAppButton({
  pos,
  page,
  label = "Chat with pi on WhatsApp",
  variant = "primary",
  openDirect = false,
}: {
  pos: string;
  page: string;
  label?: string;
  variant?: "primary" | "secondary";
  openDirect?: boolean;
}) {
  return (
    <Link
      className={`pi-btn pi-btn-${variant}`}
      href={`${PI.base}/talk-to-pi`}
      onClick={(e) => {
        track(openDirect ? "open_whatsapp" : "click_chat_cta", { page, pos });
        const target = waUrl();
        if (target && isPhone()) {
          e.preventDefault();
          window.location.href = target;
        }
      }}
    >
      {label}
    </Link>
  );
}

export function TrackOnMount({ name, page }: { name: string; page: string }) {
  useEffect(() => {
    track(name, { page });
  }, [name, page]);
  return null;
}

export function FaqItem({
  question,
  children,
}: {
  question: string;
  children: ReactNode;
}) {
  return (
    <details
      className="pi-faq-item"
      onToggle={(e) => {
        if ((e.currentTarget as HTMLDetailsElement).open)
          track("faq_open", { question });
      }}
    >
      <summary>
        <h3>{question}</h3>
      </summary>
      <div className="pi-faq-answer">{children}</div>
    </details>
  );
}

export function TrackedLink({
  href,
  event,
  page,
  className,
  children,
}: {
  href: string;
  event: string;
  page: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Link
      href={href}
      className={className}
      onClick={() => track(event, { page })}
    >
      {children}
    </Link>
  );
}
