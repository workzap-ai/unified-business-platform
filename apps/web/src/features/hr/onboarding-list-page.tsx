"use client";

import { useState } from "react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Check, Copy, Link2, SearchX, UserPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input, NativeSelect } from "@/components/ui/input";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/overlays";
import {
  ModuleNav,
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import {
  DataTable,
  Pagination,
  type Column,
} from "@/components/app/data-table";
import { FilterBar, FilterSelect } from "@/components/app/filters";
import { FormField } from "@/components/app/forms";
import { EmptyState, InlineError, Notice } from "@/components/app/states";
import { StatusBadge } from "@/components/app/status-badge";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useUrlState } from "@/hooks/use-url-state";
import { ApiError, errorMessage } from "@/services/api-client";
import { formatDay } from "@/features/billing/utils";
import {
  ONBOARDING_STATUSES,
  jobTypeLabel,
  onboardingService,
  onboardingStatusLabel,
  type LinkCreated,
  type OnboardingSummary,
} from "./onboarding-service";

const PAGE_SIZE = 25;

const COLUMNS: Column<OnboardingSummary>[] = [
  {
    key: "person",
    header: "Person",
    cell: (o) => (
      <Link href={`/hr/onboarding/${o.id}`} className="block min-w-0">
        <span className="block truncate font-medium hover:underline">
          {o.full_name ?? o.invited_name ?? "Not submitted yet"}
        </span>
        <span className="block truncate text-xs text-muted-foreground">
          {o.designation ?? o.invited_designation ?? "—"}
        </span>
      </Link>
    ),
  },
  {
    key: "status",
    header: "Status",
    cell: (o) => (
      <StatusBadge
        status={o.effective_status}
        label={onboardingStatusLabel(o.effective_status)}
      />
    ),
  },
  {
    key: "job_type",
    header: "Job type",
    cell: (o) => jobTypeLabel(o.job_type),
    hideBelow: "md",
  },
  {
    key: "joining",
    header: "Joining",
    cell: (o) =>
      o.date_of_joining ? (
        <span className="tabular whitespace-nowrap">
          {formatDay(o.date_of_joining)}
        </span>
      ) : (
        <span className="text-muted-foreground">—</span>
      ),
    hideBelow: "lg",
  },
  {
    key: "expires",
    header: "Link expires",
    cell: (o) => (
      <span className="tabular whitespace-nowrap">
        {formatDay(o.expires_at.slice(0, 10))}
      </span>
    ),
    hideBelow: "sm",
  },
];

export function OnboardingListPage() {
  return (
    <RequirePermission permission="hr.write" area="employee onboarding">
      <OnboardingList />
    </RequirePermission>
  );
}

function OnboardingList() {
  const [state, setState] = useUrlState({ status: "", page: "1", create: "" });
  const [creating, setCreating] = useState(state.create === "1");
  const page = Math.max(1, Number(state.page) || 1);
  const params = {
    page,
    pageSize: PAGE_SIZE,
    status: state.status || undefined,
  };
  const query = useScopedQuery(
    ["onboarding", params],
    () => onboardingService.list(params),
    { placeholderData: (previous) => previous },
  );

  const createButton = (
    <Button onClick={() => setCreating(true)}>
      <UserPlus /> Create onboarding link
    </Button>
  );

  return (
    <PageShell>
      <PageHeader
        title="Onboarding"
        description="Send new employees a link to fill in their details, then review and approve them into the directory."
        actions={createButton}
      />
      <ModuleNav moduleKey="hr" />
      <FilterBar
        activeCount={state.status ? 1 : 0}
        onClear={() => setState({ status: "" })}
      >
        <FilterSelect
          label="Status"
          value={state.status}
          onChange={(status) => setState({ status })}
          options={ONBOARDING_STATUSES.map((s) => ({
            value: s.value,
            label: s.label,
          }))}
        />
      </FilterBar>
      <DataTable
        columns={COLUMNS}
        rows={query.data?.items ?? []}
        getRowId={(o) => o.id}
        rowHref={(o) => `/hr/onboarding/${o.id}`}
        loading={query.isPending}
        error={query.isError ? query.error : undefined}
        onRetry={() => void query.refetch()}
        caption="Onboarding links"
        empty={
          state.status ? (
            <EmptyState
              icon={SearchX}
              title="Nothing with this status"
              description="Try another status filter."
            />
          ) : (
            <EmptyState
              icon={Link2}
              title="No onboarding links yet"
              description="Create a link and share it with a new employee on WhatsApp or email. They fill in their CNIC, contact, emergency and bank details; you approve them into the directory."
              action={createButton}
            />
          )
        }
      />
      {query.data && query.data.total > PAGE_SIZE && (
        <Pagination
          page={page}
          pageSize={PAGE_SIZE}
          total={query.data.total}
          onPage={(p) => setState({ page: String(p) }, { resetPage: false })}
          className="mt-4"
        />
      )}
      <CreateLinkDialog
        open={creating}
        onOpenChange={(open) => {
          setCreating(open);
          if (!open && state.create)
            setState({ create: "" }, { resetPage: false });
        }}
      />
    </PageShell>
  );
}

