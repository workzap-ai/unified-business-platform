import { z } from "zod";
import { apiRequest } from "@/services/api-client";

/**
 * WhatsApp business profile (what customers see when they open the business profile).
 * Backend: GET/PUT /api/v1/pi/whatsapp/profile.
 */

export const whatsappProfileSchema = z.object({
  connected: z.boolean().catch(false),
  number: z.string().nullable().catch(null),
  profile: z
    .object({
      about: z.string().catch(""),
      description: z.string().catch(""),
      address: z.string().catch(""),
      email: z.string().catch(""),
      vertical: z.string().catch("OTHER"),
      websites: z.array(z.string()).catch([]),
      photo_url: z.string().catch(""),
    })
    .nullable()
    .catch(null),
  verticals: z.array(z.string()).catch([]),
  can_edit: z.boolean().catch(false),
});
export type WhatsAppProfileData = z.infer<typeof whatsappProfileSchema>;
export type WhatsAppProfile = NonNullable<WhatsAppProfileData["profile"]>;

export type WhatsAppProfileInput = Omit<WhatsAppProfile, "photo_url">;

export const whatsappProfileService = {
  get: () => apiRequest("GET", "/pi/whatsapp/profile", whatsappProfileSchema),
  save: (input: WhatsAppProfileInput) =>
    apiRequest("PUT", "/pi/whatsapp/profile", whatsappProfileSchema, {
      body: input,
    }),
};
