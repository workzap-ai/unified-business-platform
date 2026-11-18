"use client";

import { useState } from "react";
import { FileText, Pencil, Plus, Send } from "lucide-react";
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
import {
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import { FormField } from "@/components/app/forms";
import { EmptyState, ErrorState, Notice } from "@/components/app/states";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import {
  piTemplatesService,
  type NewTemplate,
  type Template,
} from "../templates-service";

const KEY = [["pi", "templates"]];

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

/** Starting points. Wording follows pi's rules: says it is an AI, one question at the end. */
const PRESETS: (NewTemplate & { label: string })[] = [
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

/** How many {{n}} a text has. */
function variableCount(body: string) {
  return new Set(body.match(/\{\{\d+\}\}/g) ?? []).size;
}

export function TemplatesPage() {
  return (
    <RequirePermission permission="pi.read" area="pi">
      <TemplatesView />
    </RequirePermission>
  );
}

function TemplatesView() {
  const { can } = useSession();
  const manage = can("pi.settings.manage");
  const list = useScopedQuery(["pi", "templates"], piTemplatesService.list);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Template | null>(null);
  const [chosen, setChosen] = useState("");
  const templates = list.data?.templates ?? [];
  const sendable = templates.filter(
    (t) => t.status === "APPROVED" && t.fillable,
  );
  return (
    <PageShell>
      <PageHeader
        title="WhatsApp templates"
        description="WhatsApp only lets pi start a chat, or write after 24 hours of silence, with a template Meta approved. Each message sent this way is charged by WhatsApp."
        actions={
          manage ? (
            <Button onClick={() => setCreating(true)}>
              <Plus /> New template
            </Button>
          ) : null
        }
      />
      {list.isError ? (
        <ErrorState error={list.error} onRetry={() => void list.refetch()} />
      ) : list.isPending ? (
        <div className="h-40 animate-pulse rounded-xl bg-surface-sunken" />
      ) : !list.data.connected ? (
        <Notice tone="info" title="No WhatsApp number yet">
          Connect a WhatsApp number first. Templates belong to that number.
        </Notice>
      ) : (
        <div className="space-y-6">
          {manage && (
            <SendCard
              sendable={sendable}
              chosen={chosen}
              onChoose={setChosen}
              number={list.data.number}
            />
          )}
          {templates.length === 0 ? (
            <EmptyState
              icon={FileText}
              title="No templates yet"
              description="Create one to start a conversation."
            />
          ) : (
            <ul className="grid grid-cols-1 gap-3 xl:grid-cols-2">
              {templates.map((t) => (
                <li key={`${t.name}-${t.language}`}>
                  <Card>
                    <CardBody className="space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium break-all">{t.name}</span>
                        <span className="text-xs text-muted-foreground">
                          {t.language} · {t.category.toLowerCase()}
                        </span>
                        <Badge tone={STATUS_TONE[t.status] ?? "neutral"}>
                          {t.status.toLowerCase()}
                        </Badge>
                        {t.variables > 0 && (
                          <Badge>
                            {t.variables} variable{t.variables > 1 ? "s" : ""}
                          </Badge>
                        )}
                        {!t.fillable && (
                          <Badge>has buttons or media, pi can’t send it</Badge>
                        )}
                      </div>
                      <p className="text-[13px] break-words whitespace-pre-wrap text-muted-foreground">
                        {t.body}
                      </p>
                      {manage && (
                        <div className="flex gap-2">
                          {t.status === "APPROVED" && t.fillable && (
                            <Button
                              size="sm"
                              variant="secondary"
                              onClick={() => {
                                setChosen(`${t.name}|${t.language}`);
                                window.scrollTo({ top: 0, behavior: "smooth" });
                              }}
                            >
                              <Send /> Use
                            </Button>
                          )}
                          {t.id && t.fillable && (
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => setEditing(t)}
                            >
                              <Pencil /> Edit
                            </Button>
                          )}
                        </div>
                      )}
                    </CardBody>
                  </Card>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {creating && <CreateDialog onClose={() => setCreating(false)} />}
      {editing && (
        <EditDialog template={editing} onClose={() => setEditing(null)} />
      )}
    </PageShell>
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
  const [phone, setPhone] = useState("");
  // What was typed, kept per template, so another template never shows these values.
  const [typed, setTyped] = useState<Record<string, string[]>>({});
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const picked = sendable.find((t) => `${t.name}|${t.language}` === chosen);
  const values = Array.from(
    { length: picked?.variables ?? 0 },
    (_, i) => typed[chosen]?.[i] ?? "",
  );
  const send = useScopedMutation(
    () =>
      piTemplatesService.send({
        phone,
        name: picked?.name ?? "",
        language: picked?.language ?? "",
        values,
        consent,
      }),
    {
      success: "Message sent",
      toastErrors: false,
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
  const submit = () => {
    if (!picked) return setError("Choose an approved template");
    if (phone.replace(/\D/g, "").length < 7)
      return setError("Enter the number with its country code");
    if (values.some((v) => !v.trim())) return setError("Fill every value");
    if (!consent) return setError("Confirm the person agreed to be messaged");
    setError(null);
    send.mutate(undefined, {
      onError: (e) =>
        setError(e instanceof Error ? e.message : "That didn’t work."),
    });
  };
  return (
    <Card>
      <CardBody className="space-y-4">
        <div>
          <h2 className="flex items-center gap-2 font-semibold">
            <Send className="size-4" aria-hidden /> Message a number
          </h2>
          <p className="text-[13px] text-muted-foreground">
            Starts the chat from {number ?? "your number"} with an approved
            template. Their reply opens a 24-hour window for normal messages.
          </p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField label="Phone number" htmlFor="send-phone">
            <Input
              id="send-phone"
              inputMode="tel"
              autoComplete="off"
              placeholder="+92 300 1234567"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
            />
          </FormField>
          <FormField label="Template" htmlFor="send-template">
            <NativeSelect
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
            </NativeSelect>
          </FormField>
        </div>
        {picked && values.length > 0 && (
          <div className="grid gap-4 sm:grid-cols-2">
            {values.map((value, i) => (
              <FormField
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
                    setTyped((all) => ({
                      ...all,
                      [chosen]: values.map((v, j) =>
                        j === i ? e.target.value : v,
                      ),
                    }))
                  }
                />
              </FormField>
            ))}
          </div>
        )}
        {picked && (
          <p className="rounded-lg bg-surface-muted p-3 text-[13px] break-words whitespace-pre-wrap">
            {preview}
          </p>
        )}
        <label className="flex items-start gap-2 text-[13px]">
          <input
            type="checkbox"
            className="mt-0.5 size-4"
            checked={consent}
            onChange={(e) => setConsent(e.target.checked)}
          />
          <span>
            This person agreed to be messaged on WhatsApp by Workzap. (Meta
            requires it; without it the number can be blocked.)
          </span>
        </label>
        {error && (
          <p className="text-[13px] text-danger" role="alert">
            {error}
          </p>
        )}
        <Button loading={send.isPending} onClick={submit}>
          <Send /> Send template
        </Button>
      </CardBody>
    </Card>
  );
}

function CreateDialog({ onClose }: { onClose: () => void }) {
  const [form, setForm] = useState<NewTemplate>({ ...PRESETS[0] });
  const count = variableCount(form.body);
  const examples = Array.from(
    { length: count },
    (_, i) => form.examples[i] ?? "",
  );
  const [error, setError] = useState<string | null>(null);
  const create = useScopedMutation(
    () =>
      // Only the fields the API takes: a preset also carries a label, which the server refuses.
      piTemplatesService.create({
        name: form.name,
        language: form.language,
        category: form.category,
        body: form.body,
        examples: count ? examples : [],
      }),
    {
      invalidate: KEY,
      success: "Sent to Meta for review. You can use it once it’s approved.",
      onSuccess: onClose,
    },
  );
  const submit = () => {
    if (!/^[a-z0-9_]{1,512}$/.test(form.name))
      return setError("Name: lowercase letters, numbers and underscores only");
    if (!form.body.trim()) return setError("Write the message text");
    if (count && examples.some((x) => !x.trim()))
      return setError("Add an example for every {{number}}");
    setError(null);
    create.mutate(undefined);
  };
  return (
    <Dialog
      open
      onOpenChange={(next) => !next && !create.isPending && onClose()}
    >
      <DialogContent size="md">
        <DialogHeader
          title="New template"
          description="Use {{1}}, {{2}} where a name or date goes. Meta reviews it, usually within minutes to hours."
        />
        <DialogBody className="space-y-3">
          <FormField label="Start from" htmlFor="tpl-preset">
            <NativeSelect
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
            </NativeSelect>
          </FormField>
          <div className="grid gap-3 sm:grid-cols-3">
            <FormField label="Name" htmlFor="tpl-name">
              <Input
                id="tpl-name"
                autoComplete="off"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </FormField>
            <FormField label="Language" htmlFor="tpl-lang">
              <Input
                id="tpl-lang"
                autoComplete="off"
                value={form.language}
                onChange={(e) => setForm({ ...form, language: e.target.value })}
              />
            </FormField>
            <FormField label="Category" htmlFor="tpl-cat">
              <NativeSelect
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
              </NativeSelect>
            </FormField>
          </div>
          <FormField label="Message" htmlFor="tpl-body">
            <Textarea
              id="tpl-body"
              rows={5}
              maxLength={1024}
              value={form.body}
              onChange={(e) => setForm({ ...form, body: e.target.value })}
            />
          </FormField>
          {count > 0 && (
            <div className="grid gap-3 sm:grid-cols-2">
              {examples.map((value, i) => (
                <FormField
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
                </FormField>
              ))}
            </div>
          )}
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
            disabled={create.isPending}
          >
            Cancel
          </Button>
          <Button loading={create.isPending} onClick={submit}>
            Send to Meta
          </Button>
        </DialogFooter>
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
  const [body, setBody] = useState(template.body);
  const [examples, setExamples] = useState<string[]>([]);
  const count = variableCount(body);
  const filled = Array.from({ length: count }, (_, i) => examples[i] ?? "");
  const [error, setError] = useState<string | null>(null);
  const save = useScopedMutation(
    () =>
      piTemplatesService.edit(template.id, {
        body,
        examples: count ? filled : [],
      }),
    {
      invalidate: KEY,
      success: "Changed. Meta reviews it again before it can be used.",
      onSuccess: onClose,
    },
  );
  const submit = () => {
    if (!body.trim()) return setError("Write the message text");
    if (count && filled.some((x) => !x.trim()))
      return setError("Add an example for every {{number}}");
    setError(null);
    save.mutate(undefined);
  };
  return (
    <Dialog open onOpenChange={(next) => !next && !save.isPending && onClose()}>
      <DialogContent size="md">
        <DialogHeader
          title={`Edit ${template.name}`}
          description="Meta reviews the new text again. Approved templates can be edited once a day, up to ten times a month."
        />
        <DialogBody className="space-y-3">
          <FormField label="Message" htmlFor="tpl-edit-body">
            <Textarea
              id="tpl-edit-body"
              rows={6}
              maxLength={1024}
              value={body}
              onChange={(e) => setBody(e.target.value)}
            />
          </FormField>
          {count > 0 && (
            <div className="grid gap-3 sm:grid-cols-2">
              {filled.map((value, i) => (
                <FormField
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
                </FormField>
              ))}
            </div>
          )}
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
            disabled={save.isPending}
          >
            Cancel
          </Button>
          <Button loading={save.isPending} onClick={submit}>
            Save and send to Meta
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
