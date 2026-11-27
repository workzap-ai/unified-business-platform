"use client";

import * as RadioGroupPrimitive from "@radix-ui/react-radio-group";
import { Check, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";
import { stylesFor, iconFor, AgentAvatar } from "./agent-avatar";
import {
  AGENT_COLORS,
  AGENT_ICONS,
  type AgentColor,
  type AgentIcon,
} from "./meeting-agents-service";

/** Starter texts: each only sets tone and focus, never a price or a promise. */
export const TEMPLATES: { label: string; text: string }[] = [
  {
    label: "Sales coach",
    text: "Listen like a sales coach. Notice what the customer needs, what worries them and where the conversation slowed down. Point out the moments a clear next step was missed.",
  },
  {
    label: "Negotiation coach",
    text: "Listen like a negotiation coach. Notice what each side wants, where they disagree and what each side gave up. Suggest calm ways to find common ground.",
  },
  {
    label: "Customer care",
    text: "Listen like a customer care lead. Notice complaints, feelings and anything left unresolved. Keep a warm, patient tone and list what still needs a follow-up.",
  },
  {
    label: "Trainer",
    text: "Listen like a trainer. Notice what was explained well, what confused people and which questions came up twice. Suggest simple ways to explain it better next time.",
  },
];

export const ALWAYS_ON = [
  "pi says it is an AI first",
  "No prices and no promises of a result",
  "Never asks for a card, password, OTP or ID number",
  "No legal, medical, financial or tax advice",
  "Roles, not names",
];

export function AlwaysOnPanel() {
  return (
    <section
      aria-labelledby="always-on-title"
      className="rounded-xl border border-border bg-surface-muted/70 p-3.5"
    >
      <h3
        id="always-on-title"
        className="flex items-center gap-2 text-[13px] font-semibold"
      >
        <ShieldCheck className="size-4 text-primary" aria-hidden="true" />
        Always on
      </h3>
      <ul className="mt-2 space-y-1">
        {ALWAYS_ON.map((r) => (
          <li
            key={r}
            className="flex items-start gap-2 text-[12.5px] text-foreground-secondary"
          >
            <Check
              className="mt-0.5 size-3.5 shrink-0 text-primary"
              aria-hidden="true"
            />
            {r}
          </li>
        ))}
      </ul>
      <p className="mt-2.5 text-xs text-muted-foreground">
        Your agent changes tone and focus. It cannot switch these off.
      </p>
    </section>
  );
}

export function IconGrid({
  value,
  color,
  onChange,
}: {
  value: string;
  color: string;
  onChange: (icon: AgentIcon) => void;
}) {
  return (
    <RadioGroupPrimitive.Root
      aria-label="Icon"
      value={value}
      onValueChange={(v) => onChange(v as AgentIcon)}
      className="flex flex-wrap gap-1.5"
    >
      {AGENT_ICONS.map((key) => {
        const Icon = iconFor(key);
        return (
          <RadioGroupPrimitive.Item
            key={key}
            value={key}
            aria-label={key.replace("-", " ")}
            className={cn(
              "grid size-11 place-items-center rounded-lg border border-border bg-surface text-muted-foreground transition-colors hover:bg-surface-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring data-[state=checked]:border-transparent data-[state=checked]:bg-gradient-to-br data-[state=checked]:ring-2",
              "data-[state=checked]:text-inherit",
              value === key && stylesFor(color).tile,
            )}
          >
            <Icon className="size-[18px]" aria-hidden="true" />
          </RadioGroupPrimitive.Item>
        );
      })}
    </RadioGroupPrimitive.Root>
  );
}

export function ColorSwatches({
  value,
  onChange,
}: {
  value: string;
  onChange: (color: AgentColor) => void;
}) {
  return (
    <RadioGroupPrimitive.Root
      aria-label="Colour"
      value={value}
      onValueChange={(v) => onChange(v as AgentColor)}
      className="flex flex-wrap gap-2"
    >
      {AGENT_COLORS.map((key) => (
        <RadioGroupPrimitive.Item
          key={key}
          value={key}
          aria-label={key}
          className="grid size-11 place-items-center rounded-full focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          <span
            className={cn(
              "grid size-8 place-items-center rounded-full bg-gradient-to-br ring-1 ring-inset transition-transform",
              stylesFor(key).tile,
              value === key &&
                cn(
                  "scale-105 ring-2 ring-offset-2 ring-offset-surface",
                  stylesFor(key).ring,
                ),
            )}
          >
            {value === key && <Check className="size-4" aria-hidden="true" />}
          </span>
        </RadioGroupPrimitive.Item>
      ))}
    </RadioGroupPrimitive.Root>
  );
}

export function PreviewCard({
  name,
  tagline,
  icon,
  color,
}: {
  name: string;
  tagline: string;
  icon: string;
  color: string;
}) {
  return (
    <div
      aria-label="Preview"
      className="flex items-center gap-3 rounded-xl border border-border bg-gradient-to-br from-surface to-surface-muted p-3.5 shadow-sm"
    >
      <AgentAvatar icon={icon} color={color} size="lg" />
      <div className="min-w-0">
        <p className="truncate text-[15px] font-semibold">
          {name.trim() || "Your agent"}
        </p>
        <p className="truncate text-[13px] text-muted-foreground">
          {tagline.trim() || "One line about what it looks for"}
        </p>
      </div>
    </div>
  );
}
