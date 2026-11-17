"use client";

import { useQuery } from "@tanstack/react-query";
import { Ban, ShieldCheck, ShieldOff } from "lucide-react";
import * as React from "react";

import {
  Badge,
  Button,
  Card,
  CardSection,
  Dialog,
  DialogContent,
  EmptyState,
  ErrorState,
  Field,
  Input,
  LoadingBlock,
  Notice,
  Select,
  Textarea,
} from "@/components/ui";
import { errorText, del, get, post } from "@/lib/api";
import { count, dateTime, timeAgo } from "@/lib/format";
import { useAction, useBusinessKey, useCan } from "@/lib/session";

interface Block {
  id: string;
  value: string;
  masked: string;
  kind: "number" | "prefix";
  reason: string;
  note: string;
  source: "manual" | "chat" | "bulk";
  active: boolean;
  hits: number;
  last_hit_at: string | null;
  created_at: string;
}

interface BlocklistData {
  items: Block[];
  active: number;
  blocked_messages: number;
}

interface Suggestions {
  ranges: {
    prefix: string;
    chats: number;
    first_seen: string;
    last_seen: string;
  }[];
}

const SOURCE_LABEL: Record<Block["source"], string> = {
  manual: "Added here",
  chat: "From the inbox",
  bulk: "Bulk",
};

function AddDialog({
  initial,
  onClose,
}: {
  initial?: { value: string; kind: "number" | "prefix"; reason: string };
  onClose: () => void;
}) {
  const [value, setValue] = React.useState(initial?.value ?? "");
  const [kind, setKind] = React.useState<"number" | "prefix">(
    initial?.kind ?? "number",
  );
  const [reason, setReason] = React.useState(initial?.reason ?? "");
  const [note, setNote] = React.useState("");
  const run = useAction(
    () =>
      post<{ closed_chats: number }>("/pi/blocklist", {
        value,
        kind,
        reason,
        note,
        close_chats: true,
      }),
    {
      invalidate: [["blocklist"], ["blocklist-suggestions"], ["conversations"]],
      success: (r) =>
        r.closed_chats
          ? `Blocked. ${count(r.closed_chats)} open chat${r.closed_chats === 1 ? "" : "s"} closed.`
          : "Blocked",
      onSuccess: onClose,
    },
  );
  const digits = value.replace(/\D/g, "");
  const invalid = kind === "prefix" ? digits.length < 6 : digits.length < 7;
  return (
    <DialogContent
      title="Block a number"
      description="pi stops answering it. Its messages are not saved and no AI is used on them."
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (!invalid) run.mutate(undefined);
        }}
      >
        <Field label="What to block" htmlFor="block-kind">
          <Select
            id="block-kind"
            className="text-base sm:text-[15px]"
            value={kind}
            onChange={(e) => setKind(e.target.value as "number" | "prefix")}
          >
            <option value="number">One number</option>
            <option value="prefix">
              A range (numbers that start the same)
            </option>
          </Select>
        </Field>
        <Field
          label={kind === "prefix" ? "Start of the numbers" : "WhatsApp number"}
          htmlFor="block-value"
          hint={
            kind === "prefix"
              ? "Country code and the start of the number, at least 6 digits, e.g. 628956366."
              : "With country code, e.g. +62 895636626854."
          }
        >
          <Input
            id="block-value"
            inputMode="tel"
            autoComplete="off"
            className="text-base sm:text-[15px]"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={kind === "prefix" ? "628956366" : "+62 895636626854"}
          />
        </Field>
        <Field label="Why" htmlFor="block-reason" optional>
          <Input
            id="block-reason"
            className="text-base sm:text-[15px]"
            maxLength={200}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="e.g. Sends only black images"
          />
        </Field>
        <Field label="Note" htmlFor="block-note" optional>
          <Textarea
            id="block-note"
            className="text-base sm:text-[15px]"
            maxLength={500}
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </Field>
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="submit"
            variant="danger"
            loading={run.isPending}
            disabled={invalid}
          >
            Block
          </Button>
        </div>
      </form>
    </DialogContent>
  );
}

