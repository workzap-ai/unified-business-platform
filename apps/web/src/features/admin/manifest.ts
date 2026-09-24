import { UserPlus } from "lucide-react";
import type { ModuleManifest } from "@/features/modules/types";

/** Administration quick actions for the shell (Create menu, command menu). */
export const adminManifest: ModuleManifest = {
  key: "admin",
  actions: [
    {
      id: "admin.invite-member",
      label: "Invite member",
      href: "/settings/members?invite=1",
      icon: UserPlus,
      permission: "admin.members.manage",
      keywords: ["member", "user", "invite", "team", "add"],
    },
  ],
};
