"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  Blocks,
  ChevronRight,
  Layers,
  Moon,
  ShieldCheck,
  Sun,
  Users,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input, NativeSelect } from "@/components/ui/input";
import { Switch } from "@/components/ui/controls";
import { Skeleton } from "@/components/ui/display";
import {
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import {
  FormActions,
  FormField,
  FormSection,
  useUnsavedChangesWarning,
} from "@/components/app/forms";
import { ErrorState, InlineError } from "@/components/app/states";
import { useTheme } from "@/components/shell/theme";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import { errorMessage } from "@/services/api-client";
import type { BusinessSettings } from "@/features/business/types";
import { adminService } from "./service";

export function SettingsPage() {
  return (
    <RequirePermission permission="settings.manage" area="workspace settings">
      <PageShell width="default">
        <PageHeader
          title="Settings"
          description="Organization details, business defaults and how the app looks for you."
        />
        <OrganizationSection />
        <BusinessSettingsForm />
        <AppearanceSection />
        <WhereThingsLive />
      </PageShell>
    </RequirePermission>
  );
}

/* Organization ---------------------------------------------------------------------- */

const orgSchema = z.object({
  name: z
    .string()
    .trim()
    .min(2, "Use at least 2 characters")
    .max(200, "Keep the name under 200 characters"),
});

function OrganizationSection() {
  const { can } = useSession();
  const canRename = can("admin.organization.manage");
  const org = useScopedQuery(["admin", "organization"], () =>
    adminService.organization(),
  );
  const form = useForm<z.infer<typeof orgSchema>>({
    resolver: zodResolver(orgSchema),
    defaultValues: { name: "" },
  });
  const [serverError, setServerError] = useState<string | null>(null);
  const { reset } = form;
  useEffect(() => {
    if (org.data) reset({ name: org.data.name });
  }, [org.data, reset]);
  const rename = useScopedMutation(
    (name: string) => adminService.renameOrganization(name),
    {
      invalidate: [["admin", "organization"]],
      success: "Organization renamed",
      onSuccess: (result) => reset({ name: result.name }),
    },
  );
  const e = form.formState.errors;

  return (
    <FormSection
      title="Organization"
      description="The name members see in the workspace switcher, documents and PI replies."
    >
      {org.isPending ? (
        <Skeleton className="h-16" />
      ) : org.isError ? (
        <ErrorState
          compact
          error={org.error}
          onRetry={() => void org.refetch()}
        />
      ) : (
        <form
          noValidate
          onSubmit={form.handleSubmit(async (values) => {
            setServerError(null);
            try {
              await rename.mutateAsync(values.name.trim());
            } catch (error) {
              setServerError(
                errorMessage(error, "The organization could not be renamed."),
              );
            }
          })}
          className="space-y-3"
        >
          <FormField
            label="Organization name"
            htmlFor="org-name"
            required
            error={e.name}
            help={
              canRename
                ? `Workspace URL key: ${org.data.slug}`
                : "Only members who can manage the organization can rename it."
            }
          >
            <div className="flex flex-col gap-2 sm:flex-row">
              <Input
                id="org-name"
                autoComplete="organization"
                disabled={!canRename || rename.isPending}
                aria-invalid={!!e.name || undefined}
                aria-describedby={e.name ? "org-name-error" : "org-name-help"}
                {...form.register("name")}
              />
              {canRename && (
                <Button
                  type="submit"
                  variant="secondary"
                  loading={rename.isPending}
                  disabled={!form.formState.isDirty || rename.isPending}
                >
                  Rename
                </Button>
              )}
            </div>
          </FormField>
          {serverError && <InlineError message={serverError} />}
        </form>
      )}
    </FormSection>
  );
}

/* Business settings --------------------------------------------------------------------- */

const INT = /^\d+$/;
const PERCENT = /^\d{1,3}(\.\d{1,2})?$/;
const MONEY = /^\d+(\.\d{1,2})?$/;

const intField = (label: string, min: number, max: number) =>
  z
    .string()
    .trim()
    .refine((v) => INT.test(v), `${label} must be a whole number`)
    .refine(
      (v) => !INT.test(v) || (Number(v) >= min && Number(v) <= max),
      `${label} must be between ${min} and ${max}`,
    );

const percentField = (label: string) =>
  z
    .string()
    .trim()
    .refine(
      (v) => PERCENT.test(v),
      `Enter ${label} as a percentage, e.g. 17 or 7.5`,
    )
    .refine(
      (v) => !PERCENT.test(v) || Number(v) <= 100,
      `${label} can't exceed 100%`,
    );

const businessSchema = z.object({
  business_type: z.enum([
    "service_business",
    "product_business",
    "hybrid_business",
  ]),
  default_currency: z
    .string()
    .trim()
    .refine(
      (v) => /^[A-Za-z]{3}$/.test(v),
      "Use a 3-letter ISO currency code, e.g. USD or PKR",
    ),
  tax_rate: percentField("the tax rate"),
  auto_invoice_on_order_confirm: z.boolean(),
  low_stock_threshold: intField("Threshold", 0, 100000),
  invoice_due_days: intField("Due days", 0, 365),
  quote_validity_days: intField("Validity", 1, 365),
  quote_approval_threshold: z
    .string()
    .trim()
    .refine(
      (v) => !v || MONEY.test(v),
      "Enter an amount like 50000 or 49999.99, or leave empty",
    ),
  max_discount_rate: percentField("the maximum discount"),
});
type BusinessValues = z.infer<typeof businessSchema>;

/** 0–1 decimal string → percentage text without trailing zeros ("0.1700" → "17"). */
function toPercent(rate: string) {
  return String(Number((Number(rate) * 100).toFixed(2)));
}
/** Percentage text → 0–1 decimal string with 4 dp ("17.5" → "0.1750"). */
function fromPercent(percent: string) {
  const [whole = "0", fraction = ""] = percent.trim().split(".");
  const basisPoints =
    Number(whole) * 100 + Number((fraction + "00").slice(0, 2));
  return (basisPoints / 10000).toFixed(4);
}

function toForm(s: BusinessSettings): BusinessValues {
  return {
    business_type: s.business_type,
    default_currency: s.default_currency,
    tax_rate: toPercent(s.tax_rate),
    auto_invoice_on_order_confirm: s.auto_invoice_on_order_confirm,
    low_stock_threshold: String(s.low_stock_threshold),
    invoice_due_days: String(s.invoice_due_days),
    quote_validity_days: String(s.quote_validity_days),
    quote_approval_threshold: s.quote_approval_threshold ?? "",
    max_discount_rate: toPercent(s.max_discount_rate),
  };
}

function toInput(v: BusinessValues): Partial<BusinessSettings> {
  return {
    business_type: v.business_type,
    default_currency: v.default_currency.trim().toUpperCase(),
    tax_rate: fromPercent(v.tax_rate),
    auto_invoice_on_order_confirm: v.auto_invoice_on_order_confirm,
    low_stock_threshold: Number(v.low_stock_threshold),
    invoice_due_days: Number(v.invoice_due_days),
    quote_validity_days: Number(v.quote_validity_days),
    quote_approval_threshold: v.quote_approval_threshold.trim() || null,
    max_discount_rate: fromPercent(v.max_discount_rate),
  };
}

function BusinessSettingsForm() {
  const settings = useScopedQuery(["admin", "business-settings"], () =>
    adminService.businessSettings(),
  );
  const form = useForm<BusinessValues>({
    resolver: zodResolver(businessSchema),
    defaultValues: {
      business_type: "service_business",
      default_currency: "",
      tax_rate: "0",
      auto_invoice_on_order_confirm: false,
      low_stock_threshold: "0",
      invoice_due_days: "0",
      quote_validity_days: "1",
      quote_approval_threshold: "",
      max_discount_rate: "0",
    },
  });
  const { reset, formState } = form;
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  useEffect(() => {
    if (settings.data) reset(toForm(settings.data));
  }, [settings.data, reset]);
  useUnsavedChangesWarning(formState.isDirty);
  const save = useScopedMutation(
    (input: Partial<BusinessSettings>) =>
      adminService.updateBusinessSettings(input),
    {
      invalidate: [["admin", "business-settings"]],
      success: "Business settings saved",
      onSuccess: (result) => {
        reset(toForm(result));
        setSavedAt(Date.now());
      },
    },
  );
  const e = formState.errors;
  const field = (name: keyof BusinessValues) => ({
    id: `bs-${name}`,
    "aria-invalid": !!e[name] || undefined,
    "aria-describedby": e[name] ? `bs-${name}-error` : `bs-${name}-help`,
    disabled: save.isPending,
  });

  if (settings.isPending) {
    return (
      <FormSection
        title="Business settings"
        description="Defaults applied to new quotes, orders and invoices."
      >
        <Skeleton className="h-64" />
      </FormSection>
    );
  }
  if (settings.isError) {
    return (
      <FormSection title="Business settings">
        <ErrorState
          compact
          error={settings.error}
          onRetry={() => void settings.refetch()}
        />
      </FormSection>
    );
  }

  return (
    <form
      noValidate
      onSubmit={form.handleSubmit(async (values) => {
        setServerError(null);
        try {
          await save.mutateAsync(toInput(values));
        } catch (error) {
          setServerError(errorMessage(error, "Settings could not be saved."));
        }
      })}
    >
      <FormSection
        title="Business capabilities"
        description="Choose how this environment operates. Service businesses do not need inventory."
      >
        <FormField label="Business type" htmlFor="business-type" required>
          <NativeSelect id="business-type" {...form.register("business_type")}>
            <option value="service_business">Service business</option>
            <option value="product_business">Product business</option>
            <option value="hybrid_business">Services and products</option>
          </NativeSelect>
        </FormField>
      </FormSection>
      <FormSection
        title="Money & tax"
        description="Currency and tax used for new documents. Existing documents keep their values."
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField
            label="Default currency"
            htmlFor="bs-default_currency"
            required
            error={e.default_currency}
            help="ISO 4217 code, e.g. USD, PKR, AED."
          >
            <Input
              {...field("default_currency")}
              maxLength={3}
              className="uppercase"
              autoComplete="off"
              {...form.register("default_currency")}
            />
          </FormField>
          <FormField
            label="Tax rate (%)"
            htmlFor="bs-tax_rate"
            required
            error={e.tax_rate}
            help="Applied to quote and order subtotals."
          >
            <Input
              {...field("tax_rate")}
              inputMode="decimal"
              {...form.register("tax_rate")}
            />
          </FormField>
        </div>
      </FormSection>

      <FormSection
        title="Orders & invoices"
        description="How orders turn into invoices and when payment is due."
      >
        <div className="flex items-start justify-between gap-4 rounded-lg border border-border px-3.5 py-3">
          <div>
            <label
              htmlFor="bs-auto_invoice_on_order_confirm"
              className="text-[13px] font-medium"
            >
              Invoice automatically when an order is confirmed
            </label>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Creates and issues an invoice from the confirmed order lines.
            </p>
          </div>
          <Controller
            control={form.control}
            name="auto_invoice_on_order_confirm"
            render={({ field: f }) => (
              <Switch
                id="bs-auto_invoice_on_order_confirm"
                checked={f.value}
                onCheckedChange={f.onChange}
                disabled={save.isPending}
              />
            )}
          />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField
            label="Invoice due (days)"
            htmlFor="bs-invoice_due_days"
            required
            error={e.invoice_due_days}
            help="Days after issue until an invoice is due."
          >
            <Input
              {...field("invoice_due_days")}
              inputMode="numeric"
              {...form.register("invoice_due_days")}
            />
          </FormField>
          <FormField
            label="Low-stock threshold"
            htmlFor="bs-low_stock_threshold"
            required
            error={e.low_stock_threshold}
            help="Default for items without their own threshold."
          >
            <Input
              {...field("low_stock_threshold")}
              inputMode="numeric"
              {...form.register("low_stock_threshold")}
            />
          </FormField>
        </div>
      </FormSection>

      <FormSection
        title="Quotes"
        description="Validity, approval and discount rules. PI follows the same rules."
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField
            label="Quote validity (days)"
            htmlFor="bs-quote_validity_days"
            required
            error={e.quote_validity_days}
            help="How long a new quote stays valid."
          >
            <Input
              {...field("quote_validity_days")}
              inputMode="numeric"
              {...form.register("quote_validity_days")}
            />
          </FormField>
          <FormField
            label="Maximum discount (%)"
            htmlFor="bs-max_discount_rate"
            required
            error={e.max_discount_rate}
            help="Larger discounts are rejected."
          >
            <Input
              {...field("max_discount_rate")}
              inputMode="decimal"
              {...form.register("max_discount_rate")}
            />
          </FormField>
        </div>
        <FormField
          label="Approval threshold"
          htmlFor="bs-quote_approval_threshold"
          optional
          error={e.quote_approval_threshold}
          help={`Quotes above this total (in ${settings.data.default_currency}) need approval. Leave empty to not require approval by amount.`}
        >
          <Input
            {...field("quote_approval_threshold")}
            inputMode="decimal"
            placeholder="No threshold"
            className="sm:max-w-60"
            {...form.register("quote_approval_threshold")}
          />
        </FormField>
        {serverError && <InlineError message={serverError} />}
      </FormSection>

      <FormActions
        dirty={formState.isDirty}
        saving={save.isPending}
        savedAt={savedAt}
        submitLabel="Save settings"
        onCancel={
          formState.isDirty ? () => reset(toForm(settings.data)) : undefined
        }
      />
    </form>
  );
}

/* Appearance ----------------------------------------------------------------------------- */

function AppearanceSection() {
  const { theme, setTheme } = useTheme();
  const options: {
    value: "light" | "dark";
    label: string;
    icon: LucideIcon;
  }[] = [
    { value: "light", label: "Light", icon: Sun },
    { value: "dark", label: "Dark", icon: Moon },
  ];
  return (
    <FormSection title="Appearance" description="Saved on this device only.">
      <div
        role="radiogroup"
        aria-label="Theme"
        className="grid max-w-sm grid-cols-2 gap-2"
      >
        {options.map((o) => {
          const active = theme === o.value;
          return (
            <button
              key={o.value}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => setTheme(o.value)}
              className={cn(
                "flex items-center gap-2 rounded-lg border px-3 py-2.5 text-[13px] font-medium transition-colors focus-visible:outline-2 focus-visible:outline-ring",
                active
                  ? "border-primary bg-primary-soft text-primary-soft-foreground"
                  : "border-border hover:bg-surface-muted",
              )}
            >
              <o.icon className="size-4" aria-hidden="true" /> {o.label}
            </button>
          );
        })}
      </div>
    </FormSection>
  );
}

