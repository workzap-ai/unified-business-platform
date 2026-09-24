import { z } from "zod";
import type { Permission } from "./service";

/** Permissions grouped by `group`, keeping the registry's order of first appearance. */
export function groupPermissions(
  permissions: Permission[],
): [string, Permission[]][] {
  const groups = new Map<string, Permission[]>();
  for (const p of permissions)
    groups.set(p.group, [...(groups.get(p.group) ?? []), p]);
  return [...groups.entries()];
}

/** Slug used for role and environment keys: lowercase letters, digits and dashes. */
export const SLUG = /^[a-z][a-z0-9-]{1,47}$/;

export function slugify(value: string) {
  return value
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .replace(/^[^a-z]+/, "")
    .slice(0, 48);
}

/**
 * Flattens audit `details` into readable key/value rows (nested objects become dotted
 * keys, arrays are joined) so the UI never dumps raw JSON.
 */
export function flattenDetails(
  value: unknown,
  prefix = "",
): { key: string; value: string }[] {
  if (value === null || value === undefined)
    return prefix ? [{ key: prefix, value: "—" }] : [];
  if (Array.isArray(value)) {
    if (value.every((v) => v === null || typeof v !== "object"))
      return [
        {
          key: prefix || "value",
          value: value.map((v) => String(v)).join(", ") || "—",
        },
      ];
    return value.flatMap((v, i) => flattenDetails(v, `${prefix}[${i + 1}]`));
  }
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (!entries.length) return prefix ? [{ key: prefix, value: "—" }] : [];
    return entries.flatMap(([k, v]) =>
      flattenDetails(v, prefix ? `${prefix}.${k}` : k),
    );
  }
  if (typeof value === "boolean")
    return [{ key: prefix, value: value ? "Yes" : "No" }];
  return [{ key: prefix, value: String(value) }];
}

/** Short organization codes (branches, departments): stored uppercase. */
export const CODE = /^[A-Z0-9][A-Z0-9_-]{0,19}$/;
export const codeField = z
  .string()
  .trim()
  .refine(
    (v) => CODE.test(v.toUpperCase()),
    "Use 1–20 letters, digits, dashes or underscores",
  );
