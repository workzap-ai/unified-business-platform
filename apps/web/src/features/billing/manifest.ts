import { FilePlus2, Receipt } from "lucide-react";
import type { ModuleManifest } from "@/features/modules/types";
import { formatMoney } from "@/lib/format";
import { statusLabel } from "@/components/app/status-badge";
import { billingService } from "./service";

export const billingManifest: ModuleManifest = {
  key: "billing",
  actions: [
    {
      id: "billing.new-invoice",
      label: "New invoice",
      href: "/billing/invoices/new",
      icon: FilePlus2,
      permission: "billing.write",
      keywords: ["invoice", "bill", "charge", "billing"],
    },
  ],
  search: {
    key: "invoices",
    label: "Invoices",
    permission: "billing.read",
    icon: Receipt,
    search: async (query) => {
      const page = await billingService.invoices({ search: query, pageSize: 5 });
      return page.items.map((invoice) => ({
        id: invoice.id,
        title: invoice.number,
        subtitle: [
          invoice.customer_name,
          invoice.is_overdue ? "Overdue" : statusLabel(invoice.status),
          formatMoney(invoice.total, invoice.currency),
        ]
          .filter(Boolean)
          .join(" · "),
        href: `/billing/invoices/${invoice.id}`,
      }));
    },
  },
};
