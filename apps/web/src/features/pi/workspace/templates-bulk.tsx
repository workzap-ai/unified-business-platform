"use client";

/**
 * Templates page, part two: send one approved template to many numbers (pasted, existing
 * customers, or the Nori registry) and the history of every send with its real WhatsApp status.
 * Backend: pi_saas/template_sends.py. Nothing is sent from the dialog: the rows are queued and a
 * worker sends a few at a time (at most 200 a day, never at night).
 */
import { useState } from "react";
import Link from "next/link";
import { MessageCircle, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge, Card, CardBody } from "@/components/ui/display";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/overlays";
import { FormField } from "@/components/app/forms";
import { EmptyState, ErrorState } from "@/components/app/states";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { formatDateTime, relativeTime } from "@/lib/format";
import { inboxHref } from "./lib";
import {
  piTemplatesService,
  type AudienceRow,
  type BatchResult,
  type Template,
} from "../templates-service";

const HISTORY_KEY = [["pi", "templates", "history"]];

type Source = "paste" | "customers" | "nori";
type Row = { phone: string; person: string; values: string[] };

/** One person per line: `number, name, value, value`. A header line (no digits) is ignored. */
export function parsePasted(text: string): Row[] {
  const rows: Row[] = [];
  for (const line of text.split(/\r?\n/)) {
    const parts = line.split(/[,\t;|]/).map((p) => p.trim());
    if (!parts[0] || !/\d/.test(parts[0])) continue;
    rows.push({
      phone: parts[0],
      person: parts[1] ?? "",
      values: parts.slice(2),
    });
  }
  return rows;
}

