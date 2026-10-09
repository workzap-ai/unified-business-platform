"use client";
import { useRef, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/display";
import { ErrorState, Notice } from "@/components/app/states";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import { workflowService } from "./workflow-service";
import { toast } from "sonner";
import { MessageCircle } from "lucide-react";
import { DealDeliveryDialog } from "@/features/sales/deal-delivery-dialog";
import {
  dealErrorMessage,
  dealService,
  type DeliveryResult,
} from "@/features/sales/deal-service";

export function InvoiceIntegrationActions({
  id,
  open,
  draft = false,
}: {
  id: string;
  open: boolean;
  /** A draft can only be issued and sent in one step from here. */
  draft?: boolean;
}) {
  const { can } = useSession();
  const capabilities = useScopedQuery(
    ["integrations", "capabilities"],
    workflowService.capabilities,
  );
  const [url, setUrl] = useState<string | null>(null);
  const emailRequest = useRef<string | null>(null);
  const email = useScopedMutation(
    () => {
      emailRequest.current ??= crypto.randomUUID();
      return workflowService.emailInvoice(id, emailRequest.current);
    },
    {
      success:
        "Invoice email queued. Delivery status is available in integration activity.",
      invalidate: [["integrations"]],
      onSuccess: () => {
        emailRequest.current = null;
      },
    },
  );
  // One step: issue if needed, then the pay link on WhatsApp and by email.
  const [delivered, setDelivered] = useState<DeliveryResult | null>(null);
  const sendLink = useScopedMutation(() => dealService.sendPaymentLink(id), {
    invalidate: [["invoices"], ["deals"], ["integrations"], ["billing"]],
    toastErrors: false,
    onSuccess: (r) => {
      if (r.pay_link) setUrl(r.pay_link);
      const parts = [
        r.whatsapp ? "WhatsApp" : null,
        r.email ? "email" : null,
      ].filter(Boolean);
      if (parts.length)
        toast.success(`Payment link sent by ${parts.join(" and ")}`);
      if (r.email_error) toast.message(`Email not sent: ${r.email_error}`);
      if (!r.pay_link)
        toast.message(
          "No online payment is set up, so the invoice went without a pay link.",
        );
      if (r.whatsapp && r.whatsapp.delivery !== "sent")
        setDelivered(r.whatsapp);
    },
  });
  const checkout = useScopedMutation(() => workflowService.checkout(id), {
    invalidate: [["integrations"]],
    onSuccess: (r) =>
      setUrl(typeof r.output.url === "string" ? r.output.url : null),
  });
  if (!can("billing.write") || !(open || draft)) return null;
  return (
    <Card>
      <CardHeader title="Email and online payment" />
      <CardBody className="space-y-3">
        {capabilities.isError && (
          <ErrorState
            error={capabilities.error}
            onRetry={() => void capabilities.refetch()}
          />
        )}
        <div className="flex flex-wrap gap-2">
          <Button
            loading={sendLink.isPending}
            disabled={sendLink.isPending}
            onClick={() =>
              sendLink.mutate(undefined, {
                onError: (e) =>
                  toast.error(
                    dealErrorMessage(e, "The payment link couldn't be sent."),
                  ),
              })
            }
          >
            <MessageCircle />{" "}
            {draft ? "Issue and send payment link" : "Send payment link"}
          </Button>
          <Button
            variant="secondary"
            disabled={draft || !capabilities.data?.email}
            loading={email.isPending}
            onClick={() => email.mutate(undefined)}
          >
            Email invoice
          </Button>
          <Button
            variant="secondary"
            disabled={draft || !capabilities.data?.payments}
            loading={checkout.isPending}
            onClick={() => checkout.mutate(undefined)}
          >
            Create payment link
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          Send payment link issues a draft invoice, then sends the invoice and
          its pay link on WhatsApp and to the customer&apos;s email. A verified
          payment updates this invoice automatically.
        </p>
        {(!capabilities.data?.email || !capabilities.data?.payments) && (
          <Link
            href="/settings/integrations"
            className="text-sm text-primary underline"
          >
            Set up email or Stripe
          </Link>
        )}
        {url && (
          <Notice tone="success" title="Payment link ready">
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="break-all underline"
            >
              Open Stripe payment page
            </a>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => void navigator.clipboard.writeText(url)}
            >
              Copy link
            </Button>
          </Notice>
        )}
        <DealDeliveryDialog
          result={delivered}
          noun="invoice"
          onOpenChange={(open) => !open && setDelivered(null)}
        />
        {email.isError && <ErrorState error={email.error} />}
        {checkout.isError && <ErrorState error={checkout.error} />}
      </CardBody>
    </Card>
  );
}

