import { apiRequest, ApiError, DemoError } from "@/services/api-client";
import { demoDelay, select } from "@/lib/data-mode";
import {
  DEMO_ENVIRONMENTS,
  demoSession,
  readDemoState,
} from "@/demo/workspace";
import { demoEnabledProducts } from "@/features/products/service";
import registry from "./registry.generated.json";
import { resolveNavigation, validateCustomOrder } from "./resolve";
import {
  navigationSchema,
  type NavDefinition,
  type Navigation,
  type SectionKey,
} from "./types";

export interface NavigationService {
  get(): Promise<Navigation>;
  saveOrder(section: SectionKey, order: string[]): Promise<Navigation>;
  reset(section: SectionKey): Promise<Navigation>;
}

const live: NavigationService = {
  get: () => apiRequest("GET", "/navigation", navigationSchema),
  saveOrder: (section, order) =>
    apiRequest("PUT", `/navigation/preferences/${section}`, navigationSchema, {
      body: { order },
    }),
  reset: (section) =>
    apiRequest(
      "DELETE",
      `/navigation/preferences/${section}`,
      navigationSchema,
    ),
};

/* Demo: the same registry definitions (generated from the API), resolved in the browser.
   Custom order is stored per demo tenant + user, never as a global default. */

const definitions = registry as NavDefinition[];
const orderKey = (tenantId: string) => `platform.demo.nav-order.${tenantId}`;

function readOrders(): Partial<Record<SectionKey, string[]>> {
  try {
    const raw = window.localStorage.getItem(orderKey(readDemoState().tenantId));
    return raw
      ? (JSON.parse(raw) as Partial<Record<SectionKey, string[]>>)
      : {};
  } catch {
    return {};
  }
}

function writeOrders(orders: Partial<Record<SectionKey, string[]>>) {
  try {
    window.localStorage.setItem(
      orderKey(readDemoState().tenantId),
      JSON.stringify(orders),
    );
  } catch {
    /* ignore */
  }
}

async function demoBadges(): Promise<Record<string, number | null>> {
  const [{ demoOpenHandoffCount }, { demoUnreadCount }] = await Promise.all([
    import("@/features/pi/demo-badges"),
    import("@/features/notifications/demo-badges"),
  ]);
  return {
    "pi.open_handoffs": demoOpenHandoffCount() || null,
    "notifications.unread": demoUnreadCount() || null,
  };
}

function demoContext() {
  const session = demoSession();
  if (!session) throw new ApiError(401, "UNAUTHORIZED");
  const state = readDemoState();
  const environment = (DEMO_ENVIRONMENTS[state.tenantId] ?? []).find(
    (e) => e.id === state.environmentId,
  );
  return {
    permissions: new Set(session.permissions),
    roles: new Set(session.roles),
    products: demoEnabledProducts(),
    environmentKind: environment?.kind ?? "production",
  };
}

async function demoResolve(): Promise<Navigation> {
  return resolveNavigation(
    definitions,
    demoContext(),
    readOrders(),
    await demoBadges(),
  );
}

const demo: NavigationService = {
  async get() {
    await demoDelay(80);
    return demoResolve();
  },
  async saveOrder(section, order) {
    await demoDelay(150);
    const current = await demoResolve();
    const visible =
      current.sections.find((s) => s.key === section)?.items ?? [];
    try {
      validateCustomOrder(visible, order);
    } catch {
      throw new DemoError("That order contains unavailable items.");
    }
    writeOrders({ ...readOrders(), [section]: order });
    return demoResolve();
  },
  async reset(section) {
    await demoDelay(120);
    const orders = readOrders();
    delete orders[section];
    writeOrders(orders);
    return demoResolve();
  },
};

export const navigationService = select<NavigationService>({ demo, live });
export { definitions as registryDefinitions };
