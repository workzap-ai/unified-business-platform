"use client";

/**
 * Tools → "Your email": the business's own sender (SMTP, Resend or SendGrid). pi sends
 * payment links, receipts, booking and summary emails from it. Secret fields are never
 * shown back; leaving one blank keeps what is saved.
 */

import { useQuery } from "@tanstack/react-query";
import { Mail } from "lucide-react";
import * as React from "react";

import {
  Badge,
  Button,
  Card,
  CardSection,
  ErrorState,
  Field,
  Input,
  LoadingBlock,
  Select,
} from "@/components/ui";
import { del, errorText, get, post, put } from "@/lib/api";
import { date } from "@/lib/format";
import { useAction, useBusinessKey, useCan } from "@/lib/session";

type EmailField = {
  key: string;
  label: string;
  type: string;
  required: boolean;
  secret: boolean;
  help: string;
  options: { value: string; label: string }[];
};
type EmailStatus = {
  providers: {
    key: string;
    name: string;
    description: string;
    fields: EmailField[];
  }[];
  connection: {
    provider: string;
    state: "connected" | "connecting" | "action_required";
    from_address: string;
    from_name: string;
    values: Record<string, string>;
    secrets_set: string[];
    problem: string;
    last_checked_at: string | null;
  } | null;
  platform_fallback: boolean;
};
type Saved = EmailStatus & { ok: boolean; message: string };

const INPUT_TYPE: Record<string, string> = {
  email: "email",
  password: "password",
  number: "number",
  url: "url",
};