/* Where things live ----------------------------------------------------------------------- */

function WhereThingsLive() {
  const { can } = useSession();
  const links: {
    label: string;
    description: string;
    href: string;
    icon: LucideIcon;
    permission: string;
  }[] = [
    {
      label: "Members",
      description: "Invite people and assign roles",
      href: "/settings/members",
      icon: Users,
      permission: "admin.members.read",
    },
    {
      label: "Roles & permissions",
      description: "What each role can see and do",
      href: "/settings/roles",
      icon: ShieldCheck,
      permission: "admin.members.read",
    },
    {
      label: "Environments",
      description: "Production, staging and development data",
      href: "/settings/environments",
      icon: Layers,
      permission: "admin.environments.manage",
    },
    {
      label: "Platform products",
      description: "Install and enable products such as PI",
      href: "/settings/products",
      icon: Blocks,
      permission: "admin.products.manage",
    },
  ];
  const visible = links.filter((l) => can(l.permission));
  if (!visible.length) return null;
  return (
    <FormSection
      title="Where things live"
      description="Other administration lives on its own pages."
    >
      <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border">
        {visible.map((l) => (
          <li key={l.href}>
            <Link
              href={l.href}
              className="flex items-center gap-3 px-3.5 py-3 hover:bg-surface-muted"
            >
              <l.icon
                className="size-4 text-muted-foreground"
                aria-hidden="true"
              />
              <span className="min-w-0 flex-1">
                <span className="block text-[13px] font-medium">{l.label}</span>
                <span className="block text-xs text-muted-foreground">
                  {l.description}
                </span>
              </span>
              <ChevronRight
                className="size-4 text-muted-foreground"
                aria-hidden="true"
              />
            </Link>
          </li>
        ))}
      </ul>
    </FormSection>
  );
}
