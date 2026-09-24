"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ChevronRight, Power } from "lucide-react";
import { cn } from "@/lib/utils";
import { humanize } from "@/lib/format";
import { Card, Skeleton } from "@/components/ui/display";
import { Label, Switch } from "@/components/ui/controls";
import { NativeSelect } from "@/components/ui/input";
import {
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import { ConfirmDialog } from "@/components/app/forms";
import { ErrorState } from "@/components/app/states";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { piService } from "../../service";
import type { PiSettings } from "../../types";
import { MODEL_ALIASES, PROVIDER_LABELS, piKeys } from "../shared";
import { SETTINGS_SECTIONS, type SettingsSection } from "../sections";
import {
  AgentConfigurationPanel,
  AiConfigForm,
  BusinessHoursForm,
  HandoffRulesForm,
  KnowledgeConfigForm,
  PermissionsForm,
  ProviderConfigForm,
  ResponseRulesForm,
  ToolPermissionsForm,
  WhatsAppConfigForm,
} from "./settings-forms";

const alias = (v: string) =>
  MODEL_ALIASES.find((m) => m.value === v)?.label ?? v;

function summary(slug: SettingsSection, s: PiSettings): string {
  switch (slug) {
    case "business-hours": {
      if (!s.business_hours.enabled) return "Replies at any time";
      const open = Object.values(s.business_hours.days).filter(
        (d) => d.open,
      ).length;
      return `${open} days a week · ${s.timezone.replace(/_/g, " ")}`;
    }
    case "response-rules":
      return `${s.response_rules.language === "auto" ? "Auto language" : humanize(s.response_rules.language)} · ${humanize(s.response_rules.tone)} · max ${s.response_rules.max_reply_chars} chars`;
    case "ai-configuration":
      return `Routing ${alias(s.ai_config.router_alias)} · replies ${alias(s.ai_config.reply_alias)} · temperature ${Number(s.ai_config.temperature).toFixed(2)}`;
    case "provider-configuration":
      return `${s.provider_config.order.map((p) => PROVIDER_LABELS[p]).join(" → ")} → handoff`;
    case "tool-permissions": {
      const values = Object.values(s.tool_permissions);
      return `${values.filter(Boolean).length} of ${values.length} tools on`;
    }
    case "agent-configuration":
      return "Enable or disable agents";
    case "handoff-rules":
      return `${s.handoff_rules.keywords.length} keywords · threshold ${Number(s.handoff_rules.low_confidence_threshold).toFixed(2)}`;
    case "knowledge-configuration":
      return `${s.knowledge_config.semantic_enabled ? "Semantic + full-text" : "Full-text search"} · top ${s.knowledge_config.top_k}`;
    case "whatsapp-configuration":
      return (
        [
          s.whatsapp_config.send_read_receipts && "read receipts",
          s.whatsapp_config.media_voice && "voice notes",
          s.whatsapp_config.media_images && "images",
        ]
          .filter(Boolean)
          .join(" · ") || "Text only"
      );
    case "permissions":
      return `${s.permissions.length} roles`;
  }
}

/* Overview ------------------------------------------------------------------------- */

export function PiSettingsOverviewPage() {
  return (
    <RequirePermission permission="pi.settings.manage" area="PI settings">
      <Overview />
    </RequirePermission>
  );
}

function Overview() {
  const settings = useScopedQuery(piKeys.settings, () => piService.settings());
  const [confirmOff, setConfirmOff] = useState(false);
  const toggle = useScopedMutation(
    (on: boolean) => piService.updateSettings("auto_reply_enabled", on),
    {
      invalidate: [[...piKeys.settings], [...piKeys.overview]],
      success: (s) =>
        s.auto_reply_enabled ? "Auto-replies turned on" : "Auto-replies paused",
      onSuccess: () => setConfirmOff(false),
    },
  );
  const s = settings.data;
  return (
    <PageShell width="default">
      <PageHeader
        title="Settings"
        description="How PI behaves in this workspace and environment."
      />
      {settings.isError ? (
        <Card>
          <ErrorState
            error={settings.error}
            onRetry={() => void settings.refetch()}
          />
        </Card>
      ) : !s ? (
        <div className="space-y-3">
          <Skeleton className="h-24 rounded-xl" />
          <Skeleton className="h-96 rounded-xl" />
        </div>
      ) : (
        <>
          <Card
            className={cn(
              "mb-4 p-4 sm:p-5",
              !s.auto_reply_enabled && "border-warning/40",
            )}
          >
            <div className="flex items-start gap-3">
              <span
                className={cn(
                  "flex size-9 shrink-0 items-center justify-center rounded-lg",
                  s.auto_reply_enabled
                    ? "bg-pi-soft text-pi"
                    : "bg-warning-soft text-warning",
                )}
              >
                <Power className="size-4.5" aria-hidden="true" />
              </span>
              <div className="min-w-0 flex-1">
                <label
                  htmlFor="auto-reply"
                  className="text-[14px] font-semibold"
                >
                  Auto-replies
                </label>
                <p
                  id="auto-reply-description"
                  className="mt-0.5 text-[13px] text-muted-foreground"
                >
                  {s.auto_reply_enabled
                    ? "PI answers customers automatically. Turn off to have your team reply to every message."
                    : "Paused. PI still receives messages and shows them in the inbox, but doesn't reply."}
                </p>
              </div>
              <Switch
                id="auto-reply"
                aria-describedby="auto-reply-description"
                checked={s.auto_reply_enabled}
                disabled={toggle.isPending}
                onCheckedChange={(on) =>
                  on ? toggle.mutate(true) : setConfirmOff(true)
                }
              />
            </div>
          </Card>
          <Card>
            <ul className="divide-y divide-border">
              {SETTINGS_SECTIONS.map((section) => (
                <li key={section.slug}>
                  <Link
                    href={`/pi/settings/${section.slug}`}
                    className="flex items-center gap-3 px-4 py-3 hover:bg-surface-muted/60 focus-visible:outline-2 focus-visible:outline-ring"
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block text-[13.5px] font-medium">
                        {section.label}
                      </span>
                      <span className="block text-xs text-muted-foreground">
                        {section.description}
                      </span>
                    </span>
                    <span className="hidden max-w-[45%] truncate text-right text-xs text-foreground-secondary sm:block">
                      {summary(section.slug, s)}
                    </span>
                    <ChevronRight
                      className="size-4 shrink-0 text-muted-foreground"
                      aria-hidden="true"
                    />
                  </Link>
                </li>
              ))}
            </ul>
          </Card>
        </>
      )}
      <ConfirmDialog
        open={confirmOff}
        onOpenChange={setConfirmOff}
        title="Pause auto-replies?"
        description="PI stops replying to customers in this environment."
        consequences={[
          "Incoming messages still arrive in the PI inbox, but nobody is answered automatically.",
          "Your team needs to reply to every conversation until you turn this back on.",
          "Pending order confirmations wait for a human reply.",
        ]}
        confirmLabel="Pause auto-replies"
        destructive
        loading={toggle.isPending}
        onConfirm={() => toggle.mutate(false)}
      />
    </PageShell>
  );
}

/* Section page ----------------------------------------------------------------------- */

export function PiSettingsSectionPage({
  section,
}: {
  section: SettingsSection;
}) {
  return (
    <RequirePermission permission="pi.settings.manage" area="PI settings">
      <Section section={section} />
    </RequirePermission>
  );
}

function Section({ section }: { section: SettingsSection }) {
  const router = useRouter();
  const pathname = usePathname();
  const settings = useScopedQuery(piKeys.settings, () => piService.settings());
  const meta = SETTINGS_SECTIONS.find((s) => s.slug === section)!;
  const s = settings.data;

  return (
    <PageShell>
      <PageHeader
        title={meta.label}
        description={meta.description}
        eyebrow={
          <Link href="/pi/settings" className="hover:text-foreground">
            Settings
          </Link>
        }
      />
      <div className="mb-4 lg:hidden">
        <Label htmlFor="settings-section" className="sr-only">
          Settings section
        </Label>
        <NativeSelect
          id="settings-section"
          value={section}
          onChange={(e) => router.push(`/pi/settings/${e.target.value}`)}
        >
          {SETTINGS_SECTIONS.map((x) => (
            <option key={x.slug} value={x.slug}>
              {x.label}
            </option>
          ))}
        </NativeSelect>
      </div>
      <div className="grid gap-6 lg:grid-cols-[220px_minmax(0,1fr)]">
        <nav aria-label="Settings sections" className="hidden lg:block">
          <ul className="sticky top-4 space-y-0.5">
            {SETTINGS_SECTIONS.map((x) => {
              const href = `/pi/settings/${x.slug}`;
              const active = pathname === href;
              return (
                <li key={x.slug}>
                  <Link
                    href={href}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "block rounded-md px-2.5 py-1.5 text-[13px] font-medium transition-colors",
                      active
                        ? "bg-surface-muted text-foreground"
                        : "text-muted-foreground hover:bg-surface-muted/60 hover:text-foreground",
                    )}
                  >
                    {x.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
        <div className="min-w-0">
          {section === "agent-configuration" ? (
            <AgentConfigurationPanel />
          ) : settings.isError ? (
            <Card>
              <ErrorState
                error={settings.error}
                onRetry={() => void settings.refetch()}
              />
            </Card>
          ) : !s ? (
            <Skeleton className="h-96 rounded-xl" />
          ) : (
            <SectionForm section={section} settings={s} />
          )}
        </div>
      </div>
    </PageShell>
  );
}

function SectionForm({
  section,
  settings,
}: {
  section: SettingsSection;
  settings: PiSettings;
}) {
  switch (section) {
    case "business-hours":
      return <BusinessHoursForm settings={settings} />;
    case "response-rules":
      return <ResponseRulesForm settings={settings} />;
    case "ai-configuration":
      return <AiConfigForm settings={settings} />;
    case "provider-configuration":
      return <ProviderConfigForm settings={settings} />;
    case "tool-permissions":
      return <ToolPermissionsForm settings={settings} />;
    case "handoff-rules":
      return <HandoffRulesForm settings={settings} />;
    case "knowledge-configuration":
      return <KnowledgeConfigForm settings={settings} />;
    case "whatsapp-configuration":
      return <WhatsAppConfigForm settings={settings} />;
    case "permissions":
      return <PermissionsForm settings={settings} />;
    case "agent-configuration":
      return <AgentConfigurationPanel />;
  }
}
