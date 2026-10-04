"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { PI } from "@/features/pi/config";
import { track } from "@/features/pi/track";
import "./pi-launcher.css";

// The contact route on every Workzap site (owner decision, 4 Oct 2026): a pi button that
// follows the visitor down the page. It uses the official Lilac-on-Ink pi face on an Ink
// pill, carries the AI label, and opens the same start page as every other pi button
// (on a phone with a number set, WhatsApp opens directly).
function waUrl(): string | null {
  if (!PI.whatsappNumber) return null;
  return `https://wa.me/${PI.whatsappNumber}?text=${encodeURIComponent(PI.whatsappText)}`;
}

export function PiLauncher() {
  const pathname = usePathname();
  // The start page already is the contact page.
  if (pathname.startsWith(`${PI.base}/talk-to-pi`)) return null;
  return (
    <Link
      href={`${PI.base}/talk-to-pi`}
      className="pil"
      aria-label="Talk to pi, Workzap’s AI assistant, on WhatsApp"
      onClick={(e) => {
        track("click_chat_cta", { page: pathname, pos: "launcher" });
        const target = waUrl();
        if (target && /android|iphone|ipad|ipod/i.test(navigator.userAgent)) {
          e.preventDefault();
          window.location.href = target;
        }
      }}
    >
      <Image
        className="pil-face"
        src="/pi-brand/pi-greet-dark.svg"
        alt=""
        width={44}
        height={44}
        unoptimized
        loading="eager"
      />
      <span className="pil-text">Talk to pi</span>
      <span className="pil-ai" aria-hidden="true">
        AI
      </span>
    </Link>
  );
}
