import { z } from "zod";
import { apiRequest, ApiError, DemoError, pageSchema } from "@/services/api-client";
import { demoDelay, select } from "@/lib/data-mode";
import {
  DEMO_ENVIRONMENTS,
  DEMO_TENANTS,
  demoSession,
  readDemoState,
  writeDemoState,
} from "@/demo/workspace";
import {
  environmentSchema,
  sessionSchema,
  tenantSchema,
  type Environment,
  type LoginInput,
  type RegisterInput,
  type Session,
  type Tenant,
} from "./types";

export interface AuthService {
  session(): Promise<Session>;
  login(input: LoginInput): Promise<Session>;
  register(input: RegisterInput): Promise<Session>;
  logout(): Promise<void>;
  selectWorkspace(tenantId: string, environmentId?: string): Promise<Session>;
  tenants(): Promise<Tenant[]>;
  environments(): Promise<Environment[]>;
  changePassword(current: string, next: string): Promise<void>;
  logoutAll(): Promise<void>;
}

const live: AuthService = {
  session: () => apiRequest("GET", "/auth/session", sessionSchema),
  login: (input) => apiRequest("POST", "/auth/login", sessionSchema, { body: input }),
  register: (input) => apiRequest("POST", "/auth/register", sessionSchema, { body: input }),
  logout: () => apiRequest("POST", "/auth/logout", null),
  logoutAll: () => apiRequest("POST", "/auth/logout-all", null),
  selectWorkspace: (tenant_id, environment_id) =>
    apiRequest("PUT", "/auth/session/workspace", sessionSchema, {
      body: { tenant_id, environment_id: environment_id ?? null },
    }),
  tenants: async () =>
    (await apiRequest("GET", "/tenants", pageSchema(tenantSchema), { query: { page_size: 100 } }))
      .items,
  environments: () => apiRequest("GET", "/environments", z.array(environmentSchema)),
  changePassword: (current_password, new_password) =>
    apiRequest("POST", "/auth/password", null, { body: { current_password, new_password } }),
};

function requireDemoSession(): Session {
  const session = demoSession();
  if (!session) throw new ApiError(401, "UNAUTHORIZED");
  return session;
}

const demo: AuthService = {
  async session() {
    await demoDelay(60);
    return requireDemoSession();
  },
  async login(input) {
    await demoDelay(350);
    if (!input.email.includes("@") || input.password.length < 1) {
      throw new ApiError(401, "UNAUTHORIZED");
    }
    writeDemoState({ signedIn: true });
    return requireDemoSession();
  },
  async register() {
    await demoDelay(400);
    writeDemoState({ signedIn: true, tenantId: "tenant-brightline", environmentId: "env-bl-prod" });
    return requireDemoSession();
  },
  async logout() {
    await demoDelay(80);
    writeDemoState({ signedIn: false });
  },
  async logoutAll() {
    await demoDelay(80);
    writeDemoState({ signedIn: false });
  },
  async selectWorkspace(tenantId, environmentId) {
    await demoDelay(150);
    const environments = DEMO_ENVIRONMENTS[tenantId];
    if (!environments) throw new ApiError(404, "RESOURCE_NOT_FOUND");
    const env =
      environments.find((e) => e.id === environmentId) ?? environments.find((e) => e.is_default);
    if (!env) throw new ApiError(404, "RESOURCE_NOT_FOUND");
    writeDemoState({ tenantId, environmentId: env.id });
    return requireDemoSession();
  },
  async tenants() {
    await demoDelay(60);
    return DEMO_TENANTS;
  },
  async environments() {
    await demoDelay(60);
    return DEMO_ENVIRONMENTS[readDemoState().tenantId] ?? [];
  },
  async changePassword(current, next) {
    await demoDelay(300);
    if (current === next) throw new DemoError("Choose a password different from the current one.");
  },
};

export const authService = select<AuthService>({ demo, live });
