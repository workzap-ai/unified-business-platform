import { Bot, MessagesSquare } from "lucide-react";
import { ServiceNotConnectedError } from "@/services/api-client";
import type { ModuleManifest } from "@/features/modules/types";
import { piService } from "./service";

/** PI shell capabilities: quick action and conversation search for the command menu. */
export const piManifest: ModuleManifest = {
  key: "pi",
  actions: [
    {
      id: "pi.open-inbox",
      label: "Open PI inbox",
      href: "/pi/inbox",
      icon: Bot,
      permission: "pi.read",
      keywords: ["whatsapp", "conversations", "ai", "chat", "messages"],
    },
  ],
  search: {
    key: "pi-conversations",
    label: "Conversations",
    permission: "pi.read",
    icon: MessagesSquare,
    search: async (query) => {
      try {
        const page = await piService.conversations({ search: query });
        return page.items.slice(0, 5).map((c) => ({
          id: c.id,
          title: c.customer_name,
          subtitle: c.last_message_preview,
          href: `/pi/inbox?conversation=${encodeURIComponent(c.id)}`,
        }));
      } catch (error) {
        if (error instanceof ServiceNotConnectedError) return [];
        throw error;
      }
    },
  },
};
