import { z } from "zod";
import { apiRequest, ApiError } from "@/services/api-client";
import { demoDelay, select } from "@/lib/data-mode";
import { demoCollection } from "@/demo/store";
import { daysAgo } from "@/demo/random";

export const productStateSchema = z.object({
  key: z.string(),
  name: z.string(),
  description: z.string(),
  category: z.string(),
  features: z.array(z.string()),
  tenant_status: z.enum(["installed", "suspended"]).nullable(),
  environment_enabled: z.boolean(),
  enabled_features: z.array(z.string()),
  installed_at: z.string().nullable(),
});
export type ProductState = z.infer<typeof productStateSchema>;

export interface ProductsService {
  list(): Promise<ProductState[]>;
  install(key: string): Promise<ProductState[]>;
  setEnabled(key: string, enabled: boolean): Promise<ProductState[]>;
}

const PI_FEATURES = [
  "text",
  "voice",
  "vision",
  "knowledge",
  "orders",
  "quotes",
  "handoff",
];

const demoProducts = demoCollection<ProductState[]>("products", (profile) => {
  const installed =
    profile.kind !== "empty" || profile.tenantId === "tenant-northwind";
  const enabled = profile.kind !== "empty";
  return [
    {
      key: "pi",
      name: "PI",
      description:
        "AI WhatsApp customer assistant: answers questions from verified company data, checks stock, drafts orders and quotes, and hands off to your team.",
      category: "ai",
      features: PI_FEATURES,
      tenant_status: installed ? "installed" : null,
      environment_enabled: enabled,
      enabled_features: enabled ? PI_FEATURES : [],
      installed_at: installed ? daysAgo(96) : null,
    },
  ];
});

const demo: ProductsService = {
  async list() {
    await demoDelay();
    return demoProducts().map((p) => ({ ...p }));
  },
  async install(key) {
    await demoDelay(500);
    const product = demoProducts().find((p) => p.key === key);
    if (!product) throw new ApiError(404, "RESOURCE_NOT_FOUND");
    product.tenant_status = "installed";
    product.environment_enabled = true;
    product.enabled_features = [...product.features];
    product.installed_at ??= new Date().toISOString();
    return demo.list();
  },
  async setEnabled(key, enabled) {
    await demoDelay(300);
    const product = demoProducts().find((p) => p.key === key);
    if (!product) throw new ApiError(404, "RESOURCE_NOT_FOUND");
    product.environment_enabled = enabled;
    product.enabled_features = enabled ? [...product.features] : [];
    return demo.list();
  },
};

const live: ProductsService = {
  list: () => apiRequest("GET", "/products", z.array(productStateSchema)),
  install: (key) =>
    apiRequest("POST", `/products/${key}/install`, z.array(productStateSchema)),
  setEnabled: (key, enabled) =>
    apiRequest(
      "PUT",
      `/products/${key}/environment`,
      z.array(productStateSchema),
      {
        body: { enabled },
      },
    ),
};

export const productsService = select<ProductsService>({ demo, live });

/** Demo-only helper used by the demo navigation resolver. */
export function demoEnabledProducts(): Record<string, string[]> {
  return Object.fromEntries(
    demoProducts()
      .filter((p) => p.tenant_status === "installed" && p.environment_enabled)
      .map((p) => [p.key, p.enabled_features]),
  );
}
