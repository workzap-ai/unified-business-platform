"use client";

import { useEffect, useRef, useState } from "react";
import { CheckCircle2, Info } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/controls";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/overlays";
import { Notice } from "@/components/app/states";
import { useScopedMutation } from "@/hooks/use-scoped";
import { errorMessage } from "@/services/api-client";
import {
  AlwaysOnPanel,
  ColorSwatches,
  IconGrid,
  PreviewCard,
  TEMPLATES,
} from "./agent-form-parts";
import {
  AGENT_LIMITS as L,
  meetingAgentsService,
  refusalReasons,
  type Agent,
  type AgentCheck,
} from "./meeting-agents-service";
import { AGENTS_KEY } from "./use-agents";

/** Create a custom agent, or edit one (pass `agent`). The rules check runs while typing. */
export function AgentFormDialog({
  open,
  onOpenChange,
  agent,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  agent?: Agent | null;
  onSaved?: (agent: Agent) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg">
        <DialogHeader
          title={agent ? "Edit agent" : "New agent"}
          description="Say how pi should listen and what it should look for. You can change it any time."
        />
        {/* mounted only while open, so the form starts fresh every time */}
        <FormBody
          agent={agent ?? null}
          onClose={() => onOpenChange(false)}
          onSaved={onSaved}
        />
      </DialogContent>
    </Dialog>
  );
}

