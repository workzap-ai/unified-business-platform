"use client";

import { useMemo, useState } from "react";
import { PI } from "../pi/config";

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const ROLES = ["Owner", "Head of operations", "Head of finance", "Store or area manager", "Other"];
const SHOPS = ["1", "2 to 10", "11 to 25", "More than 25"];

// Working hours are shown in Pakistan time. Monday to Friday, 10:00 to 17:00, every 30
// minutes. Workzap sets the real hours; until then every request is confirmed by hand.
const SLOTS = Array.from({ length: 14 }, (_, i) => {
  const m = 10 * 60 + i * 30;
  return { h: Math.floor(m / 60), m: m % 60 };
});

function pad(n: number) {
  return String(n).padStart(2, "0");
}
function clock(h: number, m: number) {
  const hh = h % 12 === 0 ? 12 : h % 12;
  return `${hh}:${pad(m)} ${h >= 12 ? "pm" : "am"}`;
}
function iso(y: number, m: number, d: number) {
  return `${y}-${pad(m + 1)}-${pad(d)}`;
}
function label(isoDate: string, slot: { h: number; m: number }) {
  const [y, mo, d] = isoDate.split("-").map(Number);
  const dt = new Date(Date.UTC(y, mo - 1, d));
  const dow = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][dt.getUTCDay()];
  const end = slot.m + 30 >= 60 ? { h: slot.h + 1, m: slot.m - 30 } : { h: slot.h, m: slot.m + 30 };
  return `${dow} ${d} ${MONTHS[mo - 1].slice(0, 3)}, ${clock(slot.h, slot.m)} to ${clock(end.h, end.m)}, Pakistan time`;
}

type Status = "idle" | "sending" | "done" | "error";

