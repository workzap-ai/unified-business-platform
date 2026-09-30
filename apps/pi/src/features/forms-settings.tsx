"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardList } from "lucide-react";
import * as React from "react";

import {
  Button,
  Card,
  CardSection,
  Field,
  Input,
  Select,
} from "@/components/ui";
import { get, patch } from "@/lib/api";
import { useAction, useBusinessKey, useCan } from "@/lib/session";

type Purpose = "lead" | "booking" | "feedback";
interface Flow {
  flow_id: string;
  cta: string;
  screen: string;
}
type Config = Record<string, unknown> & {
  quiet_start?: number;
  quiet_end?: number;
  flows?: Partial<Record<Purpose, Flow>>;
};
interface Settings {
  whatsapp_config: Config;
}

const PURPOSES: [Purpose, string, string][] = [
  [
    "lead",
    "Customer details",
    "Name, need and budget before your team replies",
  ],
  ["booking", "Booking request", "Preferred service, day and time"],
  ["feedback", "Feedback", "A quick rating after a job is done"],
];
const EMPTY: Flow = { flow_id: "", cta: "", screen: "" };

/**
 * Quiet hours for reminders and the WhatsApp forms (Flows) Pi may send. Saved into the
 * latest settings so it never overwrites the reminder form on the same page.
 */
export function RemindersAndForms() {
  const key = useBusinessKey();
  const can = useCan();
  const client = useQueryClient();
  const settings = useQuery({
    queryKey: key(["settings"]),
    queryFn: () => get<Settings>("/pi/settings"),
  });
  const config = settings.data?.whatsapp_config;
  const [quiet, setQuiet] = React.useState<[number, number] | null>(null);
  const [flows, setFlows] = React.useState<Partial<
    Record<Purpose, Flow>
  > | null>(null);
  const hours = quiet ?? [config?.quiet_start ?? 21, config?.quiet_end ?? 9];
  const current = flows ?? config?.flows ?? {};
  const save = useAction(
    async () => {
      const latest =
        client.getQueryData<Settings>(key(["settings"]))?.whatsapp_config ?? {};
      const cleaned = Object.fromEntries(
        Object.entries(current).filter(([, f]) => f && f.flow_id.trim()),
      );
      return patch<Settings>("/pi/settings/whatsapp_config", {
        value: {
          ...latest,
          quiet_start: hours[0],
          quiet_end: hours[1],
          flows: cleaned,
        },
      });
    },
    {
      success: "Saved",
      onSuccess: (saved) => {
        client.setQueryData(key(["settings"]), saved);
        setQuiet(null);
        setFlows(null);
      },
    },
  );
  if (!config || !can("pi.settings.manage")) return null;
  const setFlow = (purpose: Purpose, patchValue: Partial<Flow>) =>
    setFlows({
      ...current,
      [purpose]: { ...(current[purpose] ?? EMPTY), ...patchValue },
    });
  const hourOptions = Array.from({ length: 24 }, (_, h) => h);
  const valid = Object.values(current).every(
    (f) =>
      !f ||
      !f.flow_id.trim() ||
      (/^[0-9]{5,32}$/.test(f.flow_id.trim()) &&
        f.cta.trim().length >= 1 &&
        f.cta.trim().length <= 20 &&
        /^[A-Z][A-Z0-9_]{0,49}$/.test(f.screen.trim())),
  );
  return (
    <Card className="mt-6">
      <CardSection className="space-y-5">
        <div>
          <h2 className="font-semibold">Quiet hours</h2>
          <p className="text-sm text-muted-foreground">
            Pi never sends reminders during these hours (your time zone). Choose
            the same time twice to turn quiet hours off.
          </p>
          <div className="mt-3 grid max-w-md grid-cols-2 gap-3">
            <Field label="From" htmlFor="quiet-from">
              <Select
                id="quiet-from"
                value={String(hours[0])}
                onChange={(e) => setQuiet([Number(e.target.value), hours[1]])}
              >
                {hourOptions.map((h) => (
                  <option key={h} value={h}>{`${h}:00`}</option>
                ))}
              </Select>
            </Field>
            <Field label="Until" htmlFor="quiet-until">
              <Select
                id="quiet-until"
                value={String(hours[1])}
                onChange={(e) => setQuiet([hours[0], Number(e.target.value)])}
              >
                {hourOptions.map((h) => (
                  <option key={h} value={h}>{`${h}:00`}</option>
                ))}
              </Select>
            </Field>
          </div>
        </div>
        <div>
          <h2 className="flex items-center gap-2 font-semibold">
            <ClipboardList className="size-4 text-accent" aria-hidden />{" "}
            WhatsApp forms
          </h2>
          <p className="text-sm text-muted-foreground">
            Build and publish a form (Flow) in your WhatsApp Manager, then add
            it here. Pi sends it only while a customer is chatting, and only if
            you turn on WhatsApp forms in My Pi → Tools.
          </p>
          <div className="mt-3 space-y-3">
            {PURPOSES.map(([purpose, title, hint]) => {
              const flow = current[purpose] ?? EMPTY;
              return (
                <fieldset
                  key={purpose}
                  className="grid gap-3 rounded-lg border border-border p-3 sm:grid-cols-3"
                >
                  <legend className="px-1 text-sm font-medium">
                    {title}{" "}
                    <span className="font-normal text-muted-foreground">
                      · {hint}
                    </span>
                  </legend>
                  <Field label="Flow ID" htmlFor={`flow-${purpose}`} optional>
                    <Input
                      id={`flow-${purpose}`}
                      inputMode="numeric"
                      value={flow.flow_id}
                      onChange={(e) =>
                        setFlow(purpose, { flow_id: e.target.value })
                      }
                    />
                  </Field>
                  <Field label="Button text" htmlFor={`cta-${purpose}`}>
                    <Input
                      id={`cta-${purpose}`}
                      maxLength={20}
                      value={flow.cta}
                      placeholder="Share details"
                      onChange={(e) =>
                        setFlow(purpose, { cta: e.target.value })
                      }
                    />
                  </Field>
                  <Field label="First screen" htmlFor={`screen-${purpose}`}>
                    <Input
                      id={`screen-${purpose}`}
                      value={flow.screen}
                      placeholder="DETAILS"
                      onChange={(e) =>
                        setFlow(purpose, {
                          screen: e.target.value.toUpperCase(),
                        })
                      }
                    />
                  </Field>
                </fieldset>
              );
            })}
          </div>
        </div>
        <Button
          loading={save.isPending}
          disabled={!valid}
          onClick={() => save.mutate(undefined)}
        >
          Save
        </Button>
      </CardSection>
    </Card>
  );
}
