import { Wallet } from "lucide-react";
import type { ModuleManifest } from "@/features/modules/types";

export const financeManifest: ModuleManifest = {
  key: "finance",
  actions: [
    {
      id: "finance.record-expense",
      label: "Record expense",
      href: "/finance/expenses?new=1",
      icon: Wallet,
      permission: "finance.write",
      keywords: ["expense", "spend", "cost", "bill", "finance"],
    },
  ],
};
