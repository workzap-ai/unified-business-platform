"use client";

import { useState } from "react";
import Link from "next/link";
import { Lock, TriangleAlert, UserCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, Skeleton } from "@/components/ui/display";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/overlays";
import { PageShell, RequirePermission } from "@/components/app/page";
import { PropertyList, RecordHeader } from "@/components/app/record";
import { ConfirmDialog, FormField } from "@/components/app/forms";
import { ErrorState, InlineError, Notice } from "@/components/app/states";
import { StatusBadge } from "@/components/app/status-badge";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { errorMessage } from "@/services/api-client";
import { adminService } from "@/features/admin/service";
import type { Employee } from "@/features/business/types";
import { formatDay } from "@/features/billing/utils";
import {
  jobTypeLabel,
  onboardingService,
  onboardingStatusLabel,
  type OnboardingDetail,
} from "./onboarding-service";

export function OnboardingReviewPage({ id }: { id: string }) {
  return (
    <RequirePermission permission="hr.write" area="employee onboarding">
      <Review id={id} />
    </RequirePermission>
  );
}

function Review({ id }: { id: string }) {
  const query = useScopedQuery(["onboarding", id], () =>
    onboardingService.detail(id),
  );
  const [approving, setApproving] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [revoking, setRevoking] = useState(false);
  const revoke = useScopedMutation(onboardingService.revoke, {
    invalidate: [["onboarding"]],
    success: "Link revoked",
    onSuccess: () => setRevoking(false),
  });

  if (query.isPending)
    return (
      <PageShell width="default">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="mt-6 h-[480px] rounded-xl" />
      </PageShell>
    );
  if (query.isError)
    return (
      <PageShell width="default">
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      </PageShell>
    );

  const o = query.data;
  const d = o.details;
  const title = o.full_name ?? o.invited_name ?? "Onboarding link";
  return (
    <PageShell width="default">
      <RecordHeader
        title={title}
        subtitle={o.designation ?? o.invited_designation ?? undefined}
        status={
          <StatusBadge
            status={o.effective_status}
            label={onboardingStatusLabel(o.effective_status)}
          />
        }
        meta={
          <span className="text-xs text-muted-foreground">
            Link created by {o.created_by_label} on{" "}
            {formatDay(o.created_at.slice(0, 10))}
          </span>
        }
        actions={
          <div className="flex flex-wrap gap-2">
            {o.status === "submitted" && (
              <>
                <Button variant="secondary" onClick={() => setRejecting(true)}>
                  Reject
                </Button>
                <Button
                  onClick={() => setApproving(true)}
                  disabled={Boolean(o.duplicate_employee_id)}
                >
                  <UserCheck /> Approve
                </Button>
              </>
            )}
            {o.status === "pending" && (
              <Button variant="secondary" onClick={() => setRevoking(true)}>
                Revoke link
              </Button>
            )}
            {o.employee_id && (
              <Button asChild>
                <Link href={`/hr/employees/${o.employee_id}`}>
                  Open employee
                </Link>
              </Button>
            )}
          </div>
        }
      />

      <div className="mt-4 space-y-4">
        {o.duplicate_employee_id && (
          <Notice
            tone="danger"
            icon={TriangleAlert}
            title="An employee with this CNIC already exists"
            action={
              <Button variant="secondary" size="sm" asChild>
                <Link href={`/hr/employees/${o.duplicate_employee_id}`}>
                  View employee
                </Link>
              </Button>
            }
          >
            Approving would create a duplicate record. Reject this submission or
            update the existing employee instead.
          </Notice>
        )}
        {o.effective_status === "pending" && (
          <Notice tone="info" title="Waiting for the employee">
            The link hasn&apos;t been submitted yet. It expires on{" "}
            {formatDay(o.expires_at.slice(0, 10))}.
          </Notice>
        )}
        {o.effective_status === "expired" && (
          <Notice tone="neutral" title="This link expired">
            Create a new link if the employee still needs to submit their
            details.
          </Notice>
        )}
        {o.review_note && (
          <Notice
            tone="neutral"
            title={`${onboardingStatusLabel(o.status)} by ${o.reviewed_by_label ?? "HR"}`}
          >
            {o.review_note}
          </Notice>
        )}
        {d && <Details o={o} />}
      </div>

      {d && (
        <>
          <ApproveDialog
            open={approving}
            onOpenChange={setApproving}
            onboarding={o}
          />
          <RejectDialog
            open={rejecting}
            onOpenChange={setRejecting}
            id={o.id}
          />
        </>
      )}
      <ConfirmDialog
        open={revoking}
        onOpenChange={setRevoking}
        title="Revoke this link?"
        description="The employee won't be able to submit the form. You can create a new link at any time."
        confirmLabel="Revoke link"
        destructive
        loading={revoke.isPending}
        onConfirm={() => revoke.mutate(o.id)}
      />
    </PageShell>
  );
}

