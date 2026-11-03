import { NextResponse } from "next/server";

// A meeting request from /nori/talk. It is checked here, then passed to the webhook in
// BOOKING_WEBHOOK_URL when one is set (a Google Apps Script or similar that writes the
// request to a sheet and emails the team). Until the Talk mailbox and that webhook exist,
// nothing is stored on the server, so the page tells the visitor to confirm on WhatsApp.
export const dynamic = "force-dynamic";

const cap = (v: unknown, n: number) => (typeof v === "string" ? v.trim().slice(0, n) : "");

export async function POST(req: Request) {
  let body: Record<string, unknown>;
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ ok: false }, { status: 400 });
  }
  // A hidden field real visitors never fill in.
  if (cap(body.website, 100)) return NextResponse.json({ ok: true, delivered: true });

  const entry = {
    name: cap(body.name, 120),
    business: cap(body.business, 160),
    role: cap(body.role, 60),
    shops: cap(body.shops, 30),
    phone: cap(body.phone, 30),
    email: cap(body.email, 160),
    notes: cap(body.notes, 500),
    day: cap(body.day, 10),
    time: cap(body.time, 5),
    when: cap(body.when, 120),
    at: new Date().toISOString(),
    source: "workzap.ai/nori/talk",
  };
  const digits = entry.phone.replace(/\D/g, "");
  if (!entry.name || !entry.business || digits.length < 8 || digits.length > 15 || !/^\d{4}-\d{2}-\d{2}$/.test(entry.day) || !/^\d{2}:\d{2}$/.test(entry.time)) {
    return NextResponse.json({ ok: false }, { status: 400 });
  }

  const hook = process.env.BOOKING_WEBHOOK_URL;
  if (!hook) return NextResponse.json({ ok: true, delivered: false });
  try {
    const r = await fetch(hook, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(entry),
      signal: AbortSignal.timeout(8000),
    });
    return NextResponse.json({ ok: true, delivered: r.ok });
  } catch {
    return NextResponse.json({ ok: true, delivered: false });
  }
}
