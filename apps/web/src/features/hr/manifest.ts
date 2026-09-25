import { IdCard, Link2, UserPlus } from "lucide-react";
import type { ModuleManifest } from "@/features/modules/types";
import { statusLabel } from "@/components/app/status-badge";
import { hrService } from "./service";

export const hrManifest: ModuleManifest = {
  key: "hr",
  actions: [
    {
      id: "hr.add-employee",
      label: "Add employee",
      href: "/hr/employees/new",
      icon: UserPlus,
      permission: "hr.write",
      keywords: ["employee", "hire", "staff", "person", "hr"],
    },
    {
      id: "hr.onboarding-link",
      label: "Send onboarding link",
      href: "/hr/onboarding?create=1",
      icon: Link2,
      permission: "hr.write",
      keywords: [
        "onboarding",
        "new employee",
        "joining",
        "cnic",
        "form",
        "link",
      ],
    },
  ],
  search: {
    key: "employees",
    label: "Employees",
    permission: "hr.read",
    icon: IdCard,
    search: async (query) => {
      const page = await hrService.employees({ search: query, pageSize: 5 });
      return page.items.map((employee) => ({
        id: employee.id,
        title: employee.full_name,
        subtitle: [
          employee.job_title,
          employee.department_name,
          statusLabel(employee.status),
        ]
          .filter(Boolean)
          .join(" · "),
        href: `/hr/employees/${employee.id}`,
      }));
    },
  },
};
