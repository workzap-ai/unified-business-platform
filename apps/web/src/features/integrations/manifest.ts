import { KeyRound, Plug } from "lucide-react";
import type { ModuleManifest } from "@/features/modules/types";
import { integrationsService } from "./service";

/** Integrations shell capabilities: quick actions and connection search. */
export const integrationsManifest: ModuleManifest = {
  key: "integrations",
  actions: [
    {
      id: "integrations.connect",
      label: "Connect an integration",
      href: "/settings/integrations",
      icon: Plug,
      permission: "integrations.manage",
      keywords: [
        "integration",
        "connect",
        "webhook",
        "whatsapp",
        "smtp",
        "provider",
      ],
    },
    {
      id: "integrations.create-api-key",
      label: "Create API key",
      href: "/settings/integrations/api-keys?create=1",
      icon: KeyRound,
      permission: "api_keys.manage",
      keywords: ["api", "key", "token", "developer", "access"],
    },
  ],
  search: {
    key: "integrations-connections",
    label: "Connections",
    permission: "integrations.read",
    icon: Plug,
    search: async (query) => {
      const q = query.trim().toLowerCase();
      const page = await integrationsService.connections({ pageSize: 100 });
      return page.items
        .filter(
          (c) =>
            c.display_name.toLowerCase().includes(q) ||
            c.integration_key.toLowerCase().includes(q),
        )
        .slice(0, 5)
        .map((c) => ({
          id: c.id,
          title: c.display_name,
          subtitle: `${c.integration_key.replace(/_/g, " ")} · ${c.status}`,
          href: `/settings/integrations/connections/${c.id}`,
        }));
    },
  },
};
