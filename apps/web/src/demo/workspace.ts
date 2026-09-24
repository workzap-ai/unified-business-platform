/**
 * Demo-mode workspace state. Everything here is fictional sample data used only when
 * NEXT_PUBLIC_DATA_MODE is not "live". It never reaches the platform API.
 */
import access from "@/features/auth/access.generated.json";
import type { Environment, Session, Tenant } from "@/features/auth/types";

export const DEMO_USER = {
  id: "user-demo-owner",
  email: "demo@example.com",
  display_name: "Amina Rahman",
};

export const DEMO_TENANTS: Tenant[] = [
  { id: "tenant-northwind", name: "Northwind Trading Co.", slug: "northwind-trading" },
  { id: "tenant-brightline", name: "Brightline Studio", slug: "brightline-studio" },
];

export const DEMO_ENVIRONMENTS: Record<string, Environment[]> = {
  "tenant-northwind": [
    { id: "env-nw-prod", key: "production", name: "Production", kind: "production", status: "active", is_default: true },
    { id: "env-nw-staging", key: "staging", name: "Staging", kind: "staging", status: "active", is_default: false },
  ],
  "tenant-brightline": [
    { id: "env-bl-prod", key: "production", name: "Production", kind: "production", status: "active", is_default: true },
  ],
};

export type DemoRoleKey = (typeof access.roles)[number]["key"];

type DemoState = {
  signedIn: boolean;
  tenantId: string;
  environmentId: string;
  role: string;
};

const KEY = "platform.demo.session";
const DEFAULT_STATE: DemoState = {
  signedIn: false,
  tenantId: "tenant-northwind",
  environmentId: "env-nw-prod",
  role: "owner",
};

export function readDemoState(): DemoState {
  if (typeof window === "undefined") return DEFAULT_STATE;
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw ? { ...DEFAULT_STATE, ...(JSON.parse(raw) as Partial<DemoState>) } : DEFAULT_STATE;
  } catch {
    return DEFAULT_STATE;
  }
}

export function writeDemoState(patch: Partial<DemoState>): DemoState {
  const next = { ...readDemoState(), ...patch };
  try {
    window.localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    /* storage unavailable: state lives for this page only */
  }
  return next;
}

export function demoRoles() {
  return access.roles;
}

export function demoPermissions(role: string): string[] {
  return access.roles.find((r) => r.key === role)?.permissions ?? [];
}

/** The scope key partitions demo data exactly like tenant + environment scope does. */
export function demoScopeKey(): string {
  const state = readDemoState();
  return `${state.tenantId}:${state.environmentId}`;
}

export function demoSession(): Session | null {
  const state = readDemoState();
  if (!state.signedIn) return null;
  const tenant = DEMO_TENANTS.find((t) => t.id === state.tenantId) ?? DEMO_TENANTS[0]!;
  const environments = DEMO_ENVIRONMENTS[tenant.id] ?? [];
  const environment =
    environments.find((e) => e.id === state.environmentId) ?? environments[0] ?? null;
  return {
    user: DEMO_USER,
    tenant: { id: tenant.id, name: tenant.name, key: tenant.slug },
    environment: environment
      ? { id: environment.id, name: environment.name, key: environment.key, kind: environment.kind }
      : null,
    branch: null,
    permissions: demoPermissions(state.role),
    roles: [state.role],
  };
}