export function TalkForm() {
  const today = useMemo(() => {
    const n = new Date();
    return new Date(n.getFullYear(), n.getMonth(), n.getDate());
  }, []);
  const [view, setView] = useState({ y: today.getFullYear(), m: today.getMonth() });
  const [day, setDay] = useState<string | null>(null);
  const [slot, setSlot] = useState<{ h: number; m: number } | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [delivered, setDelivered] = useState(false);
  const [msg, setMsg] = useState("");
  const [form, setForm] = useState({
    name: "", business: "", role: ROLES[0], shops: SHOPS[1], phone: "", email: "", notes: "", consent: false, website: "",
  });

  const first = new Date(view.y, view.m, 1);
  const lead = (first.getDay() + 6) % 7;
  const count = new Date(view.y, view.m + 1, 0).getDate();
  const limit = new Date(today.getTime() + 45 * 86400000);
  const cells: (number | null)[] = [
    ...Array.from({ length: lead }, () => null),
    ...Array.from({ length: count }, (_, i) => i + 1),
  ];
  const isOpen = (d: number) => {
    const dt = new Date(view.y, view.m, d);
    const dow = (dt.getDay() + 6) % 7;
    return dt > today && dt <= limit && dow < 5;
  };
  const canPrev = view.y > today.getFullYear() || view.m > today.getMonth();
  const canNext = new Date(view.y, view.m + 1, 1) <= limit;
  const step = (dir: -1 | 1) => {
    const d = new Date(view.y, view.m + dir, 1);
    setView({ y: d.getFullYear(), m: d.getMonth() });
    setDay(null);
    setSlot(null);
  };

  const summary = day && slot ? label(day, slot) : "";
  const waText = (extra = "") =>
    `Hi pi, I would like a 30-minute nori meeting.${summary ? ` ${summary}.` : ""} Name: ${form.name}. Business: ${form.business}. Shops: ${form.shops}.${extra}`;
  const waHref = `https://wa.me/${PI.whatsappNumber}?text=${encodeURIComponent(waText())}`;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!day || !slot) return setMsg("Please choose a day and a time first.");
    if (!form.name.trim()) return setMsg("Please fill in: your name. Nothing has been sent.");
    if (!form.business.trim()) return setMsg("Please fill in: business name. Nothing has been sent.");
    const digits = form.phone.replace(/[^\d]/g, "");
    if (digits.length < 8 || digits.length > 15)
      return setMsg("That number does not look right. Please check the country code, for example +92. Nothing has been sent.");
    if (form.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email))
      return setMsg("That email does not look right. You can leave it empty. Nothing has been sent.");
    if (!form.consent) return setMsg("Please tick the box so we can reply to you. Nothing has been sent.");
    setMsg("");
    setStatus("sending");
    try {
      const r = await fetch("/api/nori/booking", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...form, day, time: `${pad(slot.h)}:${pad(slot.m)}`, when: summary }),
      });
      const j = (await r.json()) as { ok?: boolean; delivered?: boolean };
      if (!r.ok || !j.ok) throw new Error("fail");
      setDelivered(Boolean(j.delivered));
      setStatus("done");
    } catch {
      setStatus("error");
      setMsg("We could not send your request. Nothing has been sent. Please try again in a minute, or message pi on WhatsApp.");
    }
  }

  if (status === "done") {
    return (
      <div className="nv-confirm" role="status">
        <h2>{delivered ? "Your request is with us." : "One more step."}</h2>
        <p>
          <strong>{summary}</strong>
        </p>
        <p>
          {delivered
            ? "We will message you on WhatsApp to confirm the time."
            : "Send this to pi on WhatsApp so we can confirm your time. It takes five seconds."}
        </p>
        <a className="nx-btn nx-btn-primary" href={waHref} target="_blank" rel="noopener noreferrer">
          Confirm on WhatsApp
        </a>
      </div>
    );
  }

  return (
    <form className="nv-form" onSubmit={submit} noValidate>
      <fieldset className="nv-cal">
        <legend>1. Pick a day and time</legend>
        <div className="nv-cal-head">
          <button type="button" onClick={() => step(-1)} disabled={!canPrev} aria-label="Previous month">‹</button>
          <strong>{MONTHS[view.m]} {view.y}</strong>
          <button type="button" onClick={() => step(1)} disabled={!canNext} aria-label="Next month">›</button>
        </div>
        <div className="nv-cal-grid" role="grid" aria-label={`${MONTHS[view.m]} ${view.y}`}>
          {DAYS.map((d) => (
            <span key={d} className="nv-cal-dow">{d}</span>
          ))}
          {cells.map((d, i) =>
            d === null ? (
              <span key={`b${i}`} />
            ) : (
              <button
                key={d}
                type="button"
                disabled={!isOpen(d)}
                className={day === iso(view.y, view.m, d) ? "is-on" : undefined}
                aria-pressed={day === iso(view.y, view.m, d)}
                onClick={() => {
                  setDay(iso(view.y, view.m, d));
                  setSlot(null);
                }}
              >
                {d}
              </button>
            ),
          )}
        </div>
        {day ? (
          <div className="nv-slots" role="group" aria-label="Times, Pakistan time">
            {SLOTS.map((s) => (
              <button
                key={`${s.h}${s.m}`}
                type="button"
                className={slot && slot.h === s.h && slot.m === s.m ? "is-on" : undefined}
                aria-pressed={Boolean(slot && slot.h === s.h && slot.m === s.m)}
                onClick={() => setSlot(s)}
              >
                {clock(s.h, s.m)}
              </button>
            ))}
          </div>
        ) : (
          <p className="nv-hint">Times are shown in Pakistan time. Monday to Friday.</p>
        )}
        {summary ? <p className="nv-picked">{summary}</p> : null}
      </fieldset>

      <fieldset className="nv-fields">
        <legend>2. About you</legend>
        <label>Your name
          <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} autoComplete="name" required />
        </label>
        <label>Business name
          <input value={form.business} onChange={(e) => setForm({ ...form, business: e.target.value })} autoComplete="organization" required />
        </label>
        <label>Your role
          <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
            {ROLES.map((r) => <option key={r}>{r}</option>)}
          </select>
        </label>
        <label>Number of shops
          <select value={form.shops} onChange={(e) => setForm({ ...form, shops: e.target.value })}>
            {SHOPS.map((r) => <option key={r}>{r}</option>)}
          </select>
        </label>
        <label>WhatsApp number
          <input type="tel" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} placeholder="+92 ..." autoComplete="tel" required />
        </label>
        <label>Email (optional)
          <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} autoComplete="email" />
        </label>
        <label className="nv-wide">What would you like to see? (optional)
          <textarea rows={3} maxLength={500} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
        </label>
        <input
          className="nv-hp"
          tabIndex={-1}
          autoComplete="off"
          aria-hidden="true"
          value={form.website}
          onChange={(e) => setForm({ ...form, website: e.target.value })}
        />
        <label className="nv-check nv-wide">
          <input type="checkbox" checked={form.consent} onChange={(e) => setForm({ ...form, consent: e.target.checked })} />
          <span>Workzap may use these details to arrange this meeting and reply to me.</span>
        </label>
      </fieldset>

      {msg ? <p className="nv-msg" role="alert">{msg}</p> : null}
      <button className="nx-btn nx-btn-primary" type="submit" disabled={status === "sending"}>
        {status === "sending" ? "Sending…" : "Book my meeting"}
      </button>
    </form>
  );
}
