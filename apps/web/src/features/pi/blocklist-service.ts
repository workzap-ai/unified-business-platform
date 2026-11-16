import { z } from "zod";
import { apiRequest } from "@/services/api-client";

/**
 * The blocklist: numbers pi no longer answers. A message from a blocked sender is dropped before
 * anything is stored or sent to a model. Backend: apps/api/app/modules/pi_saas/blocklist/
 * (/api/v1/pi/blocklist). Reading needs pi.read, changing needs pi.settings.manage.
 */

export const blockSchema = z.object({
  id: z.string(),
  value: z.string(),
  masked: z.string(),
  kind: z.enum(["number", "prefix"]).catch("number"),
  reason: z.string().catch(""),
  note: z.string().catch(""),
  source: z.enum(["manual", "chat", "bulk"]).catch("manual"),
  active: z.boolean(),
  hits: z.number().catch(0),
  last_hit_at: z.string().nullable().catch(null),
  created_at: z.string(),
});
export type Block = z.infer<typeof blockSchema>;

const listSchema = z.object({
  items: z.array(blockSchema),
  active: z.number().catch(0),
  blocked_messages: z.number().catch(0),
});

const suggestionsSchema = z.object({
  ranges: z.array(
    z.object({
      prefix: z.string(),
      chats: z.number(),
      first_seen: z.string(),
      last_seen: z.string(),
    }),
  ),
});

const addedSchema = blockSchema.extend({ closed_chats: z.number().catch(0) });
export type BlockInput = {
  value: string;
  kind: "number" | "prefix";
  reason: string;
  note: string;
};

export const piBlocklistService = {
  list: () => apiRequest("GET", "/pi/blocklist", listSchema),
  suggestions: () =>
    apiRequest("GET", "/pi/blocklist/suggestions", suggestionsSchema),
  add: (input: BlockInput) =>
    apiRequest("POST", "/pi/blocklist", addedSchema, {
      body: { ...input, close_chats: true },
    }),
  fromConversation: (conversationId: string, reason = "") =>
    apiRequest(
      "POST",
      `/pi/blocklist/from-conversation/${conversationId}`,
      addedSchema,
      { body: { reason } },
    ),
  unblock: (id: string) =>
    apiRequest("DELETE", `/pi/blocklist/${id}`, blockSchema),
  reblock: (block: Block) =>
    apiRequest("POST", "/pi/blocklist", addedSchema, {
      body: {
        value: block.value,
        kind: block.kind,
        reason: block.reason,
        note: block.note,
        close_chats: true,
      },
    }),
};