const linkSchema = z.object({
  invited_name: z.string().trim().max(160).optional(),
  invited_email: z
    .string()
    .trim()
    .email("Enter a valid email address")
    .optional()
    .or(z.literal("")),
  invited_designation: z.string().trim().max(120).optional(),
  expires_in_days: z.string(),
});
type LinkValues = z.infer<typeof linkSchema>;

function CreateLinkDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [created, setCreated] = useState<LinkCreated | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const form = useForm<LinkValues>({
    resolver: zodResolver(linkSchema),
    defaultValues: {
      invited_name: "",
      invited_email: "",
      invited_designation: "",
      expires_in_days: "7",
    },
  });
  const create = useScopedMutation(onboardingService.createLink, {
    invalidate: [["onboarding"]],
    toastErrors: false,
    onSuccess: (link) => setCreated(link),
  });

  const url =
    created && typeof window !== "undefined"
      ? `${window.location.origin}${created.path}`
      : "";

  function close(next: boolean) {
    if (!next) {
      setCreated(null);
      setError(null);
      setCopied(false);
      form.reset();
    }
    onOpenChange(next);
  }

  const onSubmit = form.handleSubmit((v) => {
    setError(null);
    create.mutate(
      {
        invited_name: v.invited_name || undefined,
        invited_email: v.invited_email || undefined,
        invited_designation: v.invited_designation || undefined,
        expires_in_days: Number(v.expires_in_days),
      },
      {
        onError: (e) =>
          setError(
            e instanceof ApiError && e.code === "ENCRYPTION_NOT_CONFIGURED"
              ? "Secure storage isn't configured on the server yet (SECRETS_ENCRYPTION_KEY). Ask your administrator before sharing onboarding links."
              : errorMessage(e, "The link couldn't be created."),
          ),
      },
    );
  });

  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  const e = form.formState.errors;
  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent size="md">
        <DialogHeader
          title={created ? "Share this link" : "Create onboarding link"}
          description={
            created
              ? "Send it to the new employee. It works once and expires automatically."
              : "Optional details are pre-filled on the form for the employee."
          }
        />
        {created ? (
          <>
            <DialogBody className="space-y-3">
              <div className="flex gap-2">
                <Input
                  readOnly
                  value={url}
                  aria-label="Onboarding link"
                  onFocus={(ev) => ev.currentTarget.select()}
                />
                <Button variant="secondary" onClick={copy}>
                  {copied ? <Check /> : <Copy />}
                  {copied ? "Copied" : "Copy"}
                </Button>
              </div>
              <Notice tone="warning">
                Copy it now: for security the full link can&apos;t be shown
                again. Anyone with the link can submit the form until it expires
                on {formatDay(created.expires_at.slice(0, 10))}.
              </Notice>
            </DialogBody>
            <DialogFooter>
              <Button onClick={() => close(false)}>Done</Button>
            </DialogFooter>
          </>
        ) : (
          <form onSubmit={onSubmit} noValidate>
            <DialogBody className="space-y-4">
              {error && <InlineError message={error} />}
              <FormField
                label="Employee name"
                htmlFor="invited_name"
                optional
                error={e.invited_name}
              >
                <Input id="invited_name" {...form.register("invited_name")} />
              </FormField>
              <FormField
                label="Email"
                htmlFor="invited_email"
                optional
                error={e.invited_email}
              >
                <Input
                  id="invited_email"
                  type="email"
                  {...form.register("invited_email")}
                />
              </FormField>
              <FormField
                label="Designation"
                htmlFor="invited_designation"
                optional
                error={e.invited_designation}
              >
                <Input
                  id="invited_designation"
                  {...form.register("invited_designation")}
                />
              </FormField>
              <FormField label="Link valid for" htmlFor="expires_in_days">
                <NativeSelect
                  id="expires_in_days"
                  {...form.register("expires_in_days")}
                >
                  <option value="1">1 day</option>
                  <option value="3">3 days</option>
                  <option value="7">7 days</option>
                  <option value="14">14 days</option>
                  <option value="30">30 days</option>
                </NativeSelect>
              </FormField>
            </DialogBody>
            <DialogFooter>
              <Button
                type="button"
                variant="secondary"
                onClick={() => close(false)}
              >
                Cancel
              </Button>
              <Button type="submit" loading={create.isPending}>
                Create link
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
