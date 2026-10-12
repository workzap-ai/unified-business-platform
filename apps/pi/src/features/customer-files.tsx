"use client";

/**
 * Files kept for one customer (in the database, no S3 needed): what they sent on
 * WhatsApp, files the team uploaded and the PDF receipts made for their payments.
 * Downloads go through the same-origin API, so the pi session cookie applies.
 * API: app/modules/customers/file_routes.py.
 */
import { useQuery } from "@tanstack/react-query";
import {
  Download,
  FileText,
  Image as ImageIcon,
  MessageCircle,
  Paperclip,
  Receipt,
  Trash2,
  Upload,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import {
  Badge,
  Button,
  Card,
  CardSection,
  ErrorState,
  Skeleton,
} from "@/components/ui";
import { api, del, errorText, get } from "@/lib/api";
import { dateTime, timeAgo } from "@/lib/format";
import { useAction, useBusinessKey, useCan } from "@/lib/session";

export interface CustomerFile {
  id: string;
  customer_id: string;
  conversation_id: string | null;
  message_id: string | null;
  source: "whatsapp" | "upload" | "receipt";
  name: string;
  mime: string;
  size: number;
  ref_type: string | null;
  ref_id: string | null;
  uploaded_by: string;
  created_at: string;
}

/** The API's upload limit (customers/files.py MAX_BYTES). */
const MAX_BYTES = 10 * 1024 * 1024;

export function fileDownloadUrl(fileId: string): string {
  return `/api/v1/pi-app/customer-files/${fileId}/download`;
}

export function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

const SOURCE: Record<
  CustomerFile["source"],
  { label: string; tone: "info" | "neutral" | "success" }
> = {
  whatsapp: { label: "WhatsApp", tone: "info" },
  upload: { label: "Uploaded", tone: "neutral" },
  receipt: { label: "Receipt", tone: "success" },
};

/** "Files": the customer's documents, photos and receipts, newest first. */
export function CustomerFiles({ customerId }: { customerId: string }) {
  const key = useBusinessKey();
  const can = useCan();
  const write = can("customers.write");
  const files = useQuery({
    queryKey: key(["customer-files", customerId]),
    queryFn: () => get<CustomerFile[]>(`/customers/${customerId}/files`),
  });
  const input = React.useRef<HTMLInputElement>(null);
  const [deleting, setDeleting] = React.useState<string | null>(null);
  const upload = useAction(
    (file: File) => {
      const data = new FormData();
      data.set("file", file);
      return api<CustomerFile>("POST", `/customers/${customerId}/files`, data, {
        timeoutMs: 120_000,
      });
    },
    {
      success: "File added",
      invalidate: [["customer-files", customerId]],
      onSuccess: () => {
        if (input.current) input.current.value = "";
      },
    },
  );
  const remove = useAction(
    (fileId: string) => del(`/customer-files/${fileId}`),
    {
      success: "File removed",
      invalidate: [["customer-files", customerId]],
      onSuccess: () => setDeleting(null),
    },
  );

  function choose(file: File | undefined) {
    if (!file) return;
    if (file.size > MAX_BYTES) {
      toast.error("That file is over 10 MB. Choose a smaller one.");
      if (input.current) input.current.value = "";
      return;
    }
    upload.mutate(file);
  }

  return (
    <Card>
      <CardSection>
        <div className="mb-3 flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <h2 className="flex items-center gap-2 text-base font-semibold">
              <Paperclip className="size-4 text-muted-foreground" aria-hidden />
              Files
            </h2>
            <p className="text-sm text-muted-foreground">
              Documents and photos from WhatsApp, your uploads and receipts.
            </p>
          </div>
          {write ? (
            <>
              <input
                ref={input}
                type="file"
                className="sr-only"
                aria-label="Choose a file to upload"
                accept=".pdf,.docx,.txt,image/png,image/jpeg,image/webp"
                onChange={(e) => choose(e.target.files?.[0])}
              />
              <Button
                size="sm"
                variant="secondary"
                loading={upload.isPending}
                onClick={() => input.current?.click()}
              >
                <Upload className="size-4" aria-hidden /> Upload
              </Button>
            </>
          ) : null}
        </div>
        {files.isPending ? (
          <Skeleton className="h-16 w-full" />
        ) : files.isError ? (
          <ErrorState
            message={errorText(files.error)}
            onRetry={() => files.refetch()}
          />
        ) : files.data.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No files yet. Documents and photos the customer sends on WhatsApp
            appear here by themselves.
          </p>
        ) : (
          <ul className="divide-y divide-border">
            {files.data.map((file) => {
              const Icon =
                file.source === "receipt"
                  ? Receipt
                  : file.mime.startsWith("image/")
                    ? ImageIcon
                    : FileText;
              const source = SOURCE[file.source] ?? SOURCE.upload;
              return (
                <li key={file.id} className="py-2.5 first:pt-0 last:pb-0">
                  <div className="flex items-start gap-3">
                    <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg bg-surface-muted text-muted-foreground">
                      <Icon className="size-4" aria-hidden />
                    </span>
                    <div className="min-w-0 flex-1">
                      <a
                        href={fileDownloadUrl(file.id)}
                        className="block truncate text-sm font-medium text-accent hover:underline"
                        title={file.name}
                        data-user-text
                      >
                        {file.name}
                      </a>
                      <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                        <Badge tone={source.tone}>
                          {file.source === "whatsapp" ? (
                            <MessageCircle className="size-3" aria-hidden />
                          ) : null}
                          {source.label}
                        </Badge>
                        <span>{fileSize(file.size)}</span>
                        <span title={dateTime(file.created_at)}>
                          {timeAgo(file.created_at)}
                        </span>
                      </p>
                    </div>
                    <div className="flex shrink-0">
                      <Button asChild variant="ghost" size="icon">
                        <a
                          href={fileDownloadUrl(file.id)}
                          aria-label={`Download ${file.name}`}
                        >
                          <Download className="size-4" aria-hidden />
                        </a>
                      </Button>
                      {write && file.source !== "receipt" ? (
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={`Remove ${file.name}`}
                          onClick={() => setDeleting(file.id)}
                        >
                          <Trash2 className="size-4" aria-hidden />
                        </Button>
                      ) : null}
                    </div>
                  </div>
                  {deleting === file.id ? (
                    <div className="mt-2 flex flex-wrap items-center gap-2 ps-12 text-sm">
                      <span>Remove this file?</span>
                      <Button
                        size="sm"
                        variant="danger"
                        loading={remove.isPending}
                        onClick={() => remove.mutate(file.id)}
                      >
                        Remove
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setDeleting(null)}
                      >
                        Keep
                      </Button>
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </CardSection>
    </Card>
  );
}
