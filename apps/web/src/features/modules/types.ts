import type { LucideIcon } from "lucide-react";

/**
 * Module manifest: the frontend half of the product extension kit. Navigation (routes,
 * permissions, product/feature dependencies, order) comes from the navigation registry;
 * a manifest only adds optional capabilities the shell can surface generically.
 */
export type ModuleAction = {
  id: string;
  label: string;
  href: string;
  icon: LucideIcon;
  permission?: string;
  keywords?: string[];
};

export type SearchResult = {
  id: string;
  title: string;
  subtitle?: string;
  href: string;
};

export type SearchProvider = {
  key: string;
  label: string;
  permission: string;
  icon: LucideIcon;
  search: (query: string) => Promise<SearchResult[]>;
};

export type ModuleManifest = {
  key: string;
  actions?: ModuleAction[];
  search?: SearchProvider;
};
