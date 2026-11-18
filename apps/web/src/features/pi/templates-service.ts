import { z } from "zod";
import { apiRequest } from "@/services/api-client";

/**
 * WhatsApp templates: the messages WhatsApp lets pi start outside a live chat. List, create (with
 * {{1}} variables), edit, and send a first message to one number. Backend:
 * apps/api/app/modules/pi_saas/whatsapp_tools.py (/api/v1/pi/whatsapp/templates). Reading needs
 * pi.read; creating, editing and sending need pi.settings.manage.
 */

export const templateSchema = z.object({
  id: z.string().catch(""),
  name: z.string(),
  language: z.string(),
  status: z.string().catch(""),
  category: z.string().catch(""),
  body: z.string().catch(""),
  variables: z.number().catch(0),
  fillable: z.boolean().catch(false),
});
export type Template = z.infer<typeof templateSchema>;

const listSchema = z.object({
  templates: z.array(templateSchema),
  number: z.string().nullable().catch(null),
  connected: z.boolean().catch(false),
});

const doneSchema = z.object({}).passthrough();

export type NewTemplate = {
  name: string;
  language: string;
  category: "UTILITY" | "MARKETING";
  body: string;
  examples: string[];
};

export const piTemplatesService = {
  list: () => apiRequest("GET", "/pi/whatsapp/templates", listSchema),
  create: (input: NewTemplate) =>
    apiRequest("POST", "/pi/whatsapp/templates", doneSchema, { body: input }),
  edit: (id: string, input: { body: string; examples: string[] }) =>
    apiRequest("PUT", `/pi/whatsapp/templates/${id}`, doneSchema, {
      body: input,
    }),
  send: (input: {
    phone: string;
    name: string;
    language: string;
    values: string[];
    consent: boolean;
  }) =>
    apiRequest("POST", "/pi/whatsapp/templates/send", doneSchema, {
      body: input,
    }),
};
