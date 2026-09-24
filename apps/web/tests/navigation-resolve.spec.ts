import { test, expect } from "@playwright/test";
import registry from "../src/features/navigation/registry.generated.json";
import access from "../src/features/auth/access.generated.json";
import { mergeOrder, resolveNavigation, validateCustomOrder, type NavContext } from "../src/features/navigation/resolve";
import type { NavDefinition } from "../src/features/navigation/types";

// Pure unit tests of the client-side resolver that mirrors the backend registry.
const definitions = registry as NavDefinition[];
const DEFAULT = ["Overview", "Customers / CRM", "Catalog", "PI", "Inventory", "Sales", "Quotes", "Orders", "Billing", "Finance", "HR", "Reports"];
const owner = access.roles.find((r) => r.key === "owner")!.permissions;

function ctx(permissions: string[] = owner, products: Record<string, string[]> = { pi: ["text", "knowledge", "handoff"] }): NavContext {
  return { permissions: new Set(permissions), roles: new Set(["owner"]), products, environmentKind: "production" };
}

const mainLabels = (nav: ReturnType<typeof resolveNavigation>) => nav.sections.find((s) => s.key === "main")!.items.map((i) => i.label);

test("default order matches the product contract", () => {
  expect(mainLabels(resolveNavigation(definitions, ctx()))).toEqual(DEFAULT);
});

test("PI requires installation and permission; no gaps when hidden", () => {
  expect(mainLabels(resolveNavigation(definitions, ctx(owner, {})))).toEqual(DEFAULT.filter((l) => l !== "PI"));
  expect(mainLabels(resolveNavigation(definitions, ctx(owner.filter((p) => p !== "pi.read"))))).not.toContain("PI");
});

test("custom order applies and a newly registered module appears by sort order", () => {
  const custom = ["pi", "overview", "customers", "catalog", "inventory", "sales", "quotes", "orders", "billing", "finance", "hr", "reports"];
  const withFuture: NavDefinition[] = [
    ...definitions,
    { ...definitions.find((d) => d.key === "reports")!, key: "subscriptions", label: "Subscriptions", route: "/subscriptions", sort_order: 130, required_permissions: ["billing.read"] },
  ];
  const nav = resolveNavigation(withFuture, ctx(), { main: custom });
  expect(nav.sections[0]!.items.map((i) => i.key)).toEqual([...custom, "subscriptions"]);
  const denied = resolveNavigation(withFuture, ctx(owner.filter((p) => p !== "billing.read")), { main: custom });
  expect(denied.sections[0]!.items.map((i) => i.key)).not.toContain("subscriptions");
});

test("merge inserts new items after their default neighbour and skips stale keys", () => {
  const items = [{ key: "a" }, { key: "b" }, { key: "new" }, { key: "c" }];
  expect(mergeOrder(items, ["c", "b", "a"]).map((i) => i.key)).toEqual(["c", "b", "new", "a"]);
  expect(mergeOrder(items, ["removed", "a"]).map((i) => i.key)).toEqual(["a", "b", "new", "c"]);
});

test("a saved order cannot contain hidden or duplicate items", () => {
  expect(() => validateCustomOrder([{ key: "a" }], ["a", "hidden"])).toThrow();
  expect(() => validateCustomOrder([{ key: "a" }], ["a", "a"])).toThrow();
});

test("no duplicate navigation keys or top-level routes", () => {
  const keys = definitions.map((d) => d.key);
  expect(new Set(keys).size).toBe(keys.length);
  const routes = definitions.filter((d) => d.parent === null).map((d) => d.route);
  expect(new Set(routes).size).toBe(routes.length);
});
