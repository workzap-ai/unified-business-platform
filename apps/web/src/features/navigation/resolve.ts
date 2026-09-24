/**
 * Client-side mirror of the backend navigation resolver, used by the demo adapter and
 * for optimistic reordering. In live mode the API resolves navigation authoritatively.
 * Keep behavior identical to apps/api/app/modules/navigation/registry.py.
 */
import type { NavDefinition, NavItem, Navigation, SectionKey } from "./types";

export type NavContext = {
  permissions: ReadonlySet<string>;
  roles: ReadonlySet<string>;
  products: Readonly<Record<string, readonly string[]>>;
  environmentKind: string;
};

export function allowed(item: NavDefinition, context: NavContext): boolean {
  if (!item.enabled || !item.visible) return false;
  if (!item.required_permissions.every((p) => context.permissions.has(p)))
    return false;
  if (
    item.any_permissions.length &&
    !item.any_permissions.some((p) => context.permissions.has(p))
  )
    return false;
  if (
    item.required_roles.length &&
    !item.required_roles.some((r) => context.roles.has(r))
  )
    return false;
  if (item.required_product) {
    const features = context.products[item.required_product];
    if (!features) return false;
    if (item.required_feature && !features.includes(item.required_feature))
      return false;
  }
  if (
    item.environment_scope &&
    !item.environment_scope.includes(context.environmentKind)
  )
    return false;
  return true;
}

const bySortOrder = (
  a: { sort_order: number; key: string },
  b: { sort_order: number; key: string },
) => a.sort_order - b.sort_order || a.key.localeCompare(b.key);

/**
 * Apply a saved custom order to visible items. Hidden/unknown saved keys are skipped;
 * visible items missing from the saved order (new modules) are inserted after their
 * nearest preceding item in default order.
 */
export function mergeOrder<T extends { key: string }>(
  defaults: T[],
  custom: readonly string[],
): T[] {
  const byKey = new Map(defaults.map((item) => [item.key, item]));
  const seen = new Set<string>();
  const ordered: T[] = [];
  for (const key of custom) {
    const item = byKey.get(key);
    if (item && !seen.has(key)) {
      ordered.push(item);
      seen.add(key);
    }
  }
  if (ordered.length === 0) return [...defaults];
  defaults.forEach((item, index) => {
    if (seen.has(item.key)) return;
    let position = 0;
    for (let i = index - 1; i >= 0; i -= 1) {
      const previous = defaults[i]!;
      if (seen.has(previous.key)) {
        position = ordered.indexOf(previous) + 1;
        break;
      }
    }
    ordered.splice(position, 0, item);
    seen.add(item.key);
  });
  return ordered;
}

function toItem(
  definition: NavDefinition,
  children: NavItem[],
  badge: number | null,
): NavItem {
  return {
    key: definition.key,
    label: definition.label,
    route: definition.route,
    icon: definition.icon,
    type: definition.type,
    section: definition.section,
    sort_order: definition.sort_order,
    badge,
    analytics_id: definition.analytics_id || `nav.${definition.key}`,
    keywords: definition.keywords,
    description: definition.description,
    children,
  };
}

export function resolveNavigation(
  definitions: NavDefinition[],
  context: NavContext,
  customOrders: Partial<Record<SectionKey, readonly string[]>> = {},
  badges: Record<string, number | null> = {},
): Navigation {
  const sections: Navigation["sections"] = (["main", "admin"] as const).map(
    (section) => {
      const visible = definitions
        .filter(
          (d) =>
            d.section === section && d.parent === null && allowed(d, context),
        )
        .sort(bySortOrder);
      const ordered = mergeOrder(visible, customOrders[section] ?? []);
      return {
        key: section,
        label: section === "main" ? "Main" : "Admin",
        customized: (customOrders[section] ?? []).length > 0,
        items: ordered.map((definition) =>
          toItem(
            definition,
            definitions
              .filter((d) => d.parent === definition.key && allowed(d, context))
              .sort(bySortOrder)
              .map((child) =>
                toItem(
                  child,
                  [],
                  child.badge ? (badges[child.badge] ?? null) : null,
                ),
              ),
            definition.badge ? (badges[definition.badge] ?? null) : null,
          ),
        ),
      };
    },
  );
  return { sections };
}

export function validateCustomOrder(
  visible: { key: string }[],
  order: string[],
): string[] {
  const keys = new Set(visible.map((v) => v.key));
  if (new Set(order).size !== order.length)
    throw new Error("Duplicate navigation keys");
  if (!order.every((key) => keys.has(key)))
    throw new Error("Unavailable navigation item");
  return order;
}