function Details({ o }: { o: OnboardingDetail }) {
  const d = o.details!;
  const genderLabel =
    d.gender === "male" ? "Male" : d.gender === "female" ? "Female" : null;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader title="Personal" />
        <div className="px-4 pb-2">
          <PropertyList
            items={[
              { label: "Full name (as per CNIC)", value: d.full_name },
              { label: "Father name", value: d.father_name },
              {
                label: "CNIC",
                value: <span className="tabular">{d.cnic}</span>,
              },
              { label: "Gender", value: genderLabel },
              { label: "Date of birth", value: formatDay(d.date_of_birth) },
            ]}
          />
        </div>
      </Card>
      <Card>
        <CardHeader title="Job" />
        <div className="px-4 pb-2">
          <PropertyList
            items={[
              { label: "Designation", value: d.designation },
              {
                label: "Date of joining",
                value: formatDay(d.date_of_joining),
              },
              { label: "Job type", value: jobTypeLabel(d.job_type) },
            ]}
          />
        </div>
      </Card>
      <Card>
        <CardHeader title="Contact" />
        <div className="px-4 pb-2">
          <PropertyList
            items={[
              { label: "Email", value: d.email },
              { label: "Contact number", value: d.contact_number },
              { label: "Address", value: d.address },
              {
                label: "Emergency contact 1",
                value: `${d.emergency_contact_1.name} · ${d.emergency_contact_1.phone}`,
              },
              {
                label: "Emergency contact 2",
                value: `${d.emergency_contact_2.name} · ${d.emergency_contact_2.phone}`,
              },
            ]}
          />
        </div>
      </Card>
      <Card>
        <CardHeader
          title="Bank and tax"
          icon={o.sensitive_visible ? undefined : <Lock />}
        />
        <div className="px-4 pb-2">
          {!o.sensitive_visible && (
            <p className="pb-2 text-xs text-muted-foreground">
              Account, CNIC and NTN numbers are masked. HR members with
              sensitive access see them in full.
            </p>
          )}
          <PropertyList
            items={[
              { label: "Account title", value: d.account_title ?? null },
              { label: "Bank", value: d.bank_name ?? null },
              {
                label: "Account number / IBAN",
                value: d.bank_account_number ?? null,
              },
              { label: "NTN", value: d.ntn ?? null },
            ]}
          />
        </div>
      </Card>
      {(d.professional_reference || d.about) && (
        <Card className="lg:col-span-2">
          <CardHeader title="About" />
          <div className="px-4 pb-2">
            <PropertyList
              items={[
                {
                  label: "Professional reference",
                  value: d.professional_reference ?? null,
                },
                {
                  label: "For the announcement letter",
                  value: d.about ? (
                    <span className="whitespace-pre-line">{d.about}</span>
                  ) : null,
                },
              ]}
            />
          </div>
        </Card>
      )}
    </div>
  );
}