function FormBody({
  agent,
  onClose,
  onSaved,
}: {
  agent: Agent | null;
  onClose: () => void;
  onSaved?: (agent: Agent) => void;
}) {
  const [name, setName] = useState(agent?.name ?? "");
  const [tagline, setTagline] = useState(agent?.tagline ?? "");
  const [icon, setIcon] = useState(agent?.icon ?? "sparkles");
  const [color, setColor] = useState(agent?.color ?? "violet");
  const [text, setText] = useState(agent?.instructions ?? "");
  const [check, setCheck] = useState<(AgentCheck & { text: string }) | null>(
    null,
  );
  const run = useRef(0);

  const trimmed = text.trim();
  const textOk =
    trimmed.length >= L.instructionsMin && trimmed.length <= L.instructionsMax;

  // Debounced rule check: soft hints while typing, never a block by itself on a slow network.
  useEffect(() => {
    if (!textOk) return;
    const id = ++run.current;
    const t = setTimeout(() => {
      meetingAgentsService
        .check(trimmed)
        .then((r) => {
          if (run.current === id) setCheck({ ...r, text: trimmed });
        })
        .catch(() => {
          if (run.current === id) setCheck(null);
        });
    }, 600);
    return () => clearTimeout(t);
  }, [trimmed, textOk]);

  const checked = check?.text === trimmed ? check : null;
  const checking = textOk && !checked;
  const hints = checked && !checked.ok ? checked.reasons : [];

  const save = useScopedMutation(
    () => {
      const body = {
        name: name.trim(),
        tagline: tagline.trim(),
        icon,
        color,
        instructions: trimmed,
      };
      return agent
        ? meetingAgentsService.update(agent.key, body)
        : meetingAgentsService.create(body);
    },
    {
      invalidate: [AGENTS_KEY],
      toastErrors: false,
      success: agent ? "Agent saved" : "Agent created",
      onSuccess: (saved) => {
        onSaved?.(saved);
        onClose();
      },
    },
  );
  const reasons = refusalReasons(save.error);
  const otherError =
    save.error && !reasons
      ? errorMessage(save.error, "Could not save the agent. Try again.")
      : "";
  const nameOk =
    name.trim().length >= L.nameMin && name.trim().length <= L.nameMax;
  const valid = nameOk && textOk && !(checked && !checked.ok);
  const nearLimit = text.length > L.instructionsMax - 150;

  return (
    <>
      <DialogBody className="space-y-5">
        <PreviewCard name={name} tagline={tagline} icon={icon} color={color} />

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <Label htmlFor="agent-name">Name</Label>
            <Input
              id="agent-name"
              value={name}
              maxLength={L.nameMax}
              onChange={(e) => setName(e.target.value)}
              placeholder="For example: Renewal coach"
              className="h-11 sm:h-9"
            />
          </div>
          <div>
            <Label htmlFor="agent-tagline">One line about it (optional)</Label>
            <Input
              id="agent-tagline"
              value={tagline}
              maxLength={L.taglineMax}
              onChange={(e) => setTagline(e.target.value)}
              placeholder="Finds where a deal stalled"
              className="h-11 sm:h-9"
            />
          </div>
        </div>

        <div className="space-y-4">
          <div>
            <p className="mb-1.5 text-[13px] font-medium">Icon</p>
            <IconGrid value={icon} color={color} onChange={setIcon} />
          </div>
          <div>
            <p className="mb-1.5 text-[13px] font-medium">Colour</p>
            <ColorSwatches value={color} onChange={setColor} />
          </div>
        </div>

        <div>
          <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2">
            <Label htmlFor="agent-instructions" className="mb-0">
              Instructions
            </Label>
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-xs text-muted-foreground">Start from</span>
              {TEMPLATES.map((t) => (
                <button
                  key={t.label}
                  type="button"
                  onClick={() => setText(t.text)}
                  className="min-h-8 rounded-full border border-border bg-surface px-2.5 text-xs font-medium text-foreground-secondary transition-colors hover:bg-surface-muted hover:text-foreground"
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>
          <Textarea
            id="agent-instructions"
            rows={6}
            value={text}
            maxLength={L.instructionsMax}
            onChange={(e) => {
              setText(e.target.value);
              save.reset();
            }}
            aria-describedby="agent-instructions-help"
            placeholder="Tell pi what to listen for and in what tone."
          />
          <div
            id="agent-instructions-help"
            className="mt-1 flex items-start justify-between gap-3 text-xs text-muted-foreground"
          >
            <span>
              {trimmed.length < L.instructionsMin
                ? `Write at least ${L.instructionsMin} characters.`
                : "Plain sentences work best."}
            </span>
            <span
              className={cn("tabular shrink-0", nearLimit && "text-warning")}
            >
              {text.length}/{L.instructionsMax}
            </span>
          </div>

          <div aria-live="polite" className="mt-2 space-y-2">
            {hints.length > 0 && (
              <HintList title="pi suggests a small change" items={hints} />
            )}
            {reasons && reasons.length > 0 && hints.length === 0 && (
              <HintList
                title="These instructions could not be saved as written"
                items={reasons}
              />
            )}
            {checked?.ok && (
              <p className="flex items-center gap-1.5 text-xs text-success motion-safe:animate-fade-in">
                <CheckCircle2 className="size-3.5" aria-hidden="true" />
                Looks good
              </p>
            )}
            {checking && (
              <p className="text-xs text-muted-foreground">
                Checking the rules…
              </p>
            )}
          </div>
        </div>

        <AlwaysOnPanel />
        {otherError && <Notice tone="danger">{otherError}</Notice>}
      </DialogBody>
      <DialogFooter>
        <Button variant="secondary" onClick={onClose} disabled={save.isPending}>
          Cancel
        </Button>
        <Button
          loading={save.isPending}
          disabled={!valid || checking || save.isPending}
          onClick={() => save.mutate(undefined)}
        >
          {agent ? "Save changes" : "Create agent"}
        </Button>
      </DialogFooter>
    </>
  );
}

function HintList({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="rounded-lg border border-warning/25 bg-warning-soft/60 px-3 py-2 motion-safe:animate-fade-in">
      <p className="flex items-center gap-1.5 text-xs font-semibold text-warning">
        <Info className="size-3.5" aria-hidden="true" />
        {title}
      </p>
      <ul className="mt-1 list-disc space-y-0.5 pl-5 text-[12.5px] text-foreground-secondary">
        {items.map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ul>
    </div>
  );
}
