// Measure clicks, never chat content. No vendor is wired yet: events are dispatched
// as a DOM event and pushed to window.dataLayer if one exists. No cookies are set.
export function track(name: string, props: Record<string, string> = {}) {
  if (typeof window === "undefined") return;
  document.dispatchEvent(
    new CustomEvent("pi:track", { detail: { name, ...props } }),
  );
  const w = window as unknown as { dataLayer?: unknown[] };
  (w.dataLayer ??= []).push({ event: name, ...props });
}
