import { z } from "zod";
import {
  apiRequest,
  ApiError,
  pageSchema,
  type Page,
} from "@/services/api-client";
import { demoDelay, select } from "@/lib/data-mode";
import { demoBusiness } from "@/demo/business";
import { demoCollection, demoId, paginate } from "@/demo/store";
import { demoSession, DEMO_TENANTS } from "@/demo/workspace";
import type { Employee } from "@/features/business/types";

// ------------------------------------------------------------------ contract

export const JOB_TYPES = [
  { value: "onsite", label: "Onsite" },
  { value: "hybrid", label: "Hybrid" },
  { value: "remote", label: "Remote" },
  { value: "freelancer", label: "Freelancer" },
] as const;
export type JobType = (typeof JOB_TYPES)[number]["value"];

export const ONBOARDING_STATUSES = [
  { value: "pending", label: "Awaiting employee" },
  { value: "submitted", label: "Ready for review" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
  { value: "expired", label: "Expired" },
  { value: "revoked", label: "Revoked" },
] as const;

const ts = z.string();
const contactSchema = z.object({ name: z.string(), phone: z.string() });

export const submissionDetailsSchema = z.object({
  full_name: z.string(),
  father_name: z.string(),
  cnic: z.string(),
  email: z.string(),
  designation: z.string(),
  gender: z.enum(["male", "female"]).nullable().optional(),
  date_of_joining: z.string(),
  date_of_birth: z.string(),
  job_type: z.enum(["onsite", "hybrid", "remote", "freelancer"]),
  contact_number: z.string(),
  emergency_contact_1: contactSchema,
  emergency_contact_2: contactSchema,
  address: z.string(),
  account_title: z.string().nullable().optional(),
  bank_name: z.string().nullable().optional(),
  bank_account_number: z.string().nullable().optional(),
  ntn: z.string().nullable().optional(),
  professional_reference: z.string().nullable().optional(),
  about: z.string().nullable().optional(),
});
export type SubmissionDetails = z.infer<typeof submissionDetailsSchema>;

export const onboardingSummarySchema = z.object({
  id: z.string(),
  status: z.enum(["pending", "submitted", "approved", "rejected", "revoked"]),
  effective_status: z.enum([
    "pending",
    "submitted",
    "approved",
    "rejected",
    "revoked",
    "expired",
  ]),
  invited_name: z.string().nullable(),
  invited_email: z.string().nullable(),
  invited_designation: z.string().nullable(),
  full_name: z.string().nullable(),
  email: z.string().nullable(),
  designation: z.string().nullable(),
  date_of_joining: z.string().nullable(),
  job_type: z.string().nullable(),
  expires_at: ts,
  created_by_label: z.string(),
  created_at: ts,
  submitted_at: ts.nullable(),
  reviewed_at: ts.nullable(),
  reviewed_by_label: z.string().nullable(),
  review_note: z.string().nullable(),
  employee_id: z.string().nullable(),
});
export type OnboardingSummary = z.infer<typeof onboardingSummarySchema>;

export const onboardingDetailSchema = onboardingSummarySchema.extend({
  details: submissionDetailsSchema.nullable(),
  sensitive_visible: z.boolean(),
  duplicate_employee_id: z.string().nullable(),
});
export type OnboardingDetail = z.infer<typeof onboardingDetailSchema>;

export const linkCreatedSchema = z.object({
  id: z.string(),
  token: z.string(),
  path: z.string(),
  expires_at: ts,
});
export type LinkCreated = z.infer<typeof linkCreatedSchema>;

export const publicFormSchema = z.object({
  organization_name: z.string(),
  status: z.enum(["open", "submitted", "closed", "expired"]),
  expires_at: ts,
  prefill: z.record(z.string(), z.string()),
});
export type PublicForm = z.infer<typeof publicFormSchema>;

export const personalDetailsSchema = z
  .object({
    father_name: z.string().nullable().optional(),
    cnic: z.string().nullable().optional(),
    address: z.string().nullable().optional(),
    emergency_contact_1: contactSchema.nullable().optional(),
    emergency_contact_2: contactSchema.nullable().optional(),
    account_title: z.string().nullable().optional(),
    bank_name: z.string().nullable().optional(),
    bank_account_number: z.string().nullable().optional(),
    ntn: z.string().nullable().optional(),
    professional_reference: z.string().nullable().optional(),
    about: z.string().nullable().optional(),
  })
  .partial();
export type PersonalDetails = z.infer<typeof personalDetailsSchema>;

export interface LinkInput {
  invited_name?: string;
  invited_email?: string;
  invited_designation?: string;
  expires_in_days: number;
}
export interface ApprovalInput {
  employment_type?: Employee["employment_type"];
  job_title?: string;
  department_id?: string;
  note?: string;
}

export interface OnboardingService {
  list(params: {
    page?: number;
    pageSize?: number;
    status?: string;
  }): Promise<Page<OnboardingSummary>>;
  detail(id: string): Promise<OnboardingDetail>;
  createLink(input: LinkInput): Promise<LinkCreated>;
  approve(id: string, input: ApprovalInput): Promise<OnboardingDetail>;
  reject(id: string, note: string): Promise<OnboardingDetail>;
  revoke(id: string): Promise<OnboardingDetail>;
  personal(employeeId: string): Promise<PersonalDetails>;
  publicForm(token: string): Promise<PublicForm>;
  submit(token: string, values: SubmissionDetails): Promise<PublicForm>;
}

// ------------------------------------------------------------------ live

const live: OnboardingService = {
  list: ({ page = 1, pageSize = 25, status }) =>
    apiRequest("GET", "/hr/onboarding", pageSchema(onboardingSummarySchema), {
      query: { page, page_size: pageSize, status },
    }),
  detail: (id) =>
    apiRequest("GET", `/hr/onboarding/${id}`, onboardingDetailSchema),
  createLink: (input) =>
    apiRequest("POST", "/hr/onboarding", linkCreatedSchema, { body: input }),
  approve: (id, input) =>
    apiRequest("POST", `/hr/onboarding/${id}/approve`, onboardingDetailSchema, {
      body: input,
    }),
  reject: (id, note) =>
    apiRequest("POST", `/hr/onboarding/${id}/reject`, onboardingDetailSchema, {
      body: { note },
    }),
  revoke: (id) =>
    apiRequest("POST", `/hr/onboarding/${id}/revoke`, onboardingDetailSchema, {
      body: {},
    }),
  personal: (employeeId) =>
    apiRequest(
      "GET",
      `/hr/employees/${employeeId}/personal`,
      personalDetailsSchema,
    ),
  publicForm: (token) =>
    apiRequest("GET", `/public/onboarding/${token}`, publicFormSchema),
  submit: (token, values) =>
    apiRequest("POST", `/public/onboarding/${token}`, publicFormSchema, {
      body: values,
    }),
};

// ------------------------------------------------------------------ demo
// Fictional sample records, partitioned per demo workspace like the rest of the app.

type DemoLink = OnboardingDetail & { token: string };

const DAY = 86_400_000;
const demoLinks = demoCollection<DemoLink[]>("hr-onboarding", (profile) => {
  if (profile.kind === "empty") return [];
  const now = Date.now();
  const base = {
    invited_email: null,
    email: null,
    date_of_joining: null,
    job_type: null,
    submitted_at: null,
    reviewed_at: null,
    reviewed_by_label: null,
    review_note: null,
    employee_id: null,
    details: null,
    duplicate_employee_id: null,
    sensitive_visible: true,
    created_by_label: "Sample HR",
  };
  return [
    {
      ...base,
      id: "onb-demo-1",
      token: "demo-token-submitted-0000000000000000001",
      status: "submitted",
      effective_status: "submitted",
      invited_name: "Hira Saleem",
      invited_designation: "Sales Executive",
      full_name: "Hira Saleem",
      email: "hira.saleem@example.com",
      designation: "Sales Executive",
      date_of_joining: new Date(now + 7 * DAY).toISOString().slice(0, 10),
      job_type: "onsite",
      expires_at: new Date(now + 5 * DAY).toISOString(),
      created_at: new Date(now - 2 * DAY).toISOString(),
      submitted_at: new Date(now - DAY).toISOString(),
      details: {
        full_name: "Hira Saleem",
        father_name: "Saleem Akhtar",
        cnic: "35201-0000000-2",
        email: "hira.saleem@example.com",
        designation: "Sales Executive",
        gender: "female",
        date_of_joining: new Date(now + 7 * DAY).toISOString().slice(0, 10),
        date_of_birth: "1997-08-21",
        job_type: "onsite",
        contact_number: "+923000000001",
        emergency_contact_1: {
          name: "Saleem Akhtar (father)",
          phone: "+923000000002",
        },
        emergency_contact_2: {
          name: "Nida Saleem (sister)",
          phone: "+923000000003",
        },
        address: "Sample address, near a sample landmark",
        account_title: "Hira Saleem",
        bank_name: "Sample Bank",
        bank_account_number: "PK00SAMP0000000000000001",
        ntn: null,
        professional_reference: "Sample reference, ref@example.com",
        about: "Sample introduction for the announcement letter.",
      },
    },
    {
      ...base,
      id: "onb-demo-2",
      token: "demo-token-pending-00000000000000000000002",
      status: "pending",
      effective_status: "pending",
      invited_name: "Usman Tariq",
      invited_designation: "Warehouse Associate",
      full_name: null,
      designation: null,
      expires_at: new Date(now + 6 * DAY).toISOString(),
      created_at: new Date(now - DAY).toISOString(),
    },
  ];
});

function allDemoLinks(): DemoLink[] {
  return demoLinks().map((l) => ({
    ...l,
    effective_status:
      l.status === "pending" && Date.parse(l.expires_at) <= Date.now()
        ? "expired"
        : l.status,
  }));
}

function requireWrite() {
  if (!demoSession()?.permissions.includes("hr.write"))
    throw new ApiError(403, "FORBIDDEN");
}

function view(link: DemoLink): OnboardingDetail {
  const sensitive =
    demoSession()?.permissions.includes("hr.sensitive") ?? false;
  const { token: _token, ...rest } = link;
  if (!rest.details || sensitive) return { ...rest, sensitive_visible: true };
  const mask = (v?: string | null) =>
    v ? "•".repeat(Math.max(v.length - 4, 2)) + v.slice(-4) : v;
  return {
    ...rest,
    sensitive_visible: false,
    details: {
      ...rest.details,
      cnic: "•••••-•••••••-" + rest.details.cnic.slice(-1),
      bank_account_number: mask(rest.details.bank_account_number),
      ntn: mask(rest.details.ntn),
    },
  };
}

function findLink(id: string): DemoLink {
  const link = demoLinks().find((l) => l.id === id);
  if (!link) throw new ApiError(404, "RESOURCE_NOT_FOUND");
  return link;
}

function findToken(token: string): DemoLink {
  const link = demoLinks().find((l) => l.token === token);
  if (!link) throw new ApiError(404, "RESOURCE_NOT_FOUND");
  return link;
}

function publicState(link: DemoLink): PublicForm {
  const expired =
    link.status === "pending" && Date.parse(link.expires_at) <= Date.now();
  const status = expired
    ? "expired"
    : link.status === "pending"
      ? "open"
      : link.status === "submitted" || link.status === "approved"
        ? "submitted"
        : "closed";
  const prefill: Record<string, string> = {};
  if (status === "open") {
    if (link.invited_name) prefill.full_name = link.invited_name;
    if (link.invited_email) prefill.email = link.invited_email;
    if (link.invited_designation)
      prefill.designation = link.invited_designation;
  }
  const tenant = DEMO_TENANTS.find((t) => t.id === demoSession()?.tenant?.id);
  return {
    organization_name: tenant?.name ?? "Sample workspace",
    status,
    expires_at: link.expires_at,
    prefill,
  };
}

const demo: OnboardingService = {
  async list({ page = 1, pageSize = 25, status }) {
    await demoDelay();
    requireWrite();
    const rows = allDemoLinks()
      .filter((l) => !status || l.effective_status === status)
      .sort((a, b) => b.created_at.localeCompare(a.created_at))
      .map(view);
    return paginate(rows, page, pageSize);
  },
  async detail(id) {
    await demoDelay();
    requireWrite();
    return view(findLink(id));
  },
  async createLink(input) {
    await demoDelay(250);
    requireWrite();
    const token = `demo-${demoId("t")}-${Math.random().toString(36).slice(2, 14)}`;
    const link: DemoLink = {
      id: demoId("onb"),
      token,
      status: "pending",
      effective_status: "pending",
      invited_name: input.invited_name || null,
      invited_email: input.invited_email || null,
      invited_designation: input.invited_designation || null,
      full_name: null,
      email: null,
      designation: null,
      date_of_joining: null,
      job_type: null,
      expires_at: new Date(
        Date.now() + input.expires_in_days * DAY,
      ).toISOString(),
      created_by_label: demoSession()?.user.display_name ?? "You",
      created_at: new Date().toISOString(),
      submitted_at: null,
      reviewed_at: null,
      reviewed_by_label: null,
      review_note: null,
      employee_id: null,
      details: null,
      sensitive_visible: true,
      duplicate_employee_id: null,
    };
    demoLinks().unshift(link);
    return {
      id: link.id,
      token,
      path: `/onboarding/${token}`,
      expires_at: link.expires_at,
    };
  },
  async approve(id, input) {
    await demoDelay(300);
    requireWrite();
    const link = findLink(id);
    if (link.status !== "submitted" || !link.details)
      throw new ApiError(
        422,
        "ONBOARDING_NOT_SUBMITTED",
        undefined,
        "Only submitted forms can be approved",
      );
    const d = link.details;
    const business = demoBusiness();
    const dept = business.departments.find((x) => x.id === input.department_id);
    const employee: Employee = {
      id: demoId("emp"),
      full_name: d.full_name,
      email: d.email,
      phone: d.contact_number,
      job_title: input.job_title || d.designation,
      department_id: dept?.id ?? null,
      department_name: dept?.name ?? null,
      manager_id: null,
      employment_type:
        input.employment_type ??
        (d.job_type === "freelancer" ? "contract" : "full_time"),
      status: "active",
      hire_date: d.date_of_joining,
      termination_date: null,
      salary: null,
      salary_currency: null,
      gender: d.gender ?? null,
      work_arrangement: d.job_type,
      date_of_birth: d.date_of_birth,
      has_personal_details: true,
      sensitive_visible: true,
      created_at: new Date().toISOString(),
    };
    business.employees.unshift(employee);
    demoPersonal().set(employee.id, {
      father_name: d.father_name,
      cnic: d.cnic,
      address: d.address,
      emergency_contact_1: d.emergency_contact_1,
      emergency_contact_2: d.emergency_contact_2,
      account_title: d.account_title,
      bank_name: d.bank_name,
      bank_account_number: d.bank_account_number,
      ntn: d.ntn,
      professional_reference: d.professional_reference,
      about: d.about,
    });
    Object.assign(link, {
      status: "approved",
      effective_status: "approved",
      employee_id: employee.id,
      reviewed_at: new Date().toISOString(),
      reviewed_by_label: demoSession()?.user.display_name ?? "You",
      review_note: input.note ?? null,
    });
    return view(link);
  },
  async reject(id, note) {
    await demoDelay(250);
    requireWrite();
    const link = findLink(id);
    if (link.status !== "submitted")
      throw new ApiError(
        422,
        "ONBOARDING_NOT_SUBMITTED",
        undefined,
        "Only submitted forms can be rejected",
      );
    Object.assign(link, {
      status: "rejected",
      effective_status: "rejected",
      reviewed_at: new Date().toISOString(),
      reviewed_by_label: demoSession()?.user.display_name ?? "You",
      review_note: note,
    });
    return view(link);
  },
  async revoke(id) {
    await demoDelay(200);
    requireWrite();
    const link = findLink(id);
    if (link.status !== "pending")
      throw new ApiError(
        422,
        "ONBOARDING_NOT_PENDING",
        undefined,
        "Only unused links can be revoked",
      );
    Object.assign(link, { status: "revoked", effective_status: "revoked" });
    return view(link);
  },
  async personal(employeeId) {
    await demoDelay();
    if (!demoSession()?.permissions.includes("hr.sensitive"))
      throw new ApiError(403, "FORBIDDEN");
    return demoPersonal().get(employeeId) ?? {};
  },
  async publicForm(token) {
    await demoDelay();
    return publicState(findToken(token));
  },
  async submit(token, values) {
    await demoDelay(400);
    const link = findToken(token);
    if (publicState(link).status !== "open")
      throw new ApiError(
        422,
        "ONBOARDING_LINK_CLOSED",
        undefined,
        "This onboarding link is no longer accepting responses",
      );
    Object.assign(link, {
      status: "submitted",
      effective_status: "submitted",
      full_name: values.full_name,
      email: values.email,
      designation: values.designation,
      date_of_joining: values.date_of_joining,
      job_type: values.job_type,
      submitted_at: new Date().toISOString(),
      details: values,
    });
    return publicState(link);
  },
};

const demoPersonal = demoCollection<Map<string, PersonalDetails>>(
  "hr-personal",
  () => new Map(),
);

export const onboardingService = select<OnboardingService>({ demo, live });

export function jobTypeLabel(value: string | null | undefined) {
  return JOB_TYPES.find((j) => j.value === value)?.label ?? "—";
}

export function onboardingStatusLabel(value: string) {
  return ONBOARDING_STATUSES.find((s) => s.value === value)?.label ?? value;
}
