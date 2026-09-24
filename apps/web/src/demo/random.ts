/** Deterministic pseudo-random helpers so sample data is varied but stable per seed. */
export function rng(seed: number) {
  let state = seed >>> 0 || 1;
  const next = () => {
    state ^= state << 13;
    state ^= state >>> 17;
    state ^= state << 5;
    return (state >>> 0) / 4294967296;
  };
  return {
    next,
    int: (min: number, max: number) => Math.floor(next() * (max - min + 1)) + min,
    pick: <T>(items: readonly T[]): T => items[Math.floor(next() * items.length)] as T,
    chance: (p: number) => next() < p,
    weighted: <T>(entries: readonly (readonly [T, number])[]): T => {
      const total = entries.reduce((sum, [, w]) => sum + w, 0);
      let roll = next() * total;
      for (const [value, weight] of entries) {
        roll -= weight;
        if (roll <= 0) return value;
      }
      return entries[entries.length - 1]![0];
    },
  };
}

export type Rng = ReturnType<typeof rng>;

const DAY = 86_400_000;

/** ISO timestamp `days` ago (fractional allowed) relative to now, so demos stay current. */
export function daysAgo(days: number, hour?: number): string {
  const date = new Date(Date.now() - days * DAY);
  if (hour !== undefined) date.setHours(hour, (days * 1440) % 60, 0, 0);
  return date.toISOString();
}

export function dateOnly(daysFromToday: number): string {
  const date = new Date(Date.now() + daysFromToday * DAY);
  return date.toISOString().slice(0, 10);
}

export function money(value: number): string {
  return (Math.round(value * 100) / 100).toFixed(2);
}
