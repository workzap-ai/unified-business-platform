import { z } from "zod";
import {
  apiRequest,
  ApiError,
  DemoError,
  pageSchema,
  bindApiWorkspace,
} from "@/services/api-client";
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
import { clearAgentHistory } from "@/features/workspace-agent/agent-history";
import { passkeySignIn } from "./passkey";

export interface AuthService {
  session(): Promise<Session>;
  login(input: LoginInput): Promise<Session>;
  /** Face ID / Touch ID / Windows Hello / fingerprint, via a passkey. */
  loginWithPasskey(): Promise<Session>;
  register(input: RegisterInput): Promise<Session>;
  createWorkspace(
    name: string,
    businessType: "service_business" | "product_business" | "hybrid_business",
  ): Promise<Session>;
  logout(): Promise<void>;
  selectWorkspace(tenantId: string, environmentId?: string): Promise<Session>;
  tenants(): Promise<Tenant[]>;
  environments(): Promise<Environment[]>;
  changePassword(current: string, next: string): Promise<void>;
  logoutAll(): Promise<void>;
  forgotPassword(email: string): Promise<void>;
  resetPassword(token: string, newPassword: string): Promise<void>;
  verifyEmail(token: string): Promise<void>;
  resendVerification(): Promise<void>;
  acceptInvite(token: string, newPassword: string): Promise<Session>;
}

const live: AuthService = {
  session: () =>
    apiRequest("GET", "/auth/session", sessionSchema).then(bindSession),
  login: (input) =>
    apiRequest("POST", "/auth/login", sessionSchema, { body: input }).then(
      bindSession,
    ),
  register: (input) =>
    apiRequest("POST", "/auth/register", sessionSchema, {
      body: input,
      timeoutMs: 90_000,
    }).then(bindSession),
  createWorkspace: (name, business_type) =>
    apiRequest("POST", "/auth/workspaces", sessionSchema, {
      body: { name, business_type },
      timeoutMs: 90_000,
    }),
  // Agent Beta chats are kept per person in this browser; sign-out removes them.
  logout: () =>
    apiRequest<void>("POST", "/auth/logout", null).finally(clearAgentHistory),
  logoutAll: () =>
    apiRequest<void>("POST", "/auth/logout-all", null).finally(
      clearAgentHistory,
    ),
  selectWorkspace: (tenant_id, environment_id) =>
    apiRequest("PUT", "/auth/session/workspace", sessionSchema, {
      body: { tenant_id, environment_id: environment_id ?? null },
    }).then(bindSession),
  tenants: async () =>
    (
      await apiRequest("GET", "/tenants", pageSchema(tenantSchema), {
        query: { page_size: 100 },
      })
    ).items,
  environments: () =>
    apiRequest("GET", "/environments", z.array(environmentSchema)),
  changePassword: (current_password, new_password) =>
    apiRequest("POST", "/auth/password", null, {
      body: { current_password, new_password },
    }),
  forgotPassword: (email) =>
    apiRequest("POST", "/auth/forgot-password", null, { body: { email } }),
  resetPassword: (token, new_password) =>
    apiRequest("POST", "/auth/reset-password", null, {
      body: { token, new_password },
    }),
  verifyEmail: (token) =>
    apiRequest("POST", "/auth/verify-email", null, { body: { token } }),
  resendVerification: () =>
    apiRequest("POST", "/auth/resend-verification", null, { body: {} }),
  acceptInvite: (token, new_password) =>
    apiRequest("POST", "/auth/accept-invite", sessionSchema, {
      body: { token, new_password },
    }).then(bindSession),
  loginWithPasskey: () =>
    passkeySignIn((body) =>
      apiRequest("POST", "/auth/passkeys/login/verify", sessionSchema, {
        body,
      }),
    ).then(bindSession),
};

function bindSession(session: Session): Session {
  bindApiWorkspace(session.tenant?.id, session.environment?.id);
  return session;
}

function requireDemoSession(): Session {
  const session = demoSession();
  if (!session) throw new ApiError(401, "UNAUTHORIZED");
  return session;
}

const demo: AuthService = {
  async createWorkspace() {
    throw new DemoError("New workspaces require a live API connection.");
  },
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
    writeDemoState({
      signedIn: true,
      tenantId: "tenant-brightline",
      environmentId: "env-bl-prod",
    });
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
      environments.find((e) => e.id === environmentId) ??
      environments.find((e) => e.is_default);
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
    if (current === next)
      throw new DemoError("Choose a password different from the current one.");
  },
  async forgotPassword() {
    await demoDelay(400);
    // No real email goes out in sample-data mode; the response always looks the
    // same either way, matching the live API's non-enumerating behavior.
  },
  async resetPassword() {
    await demoDelay(300);
    throw new DemoError(
      "Password reset requires a live API connection: this build never sends the email that carries the reset link.",
    );
  },
  async verifyEmail() {
    await demoDelay(300);
    throw new DemoError(
      "Email verification requires a live API connection: this build never sends the email that carries the link.",
    );
  },
  async resendVerification() {
    await demoDelay(200);
  },
  async loginWithPasskey() {
    await demoDelay(200);
    throw new DemoError("Passkeys need a live API connection.");
  },
  async acceptInvite() {
    await demoDelay(300);
    throw new DemoError(
      "Accepting an invite requires a live API connection: this build never sends the email that carries the invite link.",
    );
  },
};

export const authService = select<AuthService>({ demo, live });