const EMPLOYMENT_TYPES: {
  value: Employee["employment_type"];
  label: string;
}[] = [
  { value: "full_time", label: "Full time" },
  { value: "part_time", label: "Part time" },
  { value: "contract", label: "Contract" },
  { value: "intern", label: "Intern" },
];

function ApproveDialog({
  open,
  onOpenChange,
  onboarding,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onboarding: OnboardingDetail;
}) {
  const d = onboarding.details!;
  const [employmentType, setEmploymentType] = useState<
    Employee["employment_type"]
  >(d.job_type === "freelancer" ? "contract" : "full_time");
  const [jobTitle, setJobTitle] = useState(d.designation);
  const [department, setDepartment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const departments = useScopedQuery(
    ["departments"],
    () => adminService.departments(),
    { staleTime: 60_000, enabled: open },
  );
  const approve = useScopedMutation(
    (input: Parameters<typeof onboardingService.approve>[1]) =>
      onboardingService.approve(onboarding.id, input),
    {
      invalidate: [["onboarding"], ["employees"], ["hr"]],
      toastErrors: false,
      success: `${d.full_name} added to the directory`,
      onSuccess: () => onOpenChange(false),
    },
  );
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="md">
        <DialogHeader
          title={`Approve ${d.full_name}`}
          description="Creates their employee record with the submitted details. Personal details stay encrypted."
        />
        <DialogBody className="space-y-4">
          {error && <InlineError message={error} />}
          <FormField label="Job title" htmlFor="approve-title" required>
            <Input
              id="approve-title"
              value={jobTitle}
              onChange={(e) => setJobTitle(e.target.value)}
            />
          </FormField>
          <FormField label="Employment type" htmlFor="approve-type" required>
            <NativeSelect
              id="approve-type"
              value={employmentType}
              onChange={(e) =>
                setEmploymentType(e.target.value as Employee["employment_type"])
              }
            >
              {EMPLOYMENT_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </NativeSelect>
          </FormField>
          <FormField label="Department" htmlFor="approve-dept" optional>
            <NativeSelect
              id="approve-dept"
              value={department}
              onChange={(e) => setDepartment(e.target.value)}
            >
              <option value="">No department</option>
              {(departments.data ?? []).map((dep) => (
                <option key={dep.id} value={dep.id}>
                  {dep.name}
                </option>
              ))}
            </NativeSelect>
          </FormField>
        </DialogBody>
        <DialogFooter>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            loading={approve.isPending}
            disabled={!jobTitle.trim()}
            onClick={() => {
              setError(null);
              approve.mutate(
                {
                  employment_type: employmentType,
                  job_title: jobTitle.trim(),
                  department_id: department || undefined,
                },
                {
                  onError: (e) =>
                    setError(
                      errorMessage(e, "The employee couldn't be added."),
                    ),
                },
              );
            }}
          >
            Approve and add employee
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function RejectDialog({
  open,
  onOpenChange,
  id,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  id: string;
}) {
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const reject = useScopedMutation(
    (text: string) => onboardingService.reject(id, text),
    {
      invalidate: [["onboarding"]],
      toastErrors: false,
      success: "Submission rejected",
      onSuccess: () => onOpenChange(false),
    },
  );
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="sm">
        <DialogHeader
          title="Reject submission"
          description="No employee record is created. Create a new link if they should resubmit."
        />
        <DialogBody className="space-y-3">
          {error && <InlineError message={error} />}
          <FormField label="Reason" htmlFor="reject-note" required>
            <Textarea
              id="reject-note"
              rows={3}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </FormField>
        </DialogBody>
        <DialogFooter>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="danger"
            loading={reject.isPending}
            disabled={note.trim().length < 3}
            onClick={() => {
              setError(null);
              reject.mutate(note.trim(), {
                onError: (e) => setError(errorMessage(e)),
              });
            }}
          >
            Reject
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
