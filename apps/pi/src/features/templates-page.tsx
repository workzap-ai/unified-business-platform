"use client";

/**
 * WhatsApp templates (/templates): the messages WhatsApp lets us start outside a live chat.
 * See each template's approval, create one (with {{1}} variables), edit its text (Meta reviews it
 * again), and send a first message to a number the person agreed to be messaged on.
 * API: app/modules/pi_saas/whatsapp_tools.py (/pi/whatsapp/templates).
 */
import { useQuery } from "@tanstack/react-query";
import { Pencil, Plus, Send } from "lucide-react";
import * as React from "react";

import {
  Badge,
  Button,
  Card,
  CardSection,
  Dialog,
  DialogContent,
  Field,
  Input,
  LoadingBlock,
  Notice,
  PageHeader,
  Select,
  Textarea,
} from "@/components/ui";
import { errorText, get, post, put } from "@/lib/api";
import { useAction, useBusinessKey, useCan } from "@/lib/session";

interface Template {
  id: string;
  name: string;
  language: string;
  status: string;
  category: string;
  body: string;
  variables: number;
  fillable: boolean;
}

const STATUS_TONE: Record<
  string,
  "success" | "warning" | "danger" | "neutral"
> = {
  APPROVED: "success",
  PENDING: "warning",
  IN_APPEAL: "warning",
  REJECTED: "danger",
  PAUSED: "danger",
  DISABLED: "danger",
};

/** Starting points for a new template. Wording follows pi's rules: says it is an AI, one question. */
const PRESETS: {
  label: string;
  name: string;
  language: string;
  category: "UTILITY" | "MARKETING";
  body: string;
  examples: string[];
}[] = [
  {
    label: "Nori welcome (English)",
    name: "nori_welcome_en",
    language: "en_US",
    category: "UTILITY",
    body: "Hello {{1}}, welcome to nori. I'm pi, an AI assistant from Workzap. I can answer questions about your workspace and pass your requests to the Workzap team. What would you like help with first?",
    examples: ["Ayesha"],
  },
  {
    label: "Nori welcome (Roman Urdu)",
    name: "nori_welcome_ur",
    language: "en_US",
    category: "UTILITY",
    body: "Assalam o Alaikum {{1}}, nori mein khush aamdeed. Main pi hoon, Workzap ka AI assistant. Main aap ke workspace ke sawalon ka jawab de sakta hoon aur aap ki zaroorat Workzap team tak pohancha sakta hoon. Aap sab se pehle kis cheez mein madad chahte hain?",
    examples: ["Ayesha"],
  },
  {
    label: "Trial ending reminder",
    name: "nori_trial_reminder",
    language: "en_US",
    category: "UTILITY",
    body: "Hello {{1}}, this is pi, an AI assistant from Workzap. The trial for {{2}} ends on {{3}}. Would you like help choosing a plan in nori?",
    examples: ["Ayesha", "Mendeez Demo", "20 November"],
  },
  {
    label: "Blank",
    name: "",
    language: "en_US",
    category: "UTILITY",
    body: "",
    examples: [],
  },
];

/** The numbers inside {{n}} in a text, in order, without repeats. */
function variableCount(body: string) {
  return new Set(body.match(/\{\{\d+\}\}/g) ?? []).size;
}

