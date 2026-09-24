"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Lock } from "lucide-react";
import { Skeleton } from "@/components/ui/display";
import {
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import {
  FormActions,
  FormSection,
  useUnsavedChangesWarning,
} from "@/components/app/forms";
import { InlineError, Notice } from "@/components/app/states";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { errorMessage } from "@/services/api-client";
import { useSession } from "@/features/auth/session-provider";
import { adminService } from "@/features/admin/service";
import { hrService } from "./service";
import {
  CompensationFields,
  PersonFields,
  RoleFields,
  employeeDefaults,
  employeeFormSchema,
  toEmployeeInput,
  type EmployeeFormValues,
} from "./employee-fields";

export function EmployeeNewPage() {
  return (
    <RequirePermission permission="hr.write" area="adding employees">
      <EmployeeNewForm />
    </RequirePermission>
  );
}

function EmployeeNewForm() {
  const { can } = useSession();
  const sensitive = can("hr.sensitive");
  // Compensation defaults to the workspace currency, so wait for it before mounting the form.
  const settings = useScopedQuery(
    ["settings", "business"],
    () => adminService.businessSettings(),
    {
      staleTime: 60_000,
      enabled: sensitive,
    },
  );
  if (sensitive && settings.isPending) {
    return (
      <PageShell width="default">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="mt-2 h-4 w-80 max-w-full" />
        <Skeleton className="mt-6 h-[560px] rounded-xl" />
      </PageShell>
    );
  }
  return (
    <EmployeeForm
      sensitive={sensitive}
      currency={settings.data?.default_currency ?? ""}
    />
  );
}

function EmployeeForm({
  sensitive,
  currency,
}: {
  sensitive: boolean;
  currency: string;
}) {
  const router = useRouter();
  const [serverError, setServerError] = useState<string | null>(null);
  const [created, setCreated] = useState(false);
  const form = useForm<EmployeeFormValues>({
    resolver: zodResolver(employeeFormSchema),
    defaultValues: employeeDefaults(undefined, currency),
    mode: "onTouched",
  });
  const { handleSubmit, formState } = form;

  const create = useScopedMutation(hrService.create, {
    invalidate: [["employees"], ["hr"]],
    success: (e) => `${e.full_name} added`,
    onSuccess: (e) => {
      setCreated(true);
      router.push(`/hr/employees/${e.id}`);
    },
  });
  useUnsavedChangesWarning(formState.isDirty && !created);
  const saving = create.isPending || created;

  const onSubmit = handleSubmit((values) => {
    setServerError(null);
    create.mutate(toEmployeeInput(values, sensitive), {
      onError: (e) =>
        setServerError(errorMessage(e, "The employee couldn't be added.")),
    });
  });

  return (
    <PageShell width="default">
      <PageHeader
        eyebrow={
          <Link href="/hr/employees" className="hover:text-foreground">
            Employees
          </Link>
        }
        title="Add employee"
        description="Create a directory record. New employees start as active."
      />
      <form onSubmit={onSubmit} noValidate>
        {serverError && (
          <div className="mb-4">
            <InlineError message={serverError} />
          </div>
        )}
        <div className="rounded-xl border border-border bg-surface p-4 shadow-sm sm:p-6">
          <FormSection
            title="Person"
            description="How to identify and reach them."
          >
            <PersonFields form={form} disabled={saving} />
          </FormSection>
          <FormSection
            title="Role"
            description="Where they sit and who they report to."
          >
            <RoleFields form={form} disabled={saving} />
          </FormSection>
          <FormSection
            title="Compensation"
            description="Restricted to HR members with sensitive access."
          >
            {sensitive ? (
              <CompensationFields form={form} disabled={saving} />
            ) : (
              <Notice
                tone="neutral"
                icon={Lock}
                title="Compensation is restricted"
              >
                Only members with HR sensitive access can set or view salaries.
                Save the record now and ask an HR administrator to add
                compensation.
              </Notice>
            )}
          </FormSection>
        </div>
        <FormActions
          dirty={formState.isDirty}
          saving={saving}
          onCancel={() => router.push("/hr/employees")}
          submitLabel="Add employee"
        />
      </form>
    </PageShell>
  );
}
