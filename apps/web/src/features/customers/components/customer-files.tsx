"use client";

import { useRef, useState } from "react";
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
import { formatDateTime, relativeTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Badge, Card, CardBody, CardHeader } from "@/components/ui/display";
import { ErrorState } from "@/components/app/states";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import {
  customerFilesService,
  fileSize,
  type CustomerFile,
} from "../files-service";

const SOURCE: Record<
  CustomerFile["source"],
  { label: string; tone: "info" | "neutral" | "success" }
> = {
  whatsapp: { label: "WhatsApp", tone: "info" },
  upload: { label: "Uploaded", tone: "neutral" },
  receipt: { label: "Receipt", tone: "success" },
};

/** "Attachments": files kept for this customer (no S3 needed). */
export function CustomerFiles({ customerId }: { customerId: string }) {
  const { can } = useSession();
  const canWrite = can("customers.write");
  const key = ["customers", customerId, "files"];
  const files = useScopedQuery(key, () =>
    customerFilesService.list(customerId),
  );
  const input = useRef<HTMLInputElement>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const upload = useScopedMutation(
    (file: File) => customerFilesService.upload(customerId, file),
    {
      invalidate: [key, ["customers"]],
      success: "File added",
      onSuccess: () => {
        if (input.current) input.current.value = "";
      },
    },
  );
  const remove = useScopedMutation(
    (fileId: string) => customerFilesService.remove(fileId),
    {
      invalidate: [key, ["customers"]],
      success: "File removed",
      onSuccess: () => setDeleting(null),
    },
  );
  return (
    <Card>
      <CardHeader
        title="Attachments"
        icon={<Paperclip />}
        description="Documents and photos from WhatsApp, your uploads and receipts"
        actions={
          canWrite ? (
            <>
              <input
                ref={input}
                type="file"
                className="sr-only"
                aria-label="Choose a file to upload"
                accept=".pdf,.docx,.txt,image/png,image/jpeg,image/webp"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) upload.mutate(file);
                }}
              />
              <Button
                size="xs"
                variant="secondary"
                loading={upload.isPending}
                onClick={() => input.current?.click()}
              >
                <Upload /> Upload
              </Button>
            </>
          ) : undefined
        }
      />
      <CardBody>
        {files.isError ? (
          <ErrorState
            error={files.error}
            onRetry={() => void files.refetch()}
          />
        ) : files.isPending ? (
          <p className="text-[13px] text-muted-foreground">Loading files…</p>
        ) : !files.data.length ? (
          <p className="text-[13px] text-muted-foreground">
            No files yet. Documents and photos the customer sends on WhatsApp
            appear here automatically.
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
              return (
                <li key={file.id} className="py-2.5 first:pt-0 last:pb-0">
                  <div className="flex items-start gap-3">
                    <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md bg-surface-sunken text-muted-foreground">
                      <Icon className="size-4" aria-hidden="true" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <a
                        href={customerFilesService.downloadUrl(file.id)}
                        className="block truncate text-[13px] font-medium text-primary hover:underline"
                        title={file.name}
                      >
                        {file.name}
                      </a>
                      <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                        <Badge tone={SOURCE[file.source].tone}>
                          {file.source === "whatsapp" && (
                            <MessageCircle aria-hidden="true" />
                          )}
                          {SOURCE[file.source].label}
                        </Badge>
                        <span>{fileSize(file.size)}</span>
                        <span title={formatDateTime(file.created_at)}>
                          {relativeTime(file.created_at)}
                        </span>
                      </p>
                    </div>
                    <div className="flex shrink-0 gap-1">
                      <Button size="icon-sm" variant="ghost" asChild>
                        <a
                          href={customerFilesService.downloadUrl(file.id)}
                          aria-label={`Download ${file.name}`}
                        >
                          <Download />
                        </a>
                      </Button>
                      {canWrite && file.source !== "receipt" && (
                        <Button
                          size="icon-sm"
                          variant="ghost"
                          aria-label={`Remove ${file.name}`}
                          onClick={() => setDeleting(file.id)}
                        >
                          <Trash2 />
                        </Button>
                      )}
                    </div>
                  </div>
                  {deleting === file.id && (
                    <div className="mt-2 flex flex-wrap items-center gap-2 pl-11 text-xs">
                      <span>Remove this file?</span>
                      <Button
                        size="xs"
                        variant="danger-outline"
                        loading={remove.isPending}
                        onClick={() => remove.mutate(file.id)}
                      >
                        Remove
                      </Button>
                      <Button
                        size="xs"
                        variant="ghost"
                        onClick={() => setDeleting(null)}
                      >
                        Keep
                      </Button>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </CardBody>
    </Card>
  );
}