export function TemplatesPage() {
  const key = useBusinessKey();
  const can = useCan();
  const manage = can("pi.settings.manage");
  const list = useQuery({
    queryKey: key(["wa-templates"]),
    queryFn: () =>
      get<{
        templates: Template[];
        number: string | null;
        connected: boolean;
      }>("/pi/whatsapp/templates"),
    retry: false,
  });
  const [creating, setCreating] = React.useState(false);
  const [editing, setEditing] = React.useState<Template | null>(null);
  const [chosen, setChosen] = React.useState<string>("");
  const templates = list.data?.templates ?? [];
  const sendable = templates.filter(
    (t) => t.status === "APPROVED" && t.fillable,
  );
  return (
    <div>
      <PageHeader
        title="WhatsApp templates"
        description="WhatsApp only lets us start a chat, or write after 24 hours of silence, with a template Meta approved. Each message sent this way is charged by WhatsApp."
        action={
          manage ? (
            <Button onClick={() => setCreating(true)}>
              <Plus className="size-4" aria-hidden /> New template
            </Button>
          ) : null
        }
      />
      {list.isPending ? (
        <LoadingBlock rows={3} />
      ) : list.isError ? (
        <Notice tone="warning">{errorText(list.error)}</Notice>
      ) : !list.data.connected ? (
        <Notice tone="info">
          Connect a WhatsApp number first. Templates belong to that number.
        </Notice>
      ) : (
        <div className="space-y-6">
          {manage ? (
            <SendCard
              sendable={sendable}
              chosen={chosen}
              onChoose={setChosen}
              number={list.data.number}
            />
          ) : null}
          <Card>
            <CardSection className="space-y-3">
              <h2 className="font-semibold">
                Templates on {list.data.number ?? "this number"}{" "}
                <span className="text-sm font-normal text-muted-foreground tabular-nums">
                  {templates.length}
                </span>
              </h2>
              {templates.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No templates yet. Create one to start a conversation.
                </p>
              ) : (
                <ul className="divide-y divide-border rounded-lg border border-border">
                  {templates.map((t) => (
                    <li
                      key={`${t.name}-${t.language}`}
                      className="space-y-1.5 p-3"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium">{t.name}</span>
                        <span className="text-xs text-muted-foreground">
                          {t.language} · {t.category.toLowerCase()}
                        </span>
                        <Badge tone={STATUS_TONE[t.status] ?? "neutral"}>
                          {t.status.toLowerCase()}
                        </Badge>
                        {t.variables ? (
                          <Badge tone="neutral">
                            {t.variables} variable{t.variables > 1 ? "s" : ""}
                          </Badge>
                        ) : null}
                        {!t.fillable ? (
                          <Badge tone="neutral">
                            has buttons or media, pi can&apos;t send it
                          </Badge>
                        ) : null}
                        <span className="ms-auto flex gap-1">
                          {manage && t.status === "APPROVED" && t.fillable ? (
                            <Button
                              size="sm"
                              variant="secondary"
                              onClick={() => {
                                setChosen(`${t.name}|${t.language}`);
                                window.scrollTo({ top: 0, behavior: "smooth" });
                              }}
                            >
                              <Send className="size-3.5" aria-hidden /> Use
                            </Button>
                          ) : null}
                          {manage && t.id && t.fillable ? (
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => setEditing(t)}
                            >
                              <Pencil className="size-3.5" aria-hidden /> Edit
                            </Button>
                          ) : null}
                        </span>
                      </div>
                      <p
                        className="text-sm whitespace-pre-wrap text-muted-foreground"
                        data-user-text
                      >
                        {t.body}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </CardSection>
          </Card>
        </div>
      )}
      {creating ? <CreateDialog onClose={() => setCreating(false)} /> : null}
      {editing ? (
        <EditDialog template={editing} onClose={() => setEditing(null)} />
      ) : null}
    </div>
  );
}

/** Send the first message to one number, by an approved template. */
function SendCard({
  sendable,
  chosen,
  onChoose,
  number,
}: {
  sendable: Template[];
  chosen: string;
  onChoose: (value: string) => void;
  number: string | null;
}) {
  const [phone, setPhone] = React.useState("");
  // What was typed, kept per template, so switching template never shows another one's values.
  const [typed, setTyped] = React.useState<Record<string, string[]>>({});
  const [consent, setConsent] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const picked = sendable.find((t) => `${t.name}|${t.language}` === chosen);
  const values = Array.from(
    { length: picked?.variables ?? 0 },
    (_, i) => typed[chosen]?.[i] ?? "",
  );
  const setValues = (update: (all: string[]) => string[]) =>
    setTyped((all) => ({ ...all, [chosen]: update(values) }));
  const send = useAction(
    () =>
      post("/pi/whatsapp/templates/send", {
        phone,
        name: picked?.name,
        language: picked?.language,
        values,
        consent,
      }),
    {
      success: "Message sent",
      silentError: true,
      onSuccess: () => {
        setPhone("");
        setConsent(false);
      },
    },
  );
  const preview = picked
    ? picked.body.replace(
        /\{\{(\d+)\}\}/g,
        (_, n: string) => values[Number(n) - 1] || `{{${n}}}`,
      )
    : "";
  return (
    <Card>
      <CardSection>
        <form
          noValidate
          className="space-y-4"
          aria-label="Send a template message"
          onSubmit={async (e) => {
            e.preventDefault();
            if (!picked) return setError("Choose an approved template");
            if (phone.replace(/\D/g, "").length < 7)
              return setError("Enter the number with its country code");
            if (values.some((v) => !v.trim()))
              return setError("Fill every value");
            if (!consent)
              return setError("Confirm the person agreed to be messaged");
            setError(null);
            try {
              await send.mutateAsync(undefined);
            } catch (err) {
              setError(errorText(err));
            }
          }}
        >
          <h2 className="flex items-center gap-2 font-semibold">
            <Send className="size-4 text-accent" aria-hidden /> Message a number
          </h2>
          <p className="text-sm text-muted-foreground">
            Starts the chat from {number ?? "your number"} with an approved
            template. Their reply opens a 24-hour window for normal messages.
          </p>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Phone number" htmlFor="send-phone">
              <Input
                id="send-phone"
                inputMode="tel"
                autoComplete="off"
                placeholder="+92 300 1234567"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
              />
            </Field>
            <Field label="Template" htmlFor="send-template">
              <Select
                id="send-template"
                value={chosen}
                onChange={(e) => onChoose(e.target.value)}
              >
                <option value="">Choose…</option>
                {sendable.map((t) => (
                  <option
                    key={`${t.name}|${t.language}`}
                    value={`${t.name}|${t.language}`}
                  >
                    {t.name} ({t.language})
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          {picked && picked.variables > 0 ? (
            <div className="grid gap-4 sm:grid-cols-2">
              {values.map((value, i) => (
                <Field
                  key={i}
                  label={`Value for {{${i + 1}}}`}
                  htmlFor={`send-value-${i}`}
                >
                  <Input
                    id={`send-value-${i}`}
                    autoComplete="off"
                    maxLength={200}
                    value={value}
                    onChange={(e) =>
                      setValues((all) =>
                        all.map((v, j) => (j === i ? e.target.value : v)),
                      )
                    }
                  />
                </Field>
              ))}
            </div>
          ) : null}
          {picked ? (
            <p
              className="rounded-lg bg-surface-muted p-3 text-sm whitespace-pre-wrap"
              data-user-text
            >
              {preview}
            </p>
          ) : null}
          <label className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              className="mt-1 size-4"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
            />
            <span>
              This person agreed to be messaged on WhatsApp by Workzap. (Meta
              requires it; without it the number can be blocked.)
            </span>
          </label>
          {error ? (
            <p className="text-sm text-danger" role="alert">
              {error}
            </p>
          ) : null}
          <Button type="submit" loading={send.isPending}>
            <Send className="size-4" aria-hidden /> Send template
          </Button>
        </form>
      </CardSection>
    </Card>
  );
}

function CreateDialog({ onClose }: { onClose: () => void }) {
  const [form, setForm] = React.useState({ ...PRESETS[0] });
  const count = variableCount(form.body);
  const examples = Array.from(
    { length: count },
    (_, i) => form.examples[i] ?? "",
  );
  const [error, setError] = React.useState<string | null>(null);
  const create = useAction(
    () =>
      post("/pi/whatsapp/templates", {
        name: form.name,
        language: form.language,
        category: form.category,
        body: form.body,
        examples: count ? examples : [],
      }),
    {
      invalidate: [["wa-templates"]],
      success: "Sent to Meta for review. You can use it once it's approved.",
      silentError: true,
      onSuccess: onClose,
    },
  );
  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent
        title="New template"
        description="Use {{1}}, {{2}} where a name or date goes. Meta reviews it, usually within minutes to hours."
      >
        <form
          noValidate
          className="space-y-4"
          onSubmit={async (e) => {
            e.preventDefault();
            if (!/^[a-z0-9_]{1,512}$/.test(form.name))
              return setError(
                "Name: lowercase letters, numbers and underscores only",
              );
            if (!form.body.trim()) return setError("Write the message text");
            if (count && examples.some((x) => !x.trim()))
              return setError("Add an example for every {{number}}");
            setError(null);
            try {
              await create.mutateAsync(undefined);
            } catch (err) {
              setError(errorText(err));
            }
          }}
        >
          <Field label="Start from" htmlFor="tpl-preset">
            <Select
              id="tpl-preset"
              value=""
              onChange={(e) => {
                const preset = PRESETS[Number(e.target.value)];
                if (preset) setForm({ ...preset });
              }}
            >
              <option value="">Choose a starting point…</option>
              {PRESETS.map((p, i) => (
                <option key={p.label} value={i}>
                  {p.label}
                </option>
              ))}
            </Select>
          </Field>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Name" htmlFor="tpl-name">
              <Input
                id="tpl-name"
                autoComplete="off"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </Field>
            <Field label="Language" htmlFor="tpl-lang">
              <Input
                id="tpl-lang"
                autoComplete="off"
                value={form.language}
                onChange={(e) => setForm({ ...form, language: e.target.value })}
              />
            </Field>
            <Field label="Category" htmlFor="tpl-cat">
              <Select
                id="tpl-cat"
                value={form.category}
                onChange={(e) =>
                  setForm({
                    ...form,
                    category: e.target.value as "UTILITY" | "MARKETING",
                  })
                }
              >
                <option value="UTILITY">Utility (cheaper)</option>
                <option value="MARKETING">Marketing</option>
              </Select>
            </Field>
          </div>
          <Field label="Message" htmlFor="tpl-body">
            <Textarea
              id="tpl-body"
              rows={5}
              maxLength={1024}
              value={form.body}
              onChange={(e) => setForm({ ...form, body: e.target.value })}
            />
          </Field>
          {count ? (
            <div className="grid gap-4 sm:grid-cols-2">
              {examples.map((value, i) => (
                <Field
                  key={i}
                  label={`Example for {{${i + 1}}}`}
                  htmlFor={`tpl-ex-${i}`}
                >
                  <Input
                    id={`tpl-ex-${i}`}
                    autoComplete="off"
                    value={value}
                    onChange={(e) => {
                      const next = [...examples];
                      next[i] = e.target.value;
                      setForm({ ...form, examples: next });
                    }}
                  />
                </Field>
              ))}
            </div>
          ) : null}
          {error ? (
            <p className="text-sm text-danger" role="alert">
              {error}
            </p>
          ) : null}
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button
              type="button"
              variant="secondary"
              onClick={onClose}
              disabled={create.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" loading={create.isPending}>
              Send to Meta
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function EditDialog({
  template,
  onClose,
}: {
  template: Template;
  onClose: () => void;
}) {
  const [body, setBody] = React.useState(template.body);
  const [examples, setExamples] = React.useState<string[]>([]);
  const count = variableCount(body);
  const filled = Array.from({ length: count }, (_, i) => examples[i] ?? "");
  const [error, setError] = React.useState<string | null>(null);
  const save = useAction(
    () =>
      put(`/pi/whatsapp/templates/${template.id}`, {
        body,
        examples: count ? filled : [],
      }),
    {
      invalidate: [["wa-templates"]],
      success: "Changed. Meta reviews it again before it can be used.",
      silentError: true,
      onSuccess: onClose,
    },
  );
  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent
        title={`Edit ${template.name}`}
        description="Meta reviews the new text again. Approved templates can be edited once a day, up to ten times a month."
      >
        <form
          noValidate
          className="space-y-4"
          onSubmit={async (e) => {
            e.preventDefault();
            if (!body.trim()) return setError("Write the message text");
            if (count && filled.some((x) => !x.trim()))
              return setError("Add an example for every {{number}}");
            setError(null);
            try {
              await save.mutateAsync(undefined);
            } catch (err) {
              setError(errorText(err));
            }
          }}
        >
          <Field label="Message" htmlFor="tpl-edit-body">
            <Textarea
              id="tpl-edit-body"
              rows={6}
              maxLength={1024}
              value={body}
              onChange={(e) => setBody(e.target.value)}
            />
          </Field>
          {count ? (
            <div className="grid gap-4 sm:grid-cols-2">
              {filled.map((value, i) => (
                <Field
                  key={i}
                  label={`Example for {{${i + 1}}}`}
                  htmlFor={`tpl-edit-ex-${i}`}
                >
                  <Input
                    id={`tpl-edit-ex-${i}`}
                    autoComplete="off"
                    value={value}
                    onChange={(e) => {
                      const next = [...filled];
                      next[i] = e.target.value;
                      setExamples(next);
                    }}
                  />
                </Field>
              ))}
            </div>
          ) : null}
          {error ? (
            <p className="text-sm text-danger" role="alert">
              {error}
            </p>
          ) : null}
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button
              type="button"
              variant="secondary"
              onClick={onClose}
              disabled={save.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" loading={save.isPending}>
              Save and send to Meta
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
