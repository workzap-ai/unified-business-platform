"use client";

import { Lock } from "lucide-react";
import { Card, CardHeader, Skeleton } from "@/components/ui/display";
import { PropertyList } from "@/components/app/record";
import { ErrorState, Notice } from "@/components/app/states";
import { useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import type { Employee } from "@/features/business/types";
import { formatDay } from "@/features/billing/utils";
import { jobTypeLabel, onboardingService } from "./onboarding-service";

/** Details captured through the onboarding form. Decrypted only for hr.sensitive. */
export function PersonalDetailsCard({ employee }: { employee: Employee }) {
  const { can } = useSession();
  const sensitive = can("hr.sensitive");
  const query = useScopedQuery(
    ["employees", employee.id, "personal"],
    () => onboardingService.personal(employee.id),
    { enabled: sensitive && Boolean(employee.has_personal_details) },
  );
  if (!employee.has_personal_details && !employee.work_arrangement) return null;

  const contact = (c?: { name: string; phone: string } | null) =>
    c ? `${c.name} · ${c.phone}` : null;
  const gender =
    employee.gender === "male"
      ? "Male"
      : employee.gender === "female"
        ? "Female"
        : null;

  return (
    <Card>
      <CardHeader title="Personal details" icon={<Lock />} />
      <div className="px-4 pb-2">
        <PropertyList
          columns={2}
          items={[
            {
              label: "Work arrangement",
              value: employee.work_arrangement
                ? jobTypeLabel(employee.work_arrangement)
                : null,
            },
            { label: "Gender", value: gender },
          ]}
        />
      </div>
      {!employee.has_personal_details ? null : !sensitive ? (
        <div className="px-4 pb-4">
          <Notice tone="neutral" icon={Lock}>
            CNIC, family, address, emergency and bank details are visible to HR
            with sensitive access.
          </Notice>
        </div>
      ) : query.isPending ? (
        <div className="space-y-2 px-4 pb-4">
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-4 w-1/2" />
        </div>
      ) : query.isError ? (
        <div className="px-4 pb-4">
          <ErrorState
            error={query.error}
            onRetry={() => void query.refetch()}
            compact
          />
        </div>
      ) : (
        <div className="px-4 pb-2">
          <PropertyList
            columns={2}
            items={[
              { label: "Father name", value: query.data.father_name ?? null },
              {
                label: "CNIC",
                value: query.data.cnic ? (
                  <span className="tabular">{query.data.cnic}</span>
                ) : null,
              },
              {
                label: "Date of birth",
                value: employee.date_of_birth
                  ? formatDay(employee.date_of_birth)
                  : null,
              },
              { label: "Address", value: query.data.address ?? null },
              {
                label: "Emergency contact 1",
                value: contact(query.data.emergency_contact_1),
              },
              {
                label: "Emergency contact 2",
                value: contact(query.data.emergency_contact_2),
              },
              {
                label: "Account title",
                value: query.data.account_title ?? null,
              },
              { label: "Bank", value: query.data.bank_name ?? null },
              {
                label: "Account number / IBAN",
                value: query.data.bank_account_number ?? null,
              },
              { label: "NTN", value: query.data.ntn ?? null },
              {
                label: "Professional reference",
                value: query.data.professional_reference ?? null,
              },
              {
                label: "About",
                value: query.data.about ? (
                  <span className="whitespace-pre-line">
                    {query.data.about}
                  </span>
                ) : null,
              },
            ]}
          />
        </div>
      )}
    </Card>
  );
}
