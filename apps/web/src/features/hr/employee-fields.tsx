"use client";

import type { UseFormReturn } from "react-hook-form";
import { z } from "zod";
import { Input, NativeSelect } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/display";
import { FormField } from "@/components/app/forms";
import { useScopedQuery } from "@/hooks/use-scoped";
import { adminService } from "@/features/admin/service";
import type { Employee, EmployeeInput } from "@/features/business/types";
import { MONEY_PATTERN } from "@/features/billing/utils";
import { hrService } from "./service";
import { CURRENCIES, EMPLOYMENT_TYPES, ROSTER_PAGE_SIZE } from "./utils";

const emailFormat = z.email();

export const employeeFormSchema = z
  .object({
    full_name: z
      .string()
      .trim()
      .min(1, "Enter the person's full name")
      .max(200, "Keep it under 200 characters"),
    email: z
      .string()
      .trim()
      .max(254, "That email is too long")
      .refine(
        (v): boolean => !v || emailFormat.safeParse(v).success,
        "Enter a valid email address",
      ),
    phone: z.string().trim().max(40, "That phone number is too long"),
    job_title: z
      .string()
      .trim()
      .min(1, "Enter a job title")
      .max(200, "Keep it under 200 characters"),
    department_id: z.string(),
    manager_id: z.string(),
    employment_type: z.enum(["full_time", "part_time", "contract", "intern"]),
    hire_date: z.string().min(1, "Choose the hire date"),
    salary: z
      .string()
      .trim()
      .refine(
        (v): boolean => !v || MONEY_PATTERN.test(v),
        "Use an amount like 4500.00",
      ),
    salary_currency: z.string(),
  })
  .superRefine((v, ctx) => {
    if (v.salary && !v.salary_currency) {
      ctx.addIssue({
        code: "custom",
        path: ["salary_currency"],
        message: "Choose the salary currency",
      });
    }
  });

export type EmployeeFormValues = z.infer<typeof employeeFormSchema>;

export function employeeDefaults(
  employee?: Employee,
  currency = "",
): EmployeeFormValues {
  return {
    full_name: employee?.full_name ?? "",
    email: employee?.email ?? "",
    phone: employee?.phone ?? "",
    job_title: employee?.job_title ?? "",
    department_id: employee?.department_id ?? "",
    manager_id: employee?.manager_id ?? "",
    employment_type: employee?.employment_type ?? "full_time",
    hire_date: employee?.hire_date ?? "",
    salary: employee?.salary ?? "",
    salary_currency: employee?.salary_currency ?? currency,
  };
}

export function toEmployeeInput(
  values: EmployeeFormValues,
  includeCompensation: boolean,
): EmployeeInput {
  const input: EmployeeInput = {
    full_name: values.full_name.trim(),
    email: values.email.trim() || null,
    phone: values.phone.trim() || null,
    job_title: values.job_title.trim(),
    department_id: values.department_id || null,
    manager_id: values.manager_id || null,
    employment_type: values.employment_type,
    hire_date: values.hire_date,
  };
  if (includeCompensation) {
    input.salary = values.salary.trim() || null;
    input.salary_currency = values.salary.trim()
      ? values.salary_currency || null
      : null;
  }
  return input;
}

type FieldProps = {
  form: UseFormReturn<EmployeeFormValues>;
  disabled?: boolean;
  idPrefix?: string;
};

export function PersonFields({ form, disabled, idPrefix = "emp" }: FieldProps) {
  const { register, formState } = form;
  const { errors } = formState;
  return (
    <>
      <FormField
        label="Full name"
        htmlFor={`${idPrefix}-name`}
        required
        error={errors.full_name?.message}
      >
        <Input
          id={`${idPrefix}-name`}
          autoComplete="off"
          aria-invalid={Boolean(errors.full_name) || undefined}
          disabled={disabled}
          {...register("full_name")}
        />
      </FormField>
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField
          label="Work email"
          htmlFor={`${idPrefix}-email`}
          optional
          error={errors.email?.message}
        >
          <Input
            id={`${idPrefix}-email`}
            type="email"
            autoComplete="off"
            aria-invalid={Boolean(errors.email) || undefined}
            disabled={disabled}
            {...register("email")}
          />
        </FormField>
        <FormField
          label="Phone"
          htmlFor={`${idPrefix}-phone`}
          optional
          error={errors.phone?.message}
        >
          <Input
            id={`${idPrefix}-phone`}
            type="tel"
            autoComplete="off"
            aria-invalid={Boolean(errors.phone) || undefined}
            disabled={disabled}
            {...register("phone")}
          />
        </FormField>
      </div>
    </>
  );
}

