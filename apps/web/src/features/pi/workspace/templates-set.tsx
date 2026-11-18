"use client";

/**
 * The recommended Nori templates and the one-click "create the missing ones" dialog. Every text is
 * Utility, says pi is an AI, has no price or payment detail, and ends in one question (pi's rules).
 * Meta approves each one (minutes to hours); nothing can be sent with it until it is approved.
 * Roman Urdu is written in Latin letters and filed under en_US: Meta has no Roman Urdu language.
 */
import { useState } from "react";
import { Check, Layers } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/display";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/overlays";
import { useScopedMutation } from "@/hooks/use-scoped";
import { errorMessage } from "@/services/api-client";
import {
  piTemplatesService,
  type NewTemplate,
  type Template,
} from "../templates-service";

export type PresetTemplate = NewTemplate & { label: string };

const EN = "en_US";

export const NORI_SET: PresetTemplate[] = [
  {
    label: "Nori welcome (English)",
    name: "nori_welcome_en",
    language: EN,
    category: "UTILITY",
    body: "Hello {{1}}, welcome to nori. I'm pi, an AI assistant from Workzap. I can answer questions about your workspace and pass your requests to the Workzap team. What would you like help with first?",
    examples: ["Ayesha"],
  },
  {
    label: "Nori welcome (Roman Urdu)",
    name: "nori_welcome_ur",
    language: EN,
    category: "UTILITY",
    body: "Assalam o Alaikum {{1}}, nori mein khush aamdeed. Main pi hoon, Workzap ka AI assistant. Main aap ke workspace ke sawalon ka jawab de sakta hoon aur aap ki zaroorat Workzap team tak pohancha sakta hoon. Aap sab se pehle kis cheez mein madad chahte hain?",
    examples: ["Ayesha"],
  },
  {
    label: "Trial ending (English)",
    name: "nori_trial_reminder_en",
    language: EN,
    category: "UTILITY",
    body: "Hello {{1}}, this is pi, an AI assistant from Workzap. The trial for {{2}} ends on {{3}}. Would you like help choosing a plan in nori?",
    examples: ["Ayesha", "Mendeez Demo", "20 November"],
  },
  {
    label: "Trial ending (Roman Urdu)",
    name: "nori_trial_reminder_ur",
    language: EN,
    category: "UTILITY",
    body: "Assalam o Alaikum {{1}}, main pi hoon, Workzap ka AI assistant. {{2}} ka trial {{3}} ko khatam hoga. Kya aap ko nori ka plan chunne mein madad chahiye?",
    examples: ["Ayesha", "Mendeez Demo", "20 November"],
  },
  {
    label: "Trial ended (English)",
    name: "nori_trial_ended_en",
    language: EN,
    category: "UTILITY",
    body: "Hello {{1}}, this is pi, an AI assistant from Workzap. The trial for {{2}} ended on {{3}}. Your data is safe. Would you like help continuing in nori?",
    examples: ["Ayesha", "Mendeez Demo", "20 November"],
  },
  {
    label: "Trial ended (Roman Urdu)",
    name: "nori_trial_ended_ur",
    language: EN,
    category: "UTILITY",
    body: "Assalam o Alaikum {{1}}, main pi hoon, Workzap ka AI assistant. {{2}} ka trial {{3}} ko khatam ho gaya. Aap ka data mehfooz hai. Kya aap nori jari rakhne mein madad chahte hain?",
    examples: ["Ayesha", "Mendeez Demo", "20 November"],
  },
  {
    label: "Subscription ending (English)",
    name: "nori_subscription_ending_en",
    language: EN,
    category: "UTILITY",
    body: "Hello {{1}}, this is pi, an AI assistant from Workzap. The nori subscription for {{2}} ends on {{3}}. Would you like help renewing it?",
    examples: ["Ayesha", "Mendeez Demo", "20 December"],
  },
  {
    label: "Subscription ending (Roman Urdu)",
    name: "nori_subscription_ending_ur",
    language: EN,
    category: "UTILITY",
    body: "Assalam o Alaikum {{1}}, main pi hoon, Workzap ka AI assistant. {{2}} ki nori subscription {{3}} ko khatam hogi. Kya aap ko tajdeed mein madad chahiye?",
    examples: ["Ayesha", "Mendeez Demo", "20 December"],
  },
  {
    label: "Credits running low (English)",
    name: "nori_credits_low_en",
    language: EN,
    category: "UTILITY",
    body: "Hello {{1}}, this is pi, an AI assistant from Workzap. {{2}} has {{3}} credits left in nori. Would you like help adding more?",
    examples: ["Ayesha", "Mendeez Demo", "120"],
  },
  {
    label: "Credits running low (Roman Urdu)",
    name: "nori_credits_low_ur",
    language: EN,
    category: "UTILITY",
    body: "Assalam o Alaikum {{1}}, main pi hoon, Workzap ka AI assistant. {{2}} ke nori mein {{3}} credits bache hain. Kya aap ko mazeed credits lene mein madad chahiye?",
    examples: ["Ayesha", "Mendeez Demo", "120"],
  },
];

