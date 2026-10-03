"use client";

import { useQuery } from "@tanstack/react-query";
import { FileText, Wand2 } from "lucide-react";
import * as React from "react";

import {
  Badge,
  Button,
  Card,
  CardSection,
  Field,
  Input,
  LoadingBlock,
  Notice,
  Select,
  Textarea,
} from "@/components/ui";
import { errorText, get, post } from "@/lib/api";
import { useAction, useBusinessKey, useCan } from "@/lib/session";

interface Template {
  name: string;
  language: string;
  status: string;
  category: string;
  body: string;
  sendable: boolean;
}
interface FormItem {
  purpose: "lead" | "booking" | "feedback";
  name: string;
  fields: string[];
  flow_id: string | null;
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

/** WhatsApp templates on the connected number: see approval, add a plain-text one. */
export function TemplatesCard() {
  const key = useBusinessKey();
  const can = useCan();
  const list = useQuery({
    queryKey: key(["wa-templates"]),
    queryFn: () =>
      get<{ templates: Template[]; number: string }>("/pi/whatsapp/templates"),
    retry: false,
  });
  const [form, setForm] = React.useState({
    name: "",
    language: "en",
    category: "MARKETING",
    body: "",
  });
  const create = useAction(() => post("/pi/whatsapp/templates", form), {
    invalidate: [["wa-templates"]],
    success: "Sent to Meta for review. It can be used once it's approved.",
    onSuccess: () =>
      setForm({ name: "", language: "en", category: "MARKETING", body: "" }),
  });
  return (
    <Card className="mt-6">
      <CardSection className="space-y-4">
        <h2 className="flex items-center gap-2 font-semibold">
          <FileText className="size-4 text-accent" aria-hidden /> WhatsApp
          templates
        </h2>
        <p className="text-sm text-muted-foreground">
          Messages sent outside a live chat (reminders, campaigns) must use a
          template Meta approved. pi can send plain-text templates without
          variables or buttons.
        </p>
        {list.isPending ? (
          <LoadingBlock rows={2} />
        ) : list.isError ? (
          <Notice tone="info">{errorText(list.error)}</Notice>
        ) : !list.data.templates.length ? (
          <p className="text-sm text-muted-foreground">No templates yet.</p>
        ) : (
          <ul className="divide-y divide-border rounded-lg border border-border">
            {list.data.templates.map((t) => (
              <li key={`${t.name}-${t.language}`} className="space-y-1 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{t.name}</span>
                  <span className="text-xs text-muted-foreground">
                    {t.language} · {t.category.toLowerCase()}
                  </span>
                  <Badge tone={STATUS_TONE[t.status] ?? "neutral"}>
                    {t.status.toLowerCase()}
                  </Badge>
                  {!t.sendable ? (
                    <Badge tone="neutral">pi can&apos;t send this one</Badge>
                  ) : null}
                </div>
                <p className="text-sm text-muted-foreground" data-user-text>
                  {t.body}
                </p>
              </li>
            ))}
          </ul>
        )}
        {can("pi.settings.manage") && !list.isError ? (
          <details className="rounded-lg border border-border p-3">
            <summary className="cursor-pointer text-sm font-medium">
              Add a template
            </summary>
            <div className="mt-3 grid gap-3 sm:grid-cols-3">
              <Field
                label="Name"
                htmlFor="tpl-name"
                hint="lowercase_with_underscores"
              >
                <Input
                  id="tpl-name"
                  value={form.name}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      name: e.target.value
                        .toLowerCase()
                        .replace(/[^a-z0-9_]/g, "_"),
                    })
                  }
                />
              </Field>
              <Field label="Language code" htmlFor="tpl-lang">
                <Input
                  id="tpl-lang"
                  value={form.language}
                  onChange={(e) =>
                    setForm({ ...form, language: e.target.value })
                  }
                />
              </Field>
              <Field label="Type" htmlFor="tpl-cat">
                <Select
                  id="tpl-cat"
                  value={form.category}
                  onChange={(e) =>
                    setForm({ ...form, category: e.target.value })
                  }
                >
                  <option value="MARKETING">Offers and news</option>
                  <option value="UTILITY">Updates and reminders</option>
                </Select>
              </Field>
            </div>
            <Field label="Message" htmlFor="tpl-body">
              <Textarea
                id="tpl-body"
                rows={3}
                maxLength={1024}
                value={form.body}
                onChange={(e) => setForm({ ...form, body: e.target.value })}
              />
            </Field>
            <Button
              className="mt-3"
              loading={create.isPending}
              disabled={
                !/^[a-z0-9_]{1,512}$/.test(form.name) ||
                !form.body.trim() ||
                form.body.includes("{{")
              }
              onClick={() => create.mutate(undefined)}
            >
              Send for approval
            </Button>
          </details>
        ) : null}
      </CardSection>
    </Card>
  );
}

/** Ready-made WhatsApp forms, created and published with one click. */
export function OneClickForms() {
  const key = useBusinessKey();
  const can = useCan();
  const forms = useQuery({
    queryKey: key(["wa-forms"]),
    queryFn: () => get<{ forms: FormItem[] }>("/pi/whatsapp/forms"),
  });
  const make = useAction(
    (purpose: string) => post(`/pi/whatsapp/forms/${purpose}/create`),
    {
      invalidate: [["wa-forms"], ["settings"]],
      success: "Form created and published. Turn on WhatsApp forms in Tools.",
    },
  );
  if (forms.isPending || forms.isError) return null;
  return (
    <Card className="mt-6">
      <CardSection className="space-y-3">
        <h2 className="flex items-center gap-2 font-semibold">
          <Wand2 className="size-4 text-accent" aria-hidden /> Ready-made forms
        </h2>
        <p className="text-sm text-muted-foreground">
          Create a form on your WhatsApp number in one click. No need to open
          WhatsApp Manager.
        </p>
        <ul className="grid gap-3 sm:grid-cols-3">
          {forms.data.forms.map((f) => (
            <li key={f.purpose} className="rounded-lg border border-border p-3">
              <p className="font-medium">{f.name}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {f.fields.join(" · ")}
              </p>
              {f.flow_id ? (
                <Badge tone="success" className="mt-2">
                  Ready
                </Badge>
              ) : can("pi.settings.manage") ? (
                <Button
                  size="sm"
                  variant="secondary"
                  className="mt-2"
                  loading={make.isPending}
                  onClick={() => make.mutate(f.purpose)}
                >
                  Create this form
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      </CardSection>
    </Card>
  );
}