export function BulkDialog({
  sendable,
  onClose,
}: {
  sendable: Template[];
  onClose: () => void;
}) {
  const [chosen, setChosen] = useState("");
  const [source, setSource] = useState<Source>("paste");
  const [text, setText] = useState("");
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState<Record<string, AudienceRow>>({});
  const [nameFirst, setNameFirst] = useState(true);
  const [shared, setShared] = useState<string[]>([]);
  const [consent, setConsent] = useState(false);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BatchResult | null>(null);
  const template = sendable.find((t) => `${t.name}|${t.language}` === chosen);
  const variables = template?.variables ?? 0;
  const audience = useScopedQuery(
    ["pi", "templates", "audience", source, q],
    () => piTemplatesService.audience(source as "customers" | "nori", q),
    { enabled: source !== "paste" },
  );
  const people = Object.values(picked);
  // For picked people the first {{1}} can be each person's name; the rest are the same for all.
  const rows: Row[] =
    source === "paste"
      ? parsePasted(text)
      : people.map((p) => ({
          phone: p.phone,
          person: p.person,
          values: Array.from({ length: variables }, (_, i) =>
            i === 0 && nameFirst
              ? p.person || "there"
              : (shared[i] ?? "").trim(),
          ),
        }));
  const queue = useScopedMutation(
    () =>
      piTemplatesService.queue({
        name: template?.name ?? "",
        language: template?.language ?? "",
        rows,
        source,
        consent,
        consent_note: note.trim(),
      }),
    {
      invalidate: HISTORY_KEY,
      toastErrors: false,
      onSuccess: setResult,
    },
  );
  const submit = () => {
    if (!template) return setError("Choose an approved template");
    if (rows.length === 0) return setError("Add at least one number");
    if (rows.length > 500) return setError("Up to 500 numbers at a time");
    if (!consent || note.trim().length < 3)
      return setError(
        "Confirm these people agreed to be messaged and say how they agreed",
      );
    setError(null);
    queue.mutate(undefined, {
      onError: (e) =>
        setError(e instanceof Error ? e.message : "That didn’t work."),
    });
  };
  return (
    <Dialog
      open
      onOpenChange={(next) => !next && !queue.isPending && onClose()}
    >
      <DialogContent size="lg">
        <DialogHeader
          title="Send a template to many numbers"
          description="Nothing is sent from here. The messages are queued and go out a few at a time, never at night. People who replied STOP are skipped."
        />
        {result ? (
          <>
            <DialogBody className="space-y-3">
              <p className="text-sm">
                <strong className="tabular-nums">{result.queued}</strong>{" "}
                message{result.queued === 1 ? "" : "s"} queued. At most{" "}
                {result.daily_cap} go out a day, between 9am and 9pm. Follow
                them in History.
              </p>
              {result.rejected.length > 0 && (
                <div>
                  <p className="text-[13px] font-medium">
                    Left out ({result.rejected.length})
                  </p>
                  <ul className="mt-1 max-h-48 divide-y divide-border overflow-auto rounded-md border border-border text-[13px]">
                    {result.rejected.map((r, i) => (
                      <li key={i} className="flex justify-between gap-3 p-2">
                        <span className="tabular-nums">{r.phone || "-"}</span>
                        <span className="text-muted-foreground">
                          {r.reason}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </DialogBody>
            <DialogFooter>
              <Button onClick={onClose}>Done</Button>
            </DialogFooter>
          </>
        ) : (
          <>
            <DialogBody className="space-y-4">
              <FormField label="Template" htmlFor="bulk-template">
                <NativeSelect
                  id="bulk-template"
                  value={chosen}
                  onChange={(e) => {
                    setChosen(e.target.value);
                    setShared([]);
                  }}
                >
                  <option value="">Choose an approved template…</option>
                  {sendable.map((t) => (
                    <option
                      key={`${t.name}|${t.language}`}
                      value={`${t.name}|${t.language}`}
                    >
                      {t.name} ({t.language})
                      {t.variables ? ` · ${t.variables} value(s)` : ""}
                    </option>
                  ))}
                </NativeSelect>
              </FormField>
              {template && (
                <p className="rounded-md bg-surface-muted p-2.5 text-[13px] break-words whitespace-pre-wrap">
                  {template.body}
                </p>
              )}
              <div
                role="group"
                aria-label="Where the numbers come from"
                className="inline-flex h-8 items-center gap-0.5 rounded-md border border-border bg-surface-muted p-0.5"
              >
                {(
                  [
                    ["paste", "Paste a list"],
                    ["customers", "Existing customers"],
                    ["nori", "Nori numbers"],
                  ] as const
                ).map(([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    aria-pressed={source === key}
                    onClick={() => setSource(key)}
                    className={`inline-flex h-6.5 items-center rounded-[5px] px-2.5 text-xs font-medium ${source === key ? "bg-surface text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              {source === "paste" ? (
                <FormField
                  label="Numbers"
                  htmlFor="bulk-paste"
                  help={`One person per line: number, name${variables ? `, then ${variables} value(s) for {{1}}…` : ""}. With the country code, e.g. 923001234567, Ayesha${variables > 1 ? ", Mendeez Demo, 20 November" : ""}.`}
                >
                  <Textarea
                    id="bulk-paste"
                    rows={7}
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    placeholder={"923001234567, Ayesha\n923007654321, Bilal"}
                  />
                </FormField>
              ) : (
                <div className="space-y-2">
                  <Input
                    aria-label="Search people"
                    placeholder="Search by name or number"
                    value={q}
                    onChange={(e) => setQ(e.target.value)}
                  />
                  {audience.isPending ? (
                    <p className="text-xs text-muted-foreground">Loading…</p>
                  ) : (
                    <>
                      <div className="flex items-center justify-between text-xs text-muted-foreground">
                        <span>
                          {audience.data?.items.length ?? 0} shown ·{" "}
                          {people.length} picked
                        </span>
                        <button
                          type="button"
                          className="text-primary hover:underline"
                          onClick={() =>
                            setPicked((all) => {
                              const next = { ...all };
                              for (const p of audience.data?.items ?? [])
                                next[p.phone] = p;
                              return next;
                            })
                          }
                        >
                          Pick all shown
                        </button>
                      </div>
                      <ul className="max-h-56 divide-y divide-border overflow-auto rounded-md border border-border text-[13px]">
                        {(audience.data?.items ?? []).map((p) => (
                          <li key={p.phone}>
                            <label className="flex cursor-pointer items-center gap-2 p-2">
                              <input
                                type="checkbox"
                                className="size-4"
                                checked={!!picked[p.phone]}
                                onChange={(e) =>
                                  setPicked((all) => {
                                    const next = { ...all };
                                    if (e.target.checked) next[p.phone] = p;
                                    else delete next[p.phone];
                                    return next;
                                  })
                                }
                              />
                              <span className="min-w-0 flex-1 truncate">
                                {p.person || "No name"}
                                {p.label ? ` · ${p.label}` : ""}
                              </span>
                              <span className="text-muted-foreground tabular-nums">
                                {p.phone}
                              </span>
                            </label>
                          </li>
                        ))}
                      </ul>
                    </>
                  )}
                  {variables > 0 && (
                    <div className="grid gap-3 sm:grid-cols-2">
                      <label className="flex items-center gap-2 text-[13px] sm:col-span-2">
                        <input
                          type="checkbox"
                          className="size-4"
                          checked={nameFirst}
                          onChange={(e) => setNameFirst(e.target.checked)}
                        />
                        Use each person’s name for {"{{1}}"}
                      </label>
                      {Array.from({ length: variables }, (_, i) =>
                        i === 0 && nameFirst ? null : (
                          <FormField
                            key={i}
                            label={`Value for {{${i + 1}}} (same for everyone)`}
                            htmlFor={`bulk-shared-${i}`}
                          >
                            <Input
                              id={`bulk-shared-${i}`}
                              autoComplete="off"
                              maxLength={200}
                              value={shared[i] ?? ""}
                              onChange={(e) =>
                                setShared((all) => {
                                  const next = [...all];
                                  next[i] = e.target.value;
                                  return next;
                                })
                              }
                            />
                          </FormField>
                        ),
                      )}
                    </div>
                  )}
                </div>
              )}
              <p className="text-[13px] text-muted-foreground">
                <strong className="tabular-nums text-foreground">
                  {rows.length}
                </strong>{" "}
                number{rows.length === 1 ? "" : "s"} ready. WhatsApp charges for
                each delivered template message.
              </p>
              <label className="flex items-start gap-2 text-[13px]">
                <input
                  type="checkbox"
                  className="mt-0.5 size-4"
                  checked={consent}
                  onChange={(e) => setConsent(e.target.checked)}
                />
                <span>
                  These people agreed to be messaged on WhatsApp by Workzap.
                  (Meta requires it; without it the number can be blocked.)
                </span>
              </label>
              <FormField
                label="How did they agree?"
                htmlFor="bulk-note"
                help="Kept as evidence, e.g. “Signed up on the nori site”."
              >
                <Input
                  id="bulk-note"
                  maxLength={300}
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                />
              </FormField>
              {error && (
                <p className="text-[13px] text-danger" role="alert">
                  {error}
                </p>
              )}
            </DialogBody>
            <DialogFooter>
              <Button
                variant="secondary"
                onClick={onClose}
                disabled={queue.isPending}
              >
                Cancel
              </Button>
              <Button loading={queue.isPending} onClick={submit}>
                <Users /> Queue {rows.length || ""} message
                {rows.length === 1 ? "" : "s"}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

const SEND_TONE: Record<
  string,
  "success" | "warning" | "danger" | "neutral" | "info" | "primary"
> = {
  queued: "warning",
  sent: "info",
  delivered: "success",
  read: "success",
  failed: "danger",
  skipped: "neutral",
  cancelled: "neutral",
};

const ERROR_TEXT: Record<string, string> = {
  OPTED_OUT: "Asked us to stop",
  CANCELLED_BY_TEAM: "Cancelled by the team",
  WHATSAPP_NOT_CONNECTED: "WhatsApp not connected",
  CONVERSATION_CLOSED: "Chat closed",
  DUPLICATE_24H: "Same message sent in the last day",
};

/** Every template message sent from this page, with the real WhatsApp status. */
export function HistoryView({ templates }: { templates: Template[] }) {
  const [template, setTemplate] = useState("");
  const [phone, setPhone] = useState("");
  const [status, setStatus] = useState("");
  const history = useScopedQuery(
    ["pi", "templates", "history", template, phone.trim(), status],
    () =>
      piTemplatesService.history({
        template: template || undefined,
        phone: phone.trim() || undefined,
        status: status || undefined,
      }),
    { refetchInterval: 30_000 },
  );
  const cancel = useScopedMutation(piTemplatesService.cancelBatch, {
    invalidate: HISTORY_KEY,
    success: "Cancelled the messages that had not gone out yet",
  });
  const items = history.data?.items ?? [];
  const names = [...new Set(templates.map((t) => t.name))];
  const batches = [
    ...new Set(
      items.filter((i) => i.status === "queued").map((i) => i.batch_id),
    ),
  ];
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <FormField label="Template" htmlFor="hist-template">
          <NativeSelect
            id="hist-template"
            value={template}
            onChange={(e) => setTemplate(e.target.value)}
          >
            <option value="">All templates</option>
            {names.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </NativeSelect>
        </FormField>
        <FormField label="Status" htmlFor="hist-status">
          <NativeSelect
            id="hist-status"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="">Any</option>
            {Object.keys(SEND_TONE).map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </NativeSelect>
        </FormField>
        <FormField label="Number" htmlFor="hist-phone">
          <Input
            id="hist-phone"
            inputMode="tel"
            placeholder="Part of a number"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
          />
        </FormField>
        {batches.map((b) => (
          <Button
            key={b}
            size="sm"
            variant="secondary"
            loading={cancel.isPending}
            onClick={() => cancel.mutate(b)}
          >
            Cancel queued (
            {
              items.filter((i) => i.batch_id === b && i.status === "queued")
                .length
            }
            )
          </Button>
        ))}
      </div>
      {history.isError ? (
        <ErrorState
          error={history.error}
          onRetry={() => void history.refetch()}
        />
      ) : history.isPending ? (
        <div className="h-40 animate-pulse rounded-xl bg-surface-sunken" />
      ) : items.length === 0 ? (
        <EmptyState
          icon={MessageCircle}
          title="Nothing sent yet"
          description="Messages sent from this page, one by one or to many, show here with their status."
        />
      ) : (
        <Card>
          <CardBody className="overflow-x-auto p-0">
            <table className="w-full min-w-[640px] text-left text-[13px]">
              <thead className="border-b border-border text-xs text-muted-foreground">
                <tr>
                  <th className="p-2.5 font-medium">Person</th>
                  <th className="p-2.5 font-medium">Template</th>
                  <th className="p-2.5 font-medium">Status</th>
                  <th className="p-2.5 font-medium">When</th>
                  <th className="p-2.5" />
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {items.map((i) => (
                  <tr key={i.id}>
                    <td className="p-2.5">
                      <div className="font-medium">{i.person || "No name"}</div>
                      <div className="text-xs text-muted-foreground tabular-nums">
                        +{i.phone}
                      </div>
                    </td>
                    <td className="p-2.5">
                      <div>{i.template}</div>
                      {i.values.length > 0 && (
                        <div className="max-w-56 truncate text-xs text-muted-foreground">
                          {i.values.join(" · ")}
                        </div>
                      )}
                    </td>
                    <td className="p-2.5">
                      <Badge tone={SEND_TONE[i.status] ?? "neutral"}>
                        {i.status}
                      </Badge>
                      {i.error && (
                        <div className="mt-0.5 text-xs text-muted-foreground">
                          {ERROR_TEXT[i.error] ?? i.error}
                        </div>
                      )}
                    </td>
                    <td className="p-2.5 text-muted-foreground">
                      <time
                        dateTime={i.sent_at ?? i.created_at}
                        title={formatDateTime(i.sent_at ?? i.created_at)}
                      >
                        {relativeTime(i.sent_at ?? i.created_at)}
                      </time>
                    </td>
                    <td className="p-2.5 text-right">
                      {i.conversation_id && (
                        <Link
                          href={inboxHref(i.conversation_id)}
                          className="text-primary hover:underline"
                        >
                          Open chat
                        </Link>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardBody>
        </Card>
      )}
    </div>
  );
}
