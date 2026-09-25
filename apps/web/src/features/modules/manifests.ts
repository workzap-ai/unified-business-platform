import { adminManifest } from "@/features/admin/manifest";
import { billingManifest } from "@/features/billing/manifest";
import { catalogManifest } from "@/features/catalog/manifest";
import { customersManifest } from "@/features/customers/manifest";
import {
  documentsManifest,
  quotesSearchManifest,
} from "@/features/documents/manifest";
import { financeManifest } from "@/features/finance/manifest";
import { hrManifest } from "@/features/hr/manifest";
import { integrationsManifest } from "@/features/integrations/manifest";
import { piManifest } from "@/features/pi/manifest";
import type { ModuleManifest } from "./types";

/**
 * Optional per-module shell capabilities (quick actions, record search). A new module
 * adds its manifest here; navigation itself comes from the navigation registry.
 * Order here is the order of quick actions and search groups in the shell.
 */
export const MODULE_MANIFESTS: ModuleManifest[] = [
  customersManifest,
  catalogManifest,
  documentsManifest,
  quotesSearchManifest,
  billingManifest,
  financeManifest,
  hrManifest,
  piManifest,
  adminManifest,
  integrationsManifest,
];
