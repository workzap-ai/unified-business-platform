import { Package, PackagePlus, SlidersHorizontal } from "lucide-react";
import type { ModuleManifest } from "@/features/modules/types";
import { catalogService } from "./service";
import { priceRange } from "./lib";

export const catalogManifest: ModuleManifest = {
  key: "catalog",
  actions: [
    {
      id: "catalog.add-product",
      label: "Add product",
      href: "/catalog/products/new",
      icon: PackagePlus,
      permission: "catalog.write",
      keywords: ["new product", "create product", "sku", "item"],
    },
    {
      id: "inventory.adjust-stock",
      label: "Adjust stock",
      href: "/inventory/stock",
      icon: SlidersHorizontal,
      permission: "inventory.adjust",
      keywords: [
        "receive stock",
        "stock count",
        "inventory adjustment",
        "receipt",
      ],
    },
  ],
  search: {
    key: "products",
    label: "Products",
    permission: "catalog.read",
    icon: Package,
    search: async (query) => {
      const page = await catalogService.products({
        search: query,
        pageSize: 5,
      });
      return page.items.map((p) => {
        const price = priceRange(p.min_price, p.max_price, p.currency);
        return {
          id: p.id,
          title: p.name,
          subtitle: price !== "—" ? price : (p.category_name ?? undefined),
          href: `/catalog/products/${p.id}`,
        };
      });
    },
  },
};
