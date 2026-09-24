import { z } from "zod";

export const workspaceRefSchema = z.object({
  id: z.string(),
  name: z.string(),
  key: z.string().nullable().optional(),
  kind: z.string().nullable().optional(),
});

export const sessionSchema = z.object({
  user: z.object({
    id: z.string(),
    email: z.string(),
    display_name: z.string(),
  }),
  tenant: workspaceRefSchema.nullable(),
  environment: workspaceRefSchema.nullable(),
  branch: workspaceRefSchema.nullable(),
  permissions: z.array(z.string()),
  roles: z.array(z.string()),
});

export const tenantSchema = z.object({
  id: z.string(),
  name: z.string(),
  slug: z.string(),
});

export const environmentSchema = z.object({
  id: z.string(),
  key: z.string(),
  name: z.string(),
  kind: z.enum(["production", "staging", "development"]),
  status: z.enum(["active", "archived"]),
  is_default: z.boolean(),
});

export type Session = z.infer<typeof sessionSchema>;
export type WorkspaceRef = z.infer<typeof workspaceRefSchema>;
export type Tenant = z.infer<typeof tenantSchema>;
export type Environment = z.infer<typeof environmentSchema>;

export type LoginInput = { email: string; password: string };
export type RegisterInput = {
  email: string;
  password: string;
  display_name: string;
  organization_name: string;
};