function Row({ block, canManage }: { block: Block; canManage: boolean }) {
  const unblock = useAction(() => del(`/pi/blocklist/${block.id}`), {
    invalidate: [["blocklist"], ["blocklist-suggestions"]],
    success: "Unblocked. pi answers this number again.",
  });
  const reblock = useAction(
    () => post("/pi/blocklist", { value: block.value, kind: block.kind }),
    {
      invalidate: [["blocklist"], ["conversations"]],
      success: "Blocked again",
    },
  );
  return (
    <li>
      <Card className="min-w-0">
        <CardSection className="space-y-2 p-4">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="break-all font-mono text-[15px] font-semibold">
                {block.kind === "prefix"
                  ? `+${block.value}…`
                  : `+${block.value}`}
              </p>
              <p className="text-[13px] text-muted-foreground">
                {block.kind === "prefix" ? "Range" : "Number"} ·{" "}
                {SOURCE_LABEL[block.source]} ·{" "}
                <time
                  dateTime={block.created_at}
                  title={dateTime(block.created_at)}
                >
                  {timeAgo(block.created_at)}
                </time>
              </p>
            </div>
            <Badge tone={block.active ? "danger" : "neutral"}>
              {block.active ? "Blocked" : "Unblocked"}
            </Badge>
          </div>
          {block.reason ? (
            <p className="break-words text-sm">{block.reason}</p>
          ) : null}
          {block.note ? (
            <p className="break-words text-sm text-foreground-secondary">
              {block.note}
            </p>
          ) : null}
          <p className="text-[13px] text-muted-foreground">
            {block.hits
              ? `${count(block.hits)} message${block.hits === 1 ? "" : "s"} stopped${
                  block.last_hit_at
                    ? `, last ${timeAgo(block.last_hit_at)}`
                    : ""
                }`
              : "No messages stopped yet"}
          </p>
          {canManage ? (
            block.active ? (
              <Button
                size="sm"
                variant="secondary"
                className="min-h-11"
                loading={unblock.isPending}
                onClick={() => unblock.mutate(undefined)}
              >
                <ShieldCheck className="size-4" aria-hidden /> Unblock
              </Button>
            ) : (
              <Button
                size="sm"
                variant="secondary"
                className="min-h-11"
                loading={reblock.isPending}
                onClick={() => reblock.mutate(undefined)}
              >
                <ShieldOff className="size-4" aria-hidden /> Block again
              </Button>
            )
          ) : null}
        </CardSection>
      </Card>
    </li>
  );
}

export function Blocklist() {
  const can = useCan();
  const key = useBusinessKey();
  const canView = can("pi.read");
  const canManage = can("pi.settings.manage");
  const [adding, setAdding] = React.useState<{
    value: string;
    kind: "number" | "prefix";
    reason: string;
  } | null>(null);
  const list = useQuery({
    queryKey: key(["blocklist"]),
    queryFn: () => get<BlocklistData>("/pi/blocklist"),
    enabled: canView,
    refetchInterval: 60_000,
  });
  const suggestions = useQuery({
    queryKey: key(["blocklist-suggestions"]),
    queryFn: () => get<Suggestions>("/pi/blocklist/suggestions"),
    enabled: canView && canManage,
    staleTime: 60_000,
  });
  const ranges = suggestions.data?.ranges ?? [];

  return (
    <div className="min-w-0 space-y-4">
      {canManage ? (
        <div>
          <Button
            variant="danger"
            onClick={() => setAdding({ value: "", kind: "number", reason: "" })}
          >
            <Ban className="size-4" aria-hidden /> Block a number
          </Button>
        </div>
      ) : null}
      {!canView ? (
        <Notice tone="warning" title="No access">
          Ask your business owner for access.
        </Notice>
      ) : (
        <>
          {canManage && ranges.length ? (
            <Notice tone="warning" title="Possible flood">
              <ul className="mt-2 space-y-2">
                {ranges.map((r) => (
                  <li
                    key={r.prefix}
                    className="flex flex-wrap items-center justify-between gap-2"
                  >
                    <span className="min-w-0 text-sm">
                      {count(r.chats)} open chats from +{r.prefix}… only ever
                      sent photos or files, no text (first{" "}
                      {timeAgo(r.first_seen)}, last {timeAgo(r.last_seen)}).
                    </span>
                    <Button
                      size="sm"
                      variant="danger"
                      onClick={() =>
                        setAdding({
                          value: r.prefix,
                          kind: "prefix",
                          reason: "Only sent photos or files, no text",
                        })
                      }
                    >
                      Block this range
                    </Button>
                  </li>
                ))}
              </ul>
            </Notice>
          ) : null}
          {list.isLoading ? (
            <LoadingBlock rows={4} label="Loading the blocklist" />
          ) : list.isError ? (
            <ErrorState
              message={errorText(list.error)}
              onRetry={() => void list.refetch()}
            />
          ) : (list.data?.items.length ?? 0) === 0 ? (
            <Card>
              <EmptyState
                icon={<Ban className="size-5" aria-hidden />}
                title="No blocked numbers"
              >
                Block a number here, or from the menu of a chat in the inbox.
              </EmptyState>
            </Card>
          ) : (
            <>
              <p className="mb-3 text-sm text-foreground-secondary">
                {count(list.data?.active ?? 0)} blocked ·{" "}
                {count(list.data?.blocked_messages ?? 0)} messages stopped
              </p>
              <ul className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                {list.data?.items.map((b) => (
                  <Row key={b.id} block={b} canManage={canManage} />
                ))}
              </ul>
            </>
          )}
        </>
      )}
      <Dialog
        open={adding !== null}
        onOpenChange={(open) => {
          if (!open) setAdding(null);
        }}
      >
        {adding ? (
          <AddDialog
            key={`${adding.kind}-${adding.value}`}
            initial={adding}
            onClose={() => setAdding(null)}
          />
        ) : null}
      </Dialog>
    </div>
  );
}
