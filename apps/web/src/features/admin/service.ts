import { z } from "zod";
import {
  apiRequest,
  ApiError,
  pageSchema,
  type Page,
} from "@/services/api-client";
import { demoDelay, select } from "@/lib/data-mode";
import { demoBusiness } from "@/demo/business";
import { demoCollection, demoId, matches, paginate } from "@/demo/store";
import { daysAgo } from "@/demo/random";
import {
  DEMO_ENVIRONMENTS,
  DEMO_USER,
  demoRoles,
  readDemoState,
} from "@/demo/workspace";
import access from "@/features/auth/access.generated.json";
import {
  branchSchema,
  businessSettingsSchema,
  departmentSchema,
  type Branch,
  type BusinessSettings,
  type Department,
} from "@/features/business/types";
import { environmentSchema, type Environment } from "@/features/auth/types";

export const memberSchema = z.object({
  membership_id: z.string(),
  user_id: z.string(),
  email: z.string(),
  display_name: z.string(),
  status: z.enum(["active", "revoked"]),
  roles: z.array(z.string()),
  role_ids: z.array(z.string()),
  joined_at: z.string(),
});
export const roleSchema = z.object({
  id: z.string(),
  key: z.string(),
  name: z.string(),
  description: z.string(),
  is_system: z.boolean(),
  permissions: z.array(z.string()),
  member_count: z.number(),
});
export const permissionSchema = z.object({
  key: z.string(),
  label: z.string(),
  group: z.string(),
});
export const auditSchema = z.object({
  id: z.string(),
  actor_type: z.string(),
  actor_label: z.string(),
  action: z.string(),
  entity_type: z.string().nullable(),
  entity_id: z.string().nullable(),
  outcome: z.enum(["success", "denied", "failure"]),
  request_id: z.string().nullable(),
  environment_id: z.string().nullable(),
  details: z.record(z.string(), z.unknown()),
  created_at: z.string(),
});
export const organizationSchema = z.object({
  id: z.string(),
  name: z.string(),
  slug: z.string(),
});

export type Member = z.infer<typeof memberSchema>;
export type Role = z.infer<typeof roleSchema>;
export type Permission = z.infer<typeof permissionSchema>;
export type AuditEvent = z.infer<typeof auditSchema>;
export type Organization = z.infer<typeof organizationSchema>;

export interface AdminService {
  organization(): Promise<Organization>;
  renameOrganization(name: string): Promise<Organization>;
  businessSettings(): Promise<BusinessSettings>;
  updateBusinessSettings(
    input: Partial<BusinessSettings>,
  ): Promise<BusinessSettings>;
  members(params: { page?: number; search?: string }): Promise<Page<Member>>;
  addMember(input: {
    email: string;
    display_name: string;
    initial_password?: string | null;
    role_ids: string[];
  }): Promise<Member>;
  updateMemberRoles(id: string, roleIds: string[]): Promise<Member>;
  revokeMember(id: string): Promise<void>;
  roles(): Promise<Role[]>;
  permissions(): Promise<Permission[]>;
  createRole(input: {
    key: string;
    name: string;
    description: string;
    permissions: string[];
  }): Promise<Role>;
  updateRole(
    id: string,
    input: { name: string; description: string; permissions: string[] },
  ): Promise<Role>;
  deleteRole(id: string): Promise<void>;
  branches(): Promise<Branch[]>;
  createBranch(input: { name: string; code: string }): Promise<Branch>;
  renameBranch(id: string, name: string): Promise<Branch>;
  deleteBranch(id: string): Promise<void>;
  departments(): Promise<Department[]>;
  createDepartment(input: {
    name: string;
    code: string;
    branch_id: string | null;
  }): Promise<Department>;
  environments(): Promise<Environment[]>;
  createEnvironment(input: {
    key: string;
    name: string;
    kind: Environment["kind"];
  }): Promise<Environment>;
  updateEnvironment(
    id: string,
    input: { name: string; status: Environment["status"] },
  ): Promise<Environment>;
  audit(params: {
    page?: number;
    pageSize?: number;
    action?: string;
    entityType?: string;
    outcome?: string;
  }): Promise<Page<AuditEvent>>;
}