export function EmailCard() {
  const key = useBusinessKey();
  const can = useCan();
  const manage = can("integrations.manage");
  const status = useQuery({
    queryKey: key(["connectors", "email"]),
    queryFn: () => get<EmailStatus>("/pi/connectors/email"),
    enabled: can("integrations.read"),
  });
  const connection = status.data?.connection ?? null;
  const [provider, setProvider] = React.useState("");
  const [values, setValues] = React.useState<Record<string, string>>({});
  const [editing, setEditing] = React.useState(false);
  const [confirming, setConfirming] = React.useState(false);
  const [result, setResult] = React.useState<{
    ok: boolean;
    message: string;
  } | null>(null);

  function startEdit() {
    const chosen =
      connection?.provider ?? status.data?.providers[0]?.key ?? "smtp";
    setProvider(chosen);
    setValues(connection?.provider === chosen ? connection.values : {});
    setResult(null);
    setEditing(true);
  }

  const save = useAction(
    () => put<Saved>("/pi/connectors/email", { provider, values }),
    {
      invalidate: [["connectors", "email"]],
      onSuccess: (r) => {
        setResult({ ok: r.ok, message: r.message });
        if (r.ok) setEditing(false);
      },
    },
  );
  const test = useAction(() => post<Saved>("/pi/connectors/email/test"), {
    invalidate: [["connectors", "email"]],
    onSuccess: (r) => setResult({ ok: r.ok, message: r.message }),
  });
  const remove = useAction(() => del("/pi/connectors/email"), {
    invalidate: [["connectors", "email"]],
    success: "Email disconnected",
    onSuccess: () => {
      setConfirming(false);
      setResult(null);
    },
  });

  if (!can("integrations.read")) return null;
  const chosen = status.data?.providers.find((p) => p.key === provider);
  const kept = new Set(
    connection?.provider === provider ? connection.secrets_set : [],
  );
  const missing = (chosen?.fields ?? []).some(
    (f) =>
      f.required &&
      !(values[f.key] ?? "").trim() &&
      !(f.secret && kept.has(f.key)),
  );

  return (
    <Card>
      <CardSection className="space-y-3" id="email">
        <div className="flex items-center gap-2">
          <Mail className="size-5 text-accent" aria-hidden />
          <h3 className="font-semibold">Your email</h3>
          <span className="ms-auto">
            {connection?.state === "connected" ? (
              <Badge tone="success">Connected</Badge>
            ) : connection?.state === "action_required" ? (
              <Badge tone="warning">Needs attention</Badge>
            ) : connection ? (
              <Badge tone="info">Not finished</Badge>
            ) : (
              <Badge>Not connected</Badge>
            )}
          </span>
        </div>
        <p className="text-sm text-muted-foreground">
          Payment links, receipts and booking emails go out from your own
          address.
          {!connection && status.data?.platform_fallback
            ? " Until then they're sent from a shared address."
            : ""}
        </p>

        {status.isPending ? (
          <LoadingBlock rows={1} />
        ) : status.isError ? (
          <ErrorState
            message={errorText(status.error)}
            onRetry={() => status.refetch()}
          />
        ) : null}

        {connection && !editing ? (
          <div className="space-y-1 text-sm">
            <p className="break-words">
              Sends as{" "}
              <span className="font-medium">
                {connection.from_name
                  ? `${connection.from_name} <${connection.from_address}>`
                  : connection.from_address}
              </span>
            </p>
            {connection.state !== "connected" && connection.problem ? (
              <p className="text-warning" role="status">
                {connection.problem}
              </p>
            ) : null}
            {connection.last_checked_at ? (
              <p className="text-xs text-muted-foreground">
                Last checked {date(connection.last_checked_at)}
              </p>
            ) : null}
          </div>
        ) : null}

        {result ? (
          <p
            className={
              result.ok ? "text-sm text-success" : "text-sm text-warning"
            }
            role="status"
          >
            {result.ok ? "Email works." : result.message}
          </p>
        ) : null}

        {editing && status.data ? (
          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              save.mutate(undefined);
            }}
          >
            <Field label="Send with" htmlFor="email-provider">
              <Select
                id="email-provider"
                value={provider}
                onChange={(e) => {
                  setProvider(e.target.value);
                  setValues(
                    connection?.provider === e.target.value
                      ? connection.values
                      : {},
                  );
                }}
              >
                {status.data.providers.map((p) => (
                  <option key={p.key} value={p.key}>
                    {p.name}
                  </option>
                ))}
              </Select>
            </Field>
            {chosen?.fields.map((f) => {
              const id = `email-${f.key}`;
              const saved = f.secret && kept.has(f.key);
              return (
                <Field
                  key={f.key}
                  label={f.label}
                  htmlFor={id}
                  optional={!f.required || saved}
                  hint={
                    saved
                      ? "Saved. Leave blank to keep it."
                      : f.help || undefined
                  }
                >
                  {f.type === "select" ? (
                    <Select
                      id={id}
                      value={values[f.key] ?? f.options[0]?.value ?? ""}
                      onChange={(e) =>
                        setValues({ ...values, [f.key]: e.target.value })
                      }
                    >
                      {f.options.map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.label}
                        </option>
                      ))}
                    </Select>
                  ) : (
                    <Input
                      id={id}
                      type={INPUT_TYPE[f.type] ?? "text"}
                      value={values[f.key] ?? ""}
                      onChange={(e) =>
                        setValues({ ...values, [f.key]: e.target.value })
                      }
                      autoComplete={f.secret ? "new-password" : "off"}
                      maxLength={2000}
                    />
                  )}
                </Field>
              );
            })}
            <div className="flex flex-wrap gap-2">
              <Button type="submit" loading={save.isPending} disabled={missing}>
                Save and test
              </Button>
              <Button
                type="button"
                variant="ghost"
                onClick={() => setEditing(false)}
              >
                Cancel
              </Button>
            </div>
          </form>
        ) : null}

        {manage && !editing && status.data ? (
          <div className="flex flex-wrap gap-2">
            <Button onClick={startEdit}>
              {connection ? "Change" : "Set up email"}
            </Button>
            {connection ? (
              <Button
                variant="secondary"
                loading={test.isPending}
                onClick={() => test.mutate(undefined)}
              >
                Test
              </Button>
            ) : null}
            {connection && !confirming ? (
              <Button variant="ghost" onClick={() => setConfirming(true)}>
                Disconnect
              </Button>
            ) : null}
            {confirming ? (
              <Button
                variant="danger"
                loading={remove.isPending}
                onClick={() => remove.mutate(undefined)}
              >
                Yes, disconnect
              </Button>
            ) : null}
          </div>
        ) : null}
      </CardSection>
    </Card>
  );
}
