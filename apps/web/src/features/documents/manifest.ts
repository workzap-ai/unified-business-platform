import { FileText, ShoppingCart } from "lucide-react";
import { formatMoney } from "@/lib/format";
import type { ModuleManifest } from "@/features/modules/types";
import { documentsService } from "./service";

/** Quick actions + order record search for the command menu. Registered by the shell owner. */
export const documentsManifest: ModuleManifest = {
  key: "orders",
  actions: [
    {
      id: "quotes.create",
      label: "Create quote",
      href: "/quotes/new",
      icon: FileText,
      permission: "quotes.write",
      keywords: ["new quote", "proposal", "estimate"],
    },
    {
      id: "orders.create",
      label: "Create order",
      href: "/orders/new",
      icon: ShoppingCart,
      permission: "orders.write",
      keywords: ["new order", "sale"],
    },
  ],
  search: {
    key: "orders",
    label: "Orders",
    permission: "orders.read",
    icon: ShoppingCart,
    search: async (query) => {
      const page = await documentsService.orders({
        search: query,
        pageSize: 5,
      });
      return page.items.map((o) => ({
        id: o.id,
        title: o.number,
        subtitle: [o.customer_name, formatMoney(o.total, o.currency)]
          .filter(Boolean)
          .join(" · "),
        href: `/orders/${o.id}`,
      }));
    },
  },
};

/** Quote record search (separate provider so both appear in the command menu). */
export const quotesSearchManifest: ModuleManifest = {
  key: "quotes",
  search: {
    key: "quotes",
    label: "Quotes",
    permission: "quotes.read",
    icon: FileText,
    search: async (query) => {
      const page = await documentsService.quotes({
        search: query,
        pageSize: 5,
      });
      return page.items.map((q) => ({
        id: q.id,
        title: q.number,
        subtitle: [q.customer_name, formatMoney(q.total, q.currency)]
          .filter(Boolean)
          .join(" · "),
        href: `/quotes/${q.id}`,
      }));
    },
  },
};
