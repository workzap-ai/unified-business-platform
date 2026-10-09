import { z } from "zod";
import { apiRequest, API_BASE } from "@/services/api-client";

/**
 * Customer files kept in the database: what the customer sent on WhatsApp, team
 * uploads and receipts. Backend: apps/api/app/modules/customers/file_routes.py.
 */

export const FILE_SOURCES = ["whatsapp", "upload", "receipt"] as const;

export const customerFileSchema = z.object({
  id: z.string(),
  customer_id: z.string(),
  conversation_id: z.string().nullable(),
  message_id: z.string().nullable(),
  source: z.enum(FILE_SOURCES).catch("upload"),
  name: z.string(),
  mime: z.string(),
  size: z.number(),
  ref_type: z.string().nullable(),
  ref_id: z.string().nullable(),
  uploaded_by: z.string(),
  created_at: z.string(),
});
export type CustomerFile = z.infer<typeof customerFileSchema>;

export const customerFilesService = {
  list: (customerId: string) =>
    apiRequest(
      "GET",
      `/customers/${customerId}/files`,
      z.array(customerFileSchema),
    ),
  upload: (customerId: string, file: File) => {
    const data = new FormData();
    data.set("file", file);
    return apiRequest(
      "POST",
      `/customers/${customerId}/files`,
      customerFileSchema,
      { body: data, timeoutMs: 120000 },
    );
  },
  remove: (fileId: string) =>
    apiRequest<void>("DELETE", `/customer-files/${fileId}`, null),
  downloadUrl: (fileId: string) =>
    `${API_BASE}/customer-files/${fileId}/download`,
};

export function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