const live: AdminService = {
  organization: () => apiRequest("GET", "/organization", organizationSchema),
  renameOrganization: (name) =>
    apiRequest("PATCH", "/organization", organizationSchema, {
      body: { name },
    }),
  businessSettings: () =>
    apiRequest("GET", "/settings/business", businessSettingsSchema),
  updateBusinessSettings: (input) =>
    apiRequest("PATCH", "/settings/business", businessSettingsSchema, {
      body: input,
    }),
  members: ({ page = 1, search }) =>
    apiRequest("GET", "/members", pageSchema(memberSchema), {
      query: { page, page_size: 50, search },
    }),
  addMember: (input) =>
    apiRequest("POST", "/members", memberSchema, { body: input }),
  updateMemberRoles: (id, role_ids) =>
    apiRequest("PUT", `/members/${id}/roles`, memberSchema, {
      body: { role_ids },
    }),
  revokeMember: (id) => apiRequest("DELETE", `/members/${id}`, null),
  roles: () => apiRequest("GET", "/roles", z.array(roleSchema)),
  permissions: () =>
    apiRequest("GET", "/permissions", z.array(permissionSchema)),
  createRole: (input) =>
    apiRequest("POST", "/roles", roleSchema, { body: input }),
  updateRole: (id, input) =>
    apiRequest("PUT", `/roles/${id}`, roleSchema, { body: input }),
  deleteRole: (id) => apiRequest("DELETE", `/roles/${id}`, null),
  branches: async () =>
    (
      await apiRequest(
        "GET",
        "/organization/branches",
        pageSchema(branchSchema),
        { query: { page_size: 100 } },
      )
    ).items,
  createBranch: (input) =>
    apiRequest("POST", "/organization/branches", branchSchema, { body: input }),
  renameBranch: (id, name) =>
    apiRequest("PATCH", `/organization/branches/${id}`, branchSchema, {
      body: { name },
    }),
  deleteBranch: (id) =>
    apiRequest("DELETE", `/organization/branches/${id}`, null),
  departments: async () =>
    (
      await apiRequest(
        "GET",
        "/organization/departments",
        pageSchema(departmentSchema),
        { query: { page_size: 100 } },
      )
    ).items,
  createDepartment: (input) =>
    apiRequest("POST", "/organization/departments", departmentSchema, {
      body: input,
    }),
  environments: () =>
    apiRequest("GET", "/environments", z.array(environmentSchema)),
  createEnvironment: (input) =>
    apiRequest("POST", "/environments", environmentSchema, { body: input }),
  updateEnvironment: (id, input) =>
    apiRequest("PATCH", `/environments/${id}`, environmentSchema, {
      body: input,
    }),
  audit: ({ page = 1, pageSize = 50, action, entityType, outcome }) =>
    apiRequest("GET", "/audit/events", pageSchema(auditSchema), {
      query: {
        page,
        page_size: pageSize,
        action,
        entity_type: entityType,
        outcome,
      },
    }),
};

/* Demo ------------------------------------------------------------------------------------ */

type AdminData = {
  orgName: string;
  members: Member[];
  roles: Role[];
  audit: AuditEvent[];
};

