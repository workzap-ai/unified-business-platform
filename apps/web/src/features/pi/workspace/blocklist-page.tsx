"use client";

import { useState } from "react";
import { Ban, ShieldCheck, ShieldOff } from "lucide-react";
import { formatDateTime, relativeTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Badge, Card, CardBody } from "@/components/ui/display";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/overlays";
import {
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import { FormField } from "@/components/app/forms";
import { EmptyState, ErrorState, Notice } from "@/components/app/states";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import {
  piBlocklistService,
  type Block,
  type BlockInput,
} from "../blocklist-service";

const SOURCE_LABEL: Record<Block["source"], string> = {
  manual: "Added here",
  chat: "From the inbox",
  bulk: "Bulk",
};

const KEY = [["pi", "blocklist"], ["pi", "conversations"], ["navigation"]];

export function BlocklistPage() {
  return (
    <RequirePermission permission="pi.settings.manage" area="pi">
      <BlocklistView />
    </RequirePermission>
  );
}

function BlocklistView() {
  const { can } = useSession();
  const canManage = can("pi.settings.manage");
  const [adding, setAdding] = useState<BlockInput | null>(null);
  const list = useScopedQuery(["pi", "blocklist"], piBlocklistService.list, {
    refetchInterval: 60_000,
  });
  const suggestions = useScopedQuery(
    ["pi", "blocklist", "suggestions"],
    piBlocklistService.suggestions,
    { enabled: canManage, staleTime: 60_000 },
  );
  const ranges = suggestions.data?.ranges ?? [];
  const items = list.data?.items ?? [];
  return (
    <PageShell>
      <PageHeader
        title="Blocklist"
        description="Numbers pi no longer answers. Their messages are not saved and no AI is used on them, so a flood costs nothing."
        actions={
          canManage ? (
            <Button
              variant="danger"
              onClick={() =>
                setAdding({ value: "", kind: "number", reason: "", note: "" })
              }
            >
              <Ban /> Block a number
            </Button>
          ) : null
        }
      />
      {canManage && ranges.length > 0 && (
        <Notice tone="warning" title="Possible flood" className="mb-4">
          <ul className="mt-2 space-y-2">
            {ranges.map((r) => (
              <li
                key={r.prefix}
                className="flex flex-wrap items-center justify-between gap-2"
              >
                <span className="min-w-0 text-[13px]">
                  {r.chats} open chats from +{r.prefix}… only ever sent photos
                  or files, no text (first {relativeTime(r.first_seen)}, last{" "}
                  {relativeTime(r.last_seen)}).
                </span>
                <Button
                  size="sm"
                  variant="danger"
                  onClick={() =>
                    setAdding({
                      value: r.prefix,
                      kind: "prefix",
                      reason: "Only sent photos or files, no text",
                      note: "",
                    })
                  }
                >
                  Block this range
                </Button>
              </li>
            ))}
          </ul>
        </Notice>
      )}
      {list.isError ? (
        <ErrorState error={list.error} onRetry={() => void list.refetch()} />
      ) : list.isPending ? (
        <div className="h-40 animate-pulse rounded-xl bg-surface-sunken" />
      ) : items.length === 0 ? (
        <EmptyState
          icon={Ban}
          title="No blocked numbers"
          description="Block a number here, or from the menu of a chat in the inbox."
        />
      ) : (
        <>
          <p className="mb-3 text-[13px] text-muted-foreground">
            {list.data?.active ?? 0} blocked ·{" "}
            {list.data?.blocked_messages ?? 0} messages stopped
          </p>
          <ul className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {items.map((b) => (
              <BlockCard key={b.id} block={b} canManage={canManage} />
            ))}
          </ul>
        </>
      )}
      <AddDialog
        key={adding ? `${adding.kind}-${adding.value}` : "none"}
        initial={adding}
        onClose={() => setAdding(null)}
      />
    </PageShell>
  );
}

function BlockCard({
  block: b,
  canManage,
}: {
  block: Block;
  canManage: boolean;
}) {
  const unblock = useScopedMutation(() => piBlocklistService.unblock(b.id), {
    invalidate: KEY,
    success: "Unblocked. pi answers this number again.",
  });
  const reblock = useScopedMutation(() => piBlocklistService.reblock(b), {
    invalidate: KEY,
    success: "Blocked again",
  });
  return (
    <li>
      <Card>
        <CardBody className="space-y-2">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="font-mono text-[15px] font-semibold break-all">
                {b.kind === "prefix" ? `+${b.value}…` : `+${b.value}`}
              </p>
              <p className="text-xs text-muted-foreground">
                {b.kind === "prefix" ? "Range" : "Number"} ·{" "}
                {SOURCE_LABEL[b.source]} ·{" "}
                <time
                  dateTime={b.created_at}
                  title={formatDateTime(b.created_at)}
                >
                  {relativeTime(b.created_at)}
                </time>
              </p>
            </div>
            <Badge tone={b.active ? "danger" : "neutral"}>
              {b.active ? "Blocked" : "Unblocked"}
            </Badge>
          </div>
          {b.reason && <p className="text-[13px] break-words">{b.reason}</p>}
          {b.note && (
            <p className="text-[13px] break-words text-muted-foreground">
              {b.note}
            </p>
          )}
          <p className="text-xs text-muted-foreground">
            {b.hits
              ? `${b.hits} message${b.hits === 1 ? "" : "s"} stopped${
                  b.last_hit_at ? `, last ${relativeTime(b.last_hit_at)}` : ""
                }`
              : "No messages stopped yet"}
          </p>
          {canManage &&
            (b.active ? (
              <Button
                size="sm"
                variant="secondary"
                loading={unblock.isPending}
                onClick={() => unblock.mutate(undefined)}
              >
                <ShieldCheck /> Unblock
              </Button>
            ) : (
              <Button
                size="sm"
                variant="secondary"
                loading={reblock.isPending}
                onClick={() => reblock.mutate(undefined)}
              >
                <ShieldOff /> Block again
              </Button>
            ))}
        </CardBody>
      </Card>
    </li>
  );
}

function AddDialog({
  initial,
  onClose,
}: {
  initial: BlockInput | null;
  onClose: () => void;
}) {
  const [kind, setKind] = useState<"number" | "prefix">(
    initial?.kind ?? "number",
  );
  const [value, setValue] = useState(initial?.value ?? "");
  const [reason, setReason] = useState(initial?.reason ?? "");
  const [note, setNote] = useState("");
  const digits = value.replace(/\D/g, "");
  const invalid = kind === "prefix" ? digits.length < 6 : digits.length < 7;
  const add = useScopedMutation(
    () => piBlocklistService.add({ value, kind, reason, note }),
    {
      invalidate: KEY,
      success: (r) =>
        r.closed_chats
          ? `Blocked. ${r.closed_chats} open chat${r.closed_chats === 1 ? "" : "s"} closed.`
          : "Blocked",
      onSuccess: onClose,
    },
  );
  return (
    <Dialog
      open={initial !== null}
      onOpenChange={(next) => !next && !add.isPending && onClose()}
    >
      <DialogContent size="md">
        <DialogHeader
          title="Block a number"
          description="pi stops answering it. Its messages are not saved and no AI is used on them."
        />
        <DialogBody className="space-y-3">
          <FormField label="What to block" htmlFor="block-kind">
            <NativeSelect
              id="block-kind"
              value={kind}
              onChange={(e) => setKind(e.target.value as "number" | "prefix")}
            >
              <option value="number">One number</option>
              <option value="prefix">
                A range (numbers that start the same)
              </option>
            </NativeSelect>
          </FormField>
          <FormField
            label={
              kind === "prefix" ? "Start of the numbers" : "WhatsApp number"
            }
            htmlFor="block-value"
            help={
              kind === "prefix"
                ? "Country code and the start of the number, at least 6 digits, e.g. 628956366."
                : "With country code, e.g. +62 895636626854."
            }
          >
            <Input
              id="block-value"
              inputMode="tel"
              autoComplete="off"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder={kind === "prefix" ? "628956366" : "+62 895636626854"}
            />
          </FormField>
          <FormField label="Why" htmlFor="block-reason" optional>
            <Input
              id="block-reason"
              maxLength={200}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. Sends only black images"
            />
          </FormField>
          <FormField label="Note" htmlFor="block-note" optional>
            <Textarea
              id="block-note"
              rows={3}
              maxLength={500}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </FormField>
        </DialogBody>
        <DialogFooter>
          <Button
            variant="secondary"
            onClick={onClose}
            disabled={add.isPending}
          >
            Cancel
          </Button>
          <Button
            variant="danger"
            loading={add.isPending}
            disabled={invalid || add.isPending}
            onClick={() => add.mutate(undefined)}
          >
            Block
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
