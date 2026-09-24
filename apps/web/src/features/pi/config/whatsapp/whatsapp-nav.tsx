"use client";

import { SubNav } from "../shared";

export function WhatsAppNav() {
  return (
    <SubNav
      label="WhatsApp sections"
      items={[
        { href: "/pi/whatsapp", label: "Connection", exact: true },
        { href: "/pi/whatsapp/status", label: "Status" },
        { href: "/pi/whatsapp/events", label: "Events" },
      ]}
    />
  );
}