const demoAdmin = demoCollection<AdminData>("admin", (profile) => {
  const roles: Role[] = demoRoles().map((r) => ({
    id: `role-${r.key}`,
    key: r.key,
    name: r.name,
    description: r.description,
    is_system: true,
    permissions: r.permissions,
    member_count: 0,
  }));
  const commerce = profile.tenantId === "tenant-northwind";
  const people: [string, string, string, string?][] = commerce
    ? [
        [DEMO_USER.display_name, DEMO_USER.email, "owner"],
        ["Omar Siddiqui", "omar@northwind.example", "manager"],
        ["Sana Malik", "sana@northwind.example", "support"],
        ["Hamza Raza", "hamza@northwind.example", "support"],
        ["Iqra Aslam", "iqra@northwind.example", "support"],
        ["Nida Farooq", "nida@northwind.example", "accountant"],
        ["Faisal Iqbal", "faisal@northwind.example", "sales"],
        ["Laiba Javed", "laiba@northwind.example", "sales"],
        ["Zainab Ahmed", "zainab@northwind.example", "hr"],
        ["Kashif Butt", "kashif@northwind.example", "viewer"],
        [
          "Former Contractor",
          "contractor@external.example",
          "viewer",
          "revoked",
        ],
      ]
    : [
        [DEMO_USER.display_name, DEMO_USER.email, "owner"],
        ["Ibrahim Tahir", "ibrahim@brightline.example", "support"],
        ["Leo Park", "leo@brightline.example", "viewer"],
      ];
  const members = people.map(([name, email, role, status], i) => ({
    membership_id: `mem-${profile.tenantId}-${i}`,
    user_id: i === 0 ? DEMO_USER.id : `user-${profile.tenantId}-${i}`,
    email,
    display_name: name,
    status: (status ?? "active") as Member["status"],
    roles: [role],
    role_ids: [`role-${role}`],
    joined_at: daysAgo(400 - i * 30),
  }));
  if (commerce) {
    roles.push({
      id: "role-custom-warehouse-lead",
      key: "warehouse-lead",
      name: "Warehouse Lead",
      description: "Stock adjustments and order fulfilment",
      is_system: false,
      permissions: [
        "inventory.read",
        "inventory.adjust",
        "orders.read",
        "orders.write",
        "catalog.read",
        "overview.read",
        "notifications.read",
      ],
      member_count: 0,
    });
  }
  for (const role of roles)
    role.member_count = members.filter(
      (m) => m.status === "active" && m.role_ids.includes(role.id),
    ).length;
  const actions: [string, string, string, AuditEvent["outcome"]][] = [
    ["order.confirm", "PI", "order", "success"],
    ["payment.recorded", "Nida Farooq", "payment", "success"],
    ["quote.approve", "Omar Siddiqui", "quote", "success"],
    ["inventory.adjusted", "Kashif Butt", "catalog_variant", "success"],
    ["customer.created", "PI", "customer", "success"],
    ["auth.login_failed", "anonymous", "user", "denied"],
    ["catalog.variant_updated", "Amina Rahman", "catalog_variant", "success"],
    ["member.added", "Amina Rahman", "membership", "success"],
    ["pi.handoff_created", "PI", "pi_handoff", "success"],
    ["role.created", "Amina Rahman", "role", "success"],
    ["navigation.order_saved", "Sana Malik", "navigation", "success"],
    ["environment.created", "Omar Siddiqui", "environment", "success"],
    ["invoice.void", "Nida Farooq", "invoice", "success"],
    [
      "settings.business_updated",
      "Amina Rahman",
      "business_settings",
      "success",
    ],
    ["pi.provider_fallback", "PI", "ai_gateway", "failure"],
  ];
  const audit: AuditEvent[] =
    commerce || profile.kind === "services"
      ? Array.from({ length: 120 }, (_, i) => {
          const [action, actor, entity, outcome] = actions[i % actions.length]!;
          return {
            id: `aud-${profile.tenantId}-${i}`,
            actor_type:
              actor === "PI"
                ? "system"
                : actor === "anonymous"
                  ? "anonymous"
                  : "user",
            actor_label: actor,
            action,
            entity_type: entity,
            entity_id: `${entity}-${1000 + i}`,
            outcome,
            request_id: `req-${(0x5f3a + i * 7919).toString(16)}`,
            environment_id: profile.environmentId,
            details:
              action === "inventory.adjusted"
                ? {
                    quantity: -2,
                    kind: "adjustment",
                    reason: "Damaged in transit",
                    balance_after: 41,
                  }
                : action === "pi.provider_fallback"
                  ? {
                      from: "primary",
                      to: "fallback",
                      error_kind: "rate_limit",
                    }
                  : action === "auth.login_failed"
                    ? { reason: "invalid" }
                    : {},
            created_at: daysAgo(i * 0.21 + (i % 3) * 0.03),
          };
        })
      : [];
  return {
    orgName: commerce ? "Northwind Trading Co." : "Brightline Studio",
    members,
    roles,
    audit,
  };
});

