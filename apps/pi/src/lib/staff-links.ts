/**
 * Where a staff member goes to review a conversation. NEXT_PUBLIC_OWNER_OS_URL (baked in at build
 * time, see apps/pi/.env.example) is the origin of the Owner OS staff app. Without a valid value
 * the Pi app's own review page is used, so the link never goes nowhere.
 */

/** The configured Owner OS origin without a trailing slash, or null when unset or not http(s). */
export function ownerOsOrigin(
  raw: string | undefined = process.env.NEXT_PUBLIC_OWNER_OS_URL,
): string | null {
  const value = (raw ?? "").trim();
  if (!value) return null;
  try {
    const url = new URL(value);
    if (url.protocol !== "https:" && url.protocol !== "http:") return null;
    return url.origin;
  } catch {
    return null;
  }
}

export type StaffReviewLink = { href: string; external: boolean };

export function staffReviewLink(
  conversationId: string,
  raw?: string,
): StaffReviewLink {
  const id = encodeURIComponent(conversationId);
  const origin = ownerOsOrigin(raw ?? process.env.NEXT_PUBLIC_OWNER_OS_URL);
  return origin
    ? { href: `${origin}/pi/review?c=${id}`, external: true }
    : { href: `/brain/review?c=${id}`, external: false };
}
