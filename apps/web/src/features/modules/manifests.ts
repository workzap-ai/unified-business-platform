import type { ModuleManifest } from "./types";

/**
 * Optional per-module shell capabilities (quick actions, record search). A new module
 * adds its manifest here; navigation itself comes from the navigation registry.
 */
export const MODULE_MANIFESTS: ModuleManifest[] = [];
