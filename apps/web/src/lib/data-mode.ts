/**
 * Where feature services read data from.
 *
 * - "live": the platform API (production default in container builds).
 * - "demo": in-browser sample data that satisfies the same contracts. Used for UI work
 *   and demos when the API is not running. The shell shows a persistent "Sample data"
 *   marker in this mode so fixtures are never mistaken for real business data.
 */
export type DataMode = "demo" | "live";

export const dataMode: DataMode =
  process.env.NEXT_PUBLIC_DATA_MODE === "demo" ? "demo" : "live";

export const isDemo = dataMode === "demo";

/** Pick the implementation for the current data mode. */
export function select<T>(implementations: { demo: T; live: T }): T {
  return implementations[dataMode];
}

/** Small artificial latency so demo mode exercises loading states realistically. */
export function demoDelay(ms = 180): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