type Outcome = { name: string; ok: boolean; note: string };

/** Which of the recommended templates this number does not have yet, and a button to send them. */
export function SetDialog({
  existing,
  onClose,
}: {
  existing: Template[];
  onClose: () => void;
}) {
  const have = new Set(existing.map((t) => `${t.name}|${t.language}`));
  const missing = NORI_SET.filter((t) => !have.has(`${t.name}|${t.language}`));
  const [done, setDone] = useState<Outcome[] | null>(null);
  const create = useScopedMutation(
    async () => {
      const out: Outcome[] = [];
      for (const t of missing) {
        try {
          await piTemplatesService.create({
            name: t.name,
            language: t.language,
            category: t.category,
            body: t.body,
            examples: t.examples,
          });
          out.push({ name: t.name, ok: true, note: "Sent to Meta" });
        } catch (e) {
          out.push({ name: t.name, ok: false, note: errorMessage(e) });
        }
      }
      return out;
    },
    {
      invalidate: [["pi", "templates"]],
      toastErrors: false,
      onSuccess: setDone,
    },
  );
  return (
    <Dialog
      open
      onOpenChange={(next) => !next && !create.isPending && onClose()}
    >
      <DialogContent size="lg">
        <DialogHeader
          title="Nori template set"
          description="Welcome, trial, subscription and credits messages, in English and Roman Urdu. Meta reviews each one, usually within minutes to hours."
        />
        <DialogBody className="space-y-3">
          <ul className="divide-y divide-border rounded-md border border-border text-[13px]">
            {NORI_SET.map((t) => {
              const result = done?.find((o) => o.name === t.name);
              const there = have.has(`${t.name}|${t.language}`);
              return (
                <li key={t.name} className="space-y-1 p-2.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{t.label}</span>
                    <span className="text-xs text-muted-foreground">
                      {t.name}
                    </span>
                    {result ? (
                      <Badge tone={result.ok ? "success" : "danger"}>
                        {result.ok ? "Sent to Meta" : result.note}
                      </Badge>
                    ) : there ? (
                      <Badge tone="success">
                        <Check /> Already there
                      </Badge>
                    ) : (
                      <Badge tone="warning">Missing</Badge>
                    )}
                  </div>
                  <p className="text-xs break-words whitespace-pre-wrap text-muted-foreground">
                    {t.body}
                  </p>
                </li>
              );
            })}
          </ul>
          <p className="text-[13px] text-muted-foreground">
            They only become usable once Meta approves them. Watch the status on
            the Templates page. The ones that exist are left alone.
          </p>
        </DialogBody>
        <DialogFooter>
          <Button
            variant="secondary"
            onClick={onClose}
            disabled={create.isPending}
          >
            {done ? "Close" : "Cancel"}
          </Button>
          {!done && (
            <Button
              loading={create.isPending}
              disabled={missing.length === 0}
              onClick={() => create.mutate(undefined)}
            >
              <Layers />{" "}
              {missing.length === 0
                ? "Nothing missing"
                : `Send ${missing.length} to Meta`}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