export function RecordAttachments({
  type,
  id,
  permission,
  onlyWithStorage = false,
}: {
  type: "invoice" | "customer" | "order";
  id: string;
  permission: string;
  /** Hidden unless S3 is connected or S3 files exist (a page with its own files card). */
  onlyWithStorage?: boolean;
}) {
  const { can } = useSession();
  const capabilities = useScopedQuery(
    ["integrations", "capabilities"],
    workflowService.capabilities,
  );
  const files = useScopedQuery(["files", type, id], () =>
    workflowService.files(type, id),
  );
  const [selection, setSelection] = useState<{
    file: File;
    requestId: string;
  } | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const upload = useScopedMutation(
    (v: { file: File; requestId: string }) =>
      workflowService.upload(type, id, v.file, v.requestId),
    {
      invalidate: [["files", type, id], ["integrations"]],
      success: "File uploaded",
      onSuccess: () => {
        setSelection(null);
        if (input.current) input.current.value = "";
      },
    },
  );
  const remove = useScopedMutation(
    (fileId: string) => workflowService.remove(fileId),
    {
      invalidate: [["files", type, id]],
      success: "Attachment removed",
      onSuccess: () => setDeleting(null),
    },
  );
  if (onlyWithStorage && !capabilities.data?.storage && !files.data?.length)
    return null;
  return (
    <Card>
      <CardHeader
        title={onlyWithStorage ? "S3 attachments" : "Attachments"}
        description="Files stored in this workspace's connected S3 storage."
      />
      <CardBody className="space-y-3">
        {files.isError ? (
          <ErrorState
            error={files.error}
            onRetry={() => void files.refetch()}
          />
        ) : files.isPending ? (
          <p className="text-sm">Loading attachments…</p>
        ) : !files.data?.length ? (
          <p className="text-sm text-muted-foreground">No attachments yet.</p>
        ) : (
          <ul className="space-y-2">
            {files.data.map((file) => (
              <li key={file.id} className="rounded border p-2 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  {file.status === "succeeded" ? (
                    <a
                      href={workflowService.downloadUrl(file.id)}
                      className="break-all text-primary underline"
                    >
                      {String(file.output.name ?? "Attachment")}
                    </a>
                  ) : (
                    <span>
                      {file.status}: {file.last_error ?? "Upload incomplete"}
                    </span>
                  )}
                  {can(permission) && (
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => setDeleting(file.id)}
                    >
                      Remove
                    </Button>
                  )}
                </div>
                {deleting === file.id && (
                  <div className="mt-2 flex gap-2">
                    <Button
                      size="sm"
                      variant="danger-outline"
                      loading={remove.isPending}
                      onClick={() => remove.mutate(file.id)}
                    >
                      Confirm removal
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setDeleting(null)}
                    >
                      Cancel
                    </Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
        {can(permission) && capabilities.data?.storage ? (
          <form
            className="space-y-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (selection) upload.mutate(selection);
            }}
          >
            <label className="block text-sm">
              Attach a file (up to 25 MB)
              <input
                ref={input}
                className="mt-2 block w-full text-sm"
                type="file"
                aria-label="Choose attachment"
                disabled={upload.isPending}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  setSelection(
                    file ? { file, requestId: crypto.randomUUID() } : null,
                  );
                }}
              />
            </label>
            {selection && selection.file.size > 25 * 1024 * 1024 && (
              <p className="text-sm text-danger">
                Choose a file smaller than 25 MB.
              </p>
            )}
            <Button
              size="sm"
              type="submit"
              disabled={!selection || selection.file.size > 25 * 1024 * 1024}
              loading={upload.isPending}
            >
              Upload attachment
            </Button>
          </form>
        ) : (
          <p className="text-xs text-muted-foreground">
            Connect S3 storage in{" "}
            <Link href="/settings/integrations" className="underline">
              Integrations
            </Link>{" "}
            to upload files.
          </p>
        )}
        {upload.isError && <ErrorState error={upload.error} />}
        {remove.isError && <ErrorState error={remove.error} />}
      </CardBody>
    </Card>
  );
}