function rule(code: string, message: string, status = 422): never {
  throw new ApiError(status, code, undefined, message);
}

const demo: AdminService = {
  async organization() {
    await demoDelay(100);
    return {
      id: readDemoState().tenantId,
      name: demoAdmin().orgName,
      slug: readDemoState().tenantId.replace("tenant-", ""),
    };
  },
  async renameOrganization(name) {
    await demoDelay(250);
    demoAdmin().orgName = name;
    return demo.organization();
  },
  async businessSettings() {
    await demoDelay(100);
    return { ...demoBusiness().settings };
  },
  async updateBusinessSettings(input) {
    await demoDelay(300);
    Object.assign(demoBusiness().settings, input);
    return { ...demoBusiness().settings };
  },
  async members({ page = 1, search }) {
    await demoDelay();
    return paginate(
      demoAdmin().members.filter(
        (m) =>
          !search ||
          matches(m.display_name, search) ||
          matches(m.email, search),
      ),
      page,
      50,
    );
  },
  async addMember(input) {
    await demoDelay(350);
    const data = demoAdmin();
    if (
      data.members.some((m) => m.email === input.email && m.status === "active")
    )
      rule("RESOURCE_CONFLICT", "This person is already a member", 409);
    const roles = data.roles.filter((r) => input.role_ids.includes(r.id));
    const member: Member = {
      membership_id: demoId("mem"),
      user_id: demoId("user"),
      email: input.email,
      display_name: input.display_name,
      status: "active",
      roles: roles.map((r) => r.key),
      role_ids: roles.map((r) => r.id),
      joined_at: new Date().toISOString(),
    };
    data.members.push(member);
    roles.forEach((r) => (r.member_count += 1));
    return member;
  },
  async updateMemberRoles(id, roleIds) {
    await demoDelay(250);
    const data = demoAdmin();
    const member = data.members.find((m) => m.membership_id === id);
    if (!member) throw new ApiError(404, "RESOURCE_NOT_FOUND");
    const owners = data.members.filter(
      (m) =>
        m.status === "active" &&
        m.role_ids.includes("role-owner") &&
        m.membership_id !== id,
    );
    if (!roleIds.includes("role-owner") && owners.length === 0)
      rule("LAST_OWNER", "A workspace needs at least one owner");
    const roles = data.roles.filter((r) => roleIds.includes(r.id));
    member.role_ids = roles.map((r) => r.id);
    member.roles = roles.map((r) => r.key);
    for (const role of data.roles)
      role.member_count = data.members.filter(
        (m) => m.status === "active" && m.role_ids.includes(role.id),
      ).length;
    return { ...member };
  },
  async revokeMember(id) {
    await demoDelay(250);
    const data = demoAdmin();
    const member = data.members.find((m) => m.membership_id === id);
    if (!member) throw new ApiError(404, "RESOURCE_NOT_FOUND");
    if (member.user_id === DEMO_USER.id)
      rule("SELF_REVOKE", "You cannot remove yourself");
    member.status = "revoked";
  },
  async roles() {
    await demoDelay(100);
    return demoAdmin().roles.map((r) => ({ ...r }));
  },
  async permissions() {
    await demoDelay(60);
    return access.permissions;
  },
  async createRole(input) {
    await demoDelay(300);
    const data = demoAdmin();
    if (data.roles.some((r) => r.key === input.key))
      rule("RESOURCE_CONFLICT", "A role with this key already exists", 409);
    const role: Role = {
      id: demoId("role"),
      is_system: false,
      member_count: 0,
      ...input,
    };
    data.roles.push(role);
    return role;
  },
  async updateRole(id, input) {
    await demoDelay(300);
    const role = demoAdmin().roles.find((r) => r.id === id);
    if (!role) throw new ApiError(404, "RESOURCE_NOT_FOUND");
    if (role.is_system) rule("SYSTEM_ROLE", "System roles cannot be modified");
    Object.assign(role, input);
    return { ...role };
  },
  async deleteRole(id) {
    await demoDelay(250);
    const data = demoAdmin();
    const role = data.roles.find((r) => r.id === id);
    if (!role) throw new ApiError(404, "RESOURCE_NOT_FOUND");
    if (role.is_system) rule("SYSTEM_ROLE", "System roles cannot be deleted");
    if (role.member_count > 0)
      rule(
        "RESOURCE_CONFLICT",
        "Remove this role from members before deleting it",
        409,
      );
    data.roles = data.roles.filter((r) => r.id !== id);
  },
  async branches() {
    await demoDelay(100);
    return [...demoBusiness().branches];
  },
  async createBranch(input) {
    await demoDelay(250);
    const b = demoBusiness();
    if (b.branches.some((x) => x.code === input.code))
      rule(
        "RESOURCE_CONFLICT",
        "The operation conflicts with existing data",
        409,
      );
    const branch = {
      id: demoId("br"),
      tenant_id: readDemoState().tenantId,
      ...input,
    };
    b.branches.push(branch);
    return branch;
  },
  async renameBranch(id, name) {
    await demoDelay(200);
    const branch = demoBusiness().branches.find((b) => b.id === id);
    if (!branch) throw new ApiError(404, "RESOURCE_NOT_FOUND");
    branch.name = name;
    return { ...branch };
  },
  async deleteBranch(id) {
    await demoDelay(250);
    const b = demoBusiness();
    if (
      b.departments.some((d) => d.branch_id === id) ||
      b.locations.some((l) => l.branch_id === id)
    )
      rule(
        "RESOURCE_CONFLICT",
        "The operation conflicts with existing data",
        409,
      );
    b.branches = b.branches.filter((x) => x.id !== id);
  },
  async departments() {
    await demoDelay(100);
    return [...demoBusiness().departments];
  },
  async createDepartment(input) {
    await demoDelay(250);
    const b = demoBusiness();
    if (b.departments.some((d) => d.code === input.code))
      rule(
        "RESOURCE_CONFLICT",
        "The operation conflicts with existing data",
        409,
      );
    const dept = {
      id: demoId("dep"),
      tenant_id: readDemoState().tenantId,
      ...input,
    };
    b.departments.push(dept);
    return dept;
  },
  async environments() {
    await demoDelay(100);
    return [...(DEMO_ENVIRONMENTS[readDemoState().tenantId] ?? [])];
  },
  async createEnvironment(input) {
    await demoDelay(300);
    const list = DEMO_ENVIRONMENTS[readDemoState().tenantId] ?? [];
    if (list.some((e) => e.key === input.key))
      rule(
        "RESOURCE_CONFLICT",
        "An environment with this key already exists",
        409,
      );
    const env: Environment = {
      id: demoId("env"),
      status: "active",
      is_default: false,
      ...input,
    };
    list.push(env);
    return env;
  },
  async updateEnvironment(id, input) {
    await demoDelay(250);
    const env = (DEMO_ENVIRONMENTS[readDemoState().tenantId] ?? []).find(
      (e) => e.id === id,
    );
    if (!env) throw new ApiError(404, "RESOURCE_NOT_FOUND");
    if (
      input.status === "archived" &&
      (env.is_default || env.id === readDemoState().environmentId)
    )
      rule(
        "ENVIRONMENT_IN_USE",
        "The default or current environment cannot be archived",
      );
    Object.assign(env, input);
    return { ...env };
  },
  async audit({ page = 1, pageSize = 50, action, entityType, outcome }) {
    await demoDelay();
    const rows = demoAdmin().audit.filter(
      (a) =>
        (!action || a.action.startsWith(action)) &&
        (!entityType || a.entity_type === entityType) &&
        (!outcome || a.outcome === outcome),
    );
    return paginate(rows, page, pageSize);
  },
};

export const adminService = select<AdminService>({ demo, live });
