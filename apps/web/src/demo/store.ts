/**
 * In-browser demo data, partitioned by tenant + environment like real scope.
 *
 * Each feature declares its collection with `demoCollection(name, seed)`; the seed runs
 * lazily per workspace. Mutations made through demo services live in memory for the
 * page session so create/edit flows can be demonstrated end to end. None of this is
 * used when NEXT_PUBLIC_DATA_MODE=live.
 */
import { demoScopeKey } from "./workspace";

export type DemoProfile = {
  scopeKey: string;
  tenantId: string;
  environmentId: string;
  /** commerce: rich retail data; services: agency; empty: first-use states. */
  kind: "commerce" | "services" | "empty";
};

const stores = new Map<string, Map<string, unknown>>();

function profileFor(scopeKey: string): DemoProfile {
  const [tenantId = "", environmentId = ""] = scopeKey.split(":");
  const kind =
    environmentId === "env-nw-prod"
      ? "commerce"
      : environmentId === "env-bl-prod"
        ? "services"
        : "empty";
  return { scopeKey, tenantId, environmentId, kind };
}

export function demoCollection<T>(name: string, seed: (profile: DemoProfile) => T): () => T {
  return () => {
    const key = demoScopeKey();
    let bucket = stores.get(key);
    if (!bucket) {
      bucket = new Map();
      stores.set(key, bucket);
    }
    if (!bucket.has(name)) bucket.set(name, seed(profileFor(key)));
    return bucket.get(name) as T;
  };
}

let counter = 0;
export function demoId(prefix: string) {
  counter += 1;
  return `${prefix}-${Date.now().toString(36)}-${counter.toString(36)}`;
}

export function paginate<T>(items: T[], page = 1, pageSize = 25) {
  const start = (page - 1) * pageSize;
  return { items: items.slice(start, start + pageSize), total: items.length, page, page_size: pageSize };
}

export function matches(text: string | null | undefined, query: string | undefined | null) {
  if (!query) return true;
  return (text ?? "").toLowerCase().includes(query.trim().toLowerCase());
}
