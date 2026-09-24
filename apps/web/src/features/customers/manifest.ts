import { Target, UserPlus, Users } from "lucide-react";
import type { ModuleManifest } from "@/features/modules/types";
import { customersService } from "./service";

/** Customers/CRM + Sales shell capabilities: quick actions and customer record search. */
export const customersManifest: ModuleManifest = {
  key: "customers",
  actions: [
    {
      id: "customers.add",
      label: "Add customer",
      href: "/customers/new",
      icon: UserPlus,
      permission: "customers.write",
      keywords: ["new customer", "contact", "crm", "client"],
    },
    {
      id: "sales.new-lead",
      label: "New lead",
      href: "/sales/leads?new=1",
      icon: Target,
      permission: "sales.write",
      keywords: ["lead", "opportunity", "deal", "pipeline", "sales"],
    },
  ],
  search: {
    key: "customers",
    label: "Customers",
    permission: "customers.read",
    icon: Users,
    search: async (query) => {
      const page = await customersService.list({ search: query, pageSize: 5 });
      return page.items.map((c) => ({
        id: c.id,
        title: c.name,
        subtitle: c.phone ?? c.company ?? c.email ?? undefined,
        href: `/customers/${c.id}`,
      }));
    },
  },
};
