/** Recently opened records (per browser, per workspace) for the command menu. */
export type RecentItem = {
  href: string;
  title: string;
  kind: string;
  at: number;
};

const KEY = "platform.recent";
const MAX = 8;

export function readRecent(scope: string): RecentItem[] {
  try {
    const raw = window.localStorage.getItem(`${KEY}.${scope}`);
    return raw ? (JSON.parse(raw) as RecentItem[]) : [];
  } catch {
    return [];
  }
}

export function pushRecent(scope: string, item: Omit<RecentItem, "at">) {
  try {
    const next = [
      { ...item, at: Date.now() },
      ...readRecent(scope).filter((r) => r.href !== item.href),
    ].slice(0, MAX);
    window.localStorage.setItem(`${KEY}.${scope}`, JSON.stringify(next));
  } catch {
    /* storage unavailable */
  }
}
