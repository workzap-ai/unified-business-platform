import { z } from "zod";

/** A registered navigation definition (mirrors the backend NavDefinition). */
export type NavDefinition = {
  key: string;
  label: string;
  route: string;
  icon: string;
  section: "main" | "admin";
  sort_order: number;
  type: "module" | "product" | "page";
  parent: string | null;
  enabled: boolean;
  visible: boolean;
  required_permissions: string[];
  any_permissions: string[];
  required_roles: string[];
  required_product: string | null;
  required_feature: string | null;
  environment_scope: string[] | null;
  badge: string | null;
  analytics_id: string;
  keywords: string[];
  description: string;
};

export type NavItem = {
  key: string;
  label: string;
  route: string;
  icon: string;
  type: string;
  section: string;
  sort_order: number;
  badge: number | null;
  analytics_id: string;
  keywords: string[];
  description: string;
  children: NavItem[];
};

export const navItemSchema: z.ZodType<NavItem> = z.lazy(() =>
  z.object({
    key: z.string(),
    label: z.string(),
    route: z.string().startsWith("/"),
    icon: z.string(),
    type: z.string(),
    section: z.string(),
    sort_order: z.number(),
    badge: z.number().nullable(),
    analytics_id: z.string(),
    keywords: z.array(z.string()),
    description: z.string(),
    children: z.array(navItemSchema),
  }),
);

export const navigationSchema = z.object({
  sections: z.array(
    z.object({
      key: z.enum(["main", "admin"]),
      label: z.string(),
      customized: z.boolean(),
      items: z.array(navItemSchema),
    }),
  ),
});

export type Navigation = z.infer<typeof navigationSchema>;
export type NavSection = Navigation["sections"][number];
export type SectionKey = NavSection["key"];