export function RoleFields({
  form,
  disabled,
  idPrefix = "emp",
  employeeId,
}: FieldProps & { employeeId?: string }) {
  const { register, formState } = form;
  const { errors } = formState;
  const departments = useScopedQuery(
    ["departments"],
    () => adminService.departments(),
    { staleTime: 60_000 },
  );
  const roster = useScopedQuery(
    ["employees", { pageSize: ROSTER_PAGE_SIZE }],
    () => hrService.employees({ pageSize: ROSTER_PAGE_SIZE }),
  );
  const managers = (roster.data?.items ?? []).filter(
    (e) => e.id !== employeeId && e.status !== "terminated",
  );
  // Selects mount only once their options exist, so saved values are applied correctly.
  const optionsReady = !departments.isPending && !roster.isPending;

  return (
    <>
      <FormField
        label="Job title"
        htmlFor={`${idPrefix}-title`}
        required
        error={errors.job_title?.message}
      >
        <Input
          id={`${idPrefix}-title`}
          placeholder="e.g. Operations Manager"
          aria-invalid={Boolean(errors.job_title) || undefined}
          disabled={disabled}
          {...register("job_title")}
        />
      </FormField>
      {!optionsReady ? (
        <div className="grid gap-4 sm:grid-cols-2" aria-busy="true">
          <Skeleton className="h-[58px]" />
          <Skeleton className="h-[58px]" />
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField
            label="Department"
            htmlFor={`${idPrefix}-department`}
            optional
            help={
              departments.isError
                ? "Departments couldn't be loaded."
                : undefined
            }
          >
            <NativeSelect
              id={`${idPrefix}-department`}
              disabled={disabled}
              {...register("department_id")}
            >
              <option value="">No department</option>
              {(departments.data ?? []).map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </NativeSelect>
          </FormField>
          <FormField
            label="Manager"
            htmlFor={`${idPrefix}-manager`}
            optional
            help={
              roster.isError
                ? "The employee list couldn't be loaded."
                : undefined
            }
          >
            <NativeSelect
              id={`${idPrefix}-manager`}
              disabled={disabled}
              {...register("manager_id")}
            >
              <option value="">No manager</option>
              {managers.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.full_name} — {m.job_title}
                </option>
              ))}
            </NativeSelect>
          </FormField>
        </div>
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField
          label="Employment type"
          htmlFor={`${idPrefix}-type`}
          required
          error={errors.employment_type?.message}
        >
          <NativeSelect
            id={`${idPrefix}-type`}
            disabled={disabled}
            {...register("employment_type")}
          >
            {EMPLOYMENT_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </NativeSelect>
        </FormField>
        <FormField
          label="Hire date"
          htmlFor={`${idPrefix}-hire`}
          required
          error={errors.hire_date?.message}
          help="A future date marks an upcoming starter."
        >
          <Input
            id={`${idPrefix}-hire`}
            type="date"
            aria-invalid={Boolean(errors.hire_date) || undefined}
            disabled={disabled}
            {...register("hire_date")}
          />
        </FormField>
      </div>
    </>
  );
}

export function CompensationFields({
  form,
  disabled,
  idPrefix = "emp",
}: FieldProps) {
  const { register, formState } = form;
  const { errors } = formState;
  const initial = formState.defaultValues?.salary_currency;
  const currencies =
    initial && !CURRENCIES.includes(initial)
      ? [initial, ...CURRENCIES]
      : CURRENCIES;
  return (
    <div className="grid gap-4 sm:grid-cols-[1fr_140px]">
      <FormField
        label="Salary"
        htmlFor={`${idPrefix}-salary`}
        optional
        error={errors.salary?.message}
        help="Annual gross amount. Only members with HR sensitive access can see it."
      >
        <Input
          id={`${idPrefix}-salary`}
          inputMode="decimal"
          placeholder="0.00"
          className="tabular"
          aria-invalid={Boolean(errors.salary) || undefined}
          disabled={disabled}
          {...register("salary")}
        />
      </FormField>
      <FormField
        label="Currency"
        htmlFor={`${idPrefix}-currency`}
        error={errors.salary_currency?.message}
      >
        <NativeSelect
          id={`${idPrefix}-currency`}
          aria-invalid={Boolean(errors.salary_currency) || undefined}
          disabled={disabled}
          {...register("salary_currency")}
        >
          <option value="">Choose…</option>
          {currencies.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </NativeSelect>
      </FormField>
    </div>
  );
}
