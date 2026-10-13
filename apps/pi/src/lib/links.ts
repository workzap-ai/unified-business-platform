/**
 * Links the API writes for the whole platform (notifications, a deal's next step) use
 * the shared page paths. This turns them into pi app pages, so a pi business never
 * lands on a page that doesn't exist here.
 */
const RULES: [RegExp, string | ((m: RegExpMatchArray) => string)][] = [
  [/^\/pi\/inbox(\?.*)?$/, (m) => `/inbox${m[1] ?? ""}`],
  [/^\/pi\/handoffs(\/.*)?$/, "/inbox/handoffs"],
  [/^\/pi\/requests(\?.*)?$/, (m) => `/requests${m[1] ?? ""}`],
  [/^\/pi\/team(\?.*)?$/, (m) => `/team${m[1] ?? ""}`],
  [/^\/pi\/knowledge(\/.*)?$/, "/my-pi/knowledge"],
  [/^\/pi\/settings\/whatsapp.*$/, "/settings/whatsapp"],
  [/^\/pi\/settings(\/.*)?$/, "/my-pi/settings"],
  [/^\/pi\/analytics(\/.*)?$/, "/analytics"],
  [/^\/pi\/deals(\/.*)?$/, "/deals"],
  [/^\/sales\/leads\/([^/?#]+)/, (m) => `/deals/${m[1]}`],
  [/^\/(sales|quotes|orders|invoices|billing)(\/.*)?$/, "/deals"],
  [/^\/customers\/([^/?#]+)/, (m) => `/customers/${m[1]}`],
];

export function piLink(link: string | null | undefined): string | null {
  if (!link) return null;
  if (/^https?:\/\//.test(link)) return link;
  for (const [pattern, target] of RULES) {
    const match = link.match(pattern);
    if (match) return typeof target === "string" ? target : target(match);
  }
  return link;
}
