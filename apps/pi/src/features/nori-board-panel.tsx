"use client";

/**
 * Nori Platform board parts: the numbers pi recognises as nori users and the form for a
 * requirement added by hand. The cards themselves are the team board filtered to kind
 * "nori" (team-board.tsx). API: /pi/nori-board (reading pi.work.read, changing
 * pi.work.manage).
 */
import { useQuery } from "@tanstack/react-query";
import { Phone, Plus, Trash2 } from "lucide-react";
import * as React from "react";

import {
  Badge,
  Button,
  Dialog,
  DialogContent,
  ErrorState,
  Field,
  Input,
  Select,
  Skeleton,
  Switch,
  Textarea,
} from "@/components/ui";
import { del, errorText, get, patch, post } from "@/lib/api";
import { useAction, useBusinessKey } from "@/lib/session";

export type NoriItemKind =
  | "feature"
  | "problem"
  | "feedback"
  | "module"
  | "question"
  | "change"
  | "note";

export const NORI_ITEM_KINDS: NoriItemKind[] = [
  "feature",
  "problem",
  "feedback",
  "module",
  "question",
  "change",
  "note",
];

export const NORI_ITEM_LABEL: Record<NoriItemKind, string> = {
  feature: "Feature",
  problem: "Problem",
  feedback: "Feedback",
  module: "Module idea",
  question: "Question",
  change: "Change",
  note: "Note",
};

/** What a nori card knows about who wrote it (null on other kinds of card). */
export interface NoriInfo {
  item_kind: NoriItemKind;
  workspace: string;
  person: string;
  department: string;
  phone_mask: string;
  source: "nori" | "whatsapp" | "manual";
  url: string | null;
}

export interface NoriNumber {
  id: string;
  /** Full digits only for people who can manage the board, otherwise masked. */
  phone: string;
  workspace: string;
  person: string;
  department: string;
  active: boolean;
  source: "manual" | "nori";
  created_at: string;
}

type Priority = "low" | "normal" | "high" | "urgent";

const NUMBERS_KEY = ["team-board", "nori-numbers"];

/** Numbers pi recognises as nori users, with the nori workspace each belongs to. */
export function NoriNumbersPanel({ manage }: { manage: boolean }) {
  const key = useBusinessKey();
  const query = useQuery({
    queryKey: key(NUMBERS_KEY),
    queryFn: () => get<{ numbers: NoriNumber[] }>("/pi/nori-board/numbers"),
  });
  const [phone, setPhone] = React.useState("");
  const [workspace, setWorkspace] = React.useState("");
  const [person, setPerson] = React.useState("");
  const [department, setDepartment] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [removing, setRemoving] = React.useState<NoriNumber | null>(null);
  const add = useAction(
    () =>
      post<NoriNumber>("/pi/nori-board/numbers", {
        phone: phone.trim(),
        workspace: workspace.trim(),
        person: person.trim() || undefined,
        department: department.trim() || undefined,
      }),
    {
      invalidate: [NUMBERS_KEY],
      success: "Nori number added",
      silentError: true,
      onSuccess: () => {
        setPhone("");
        setWorkspace("");
        setPerson("");
        setDepartment("");
      },
    },
  );
  const update = useAction(
    ({ id, active }: { id: string; active: boolean }) =>
      patch<NoriNumber>(`/pi/nori-board/numbers/${id}`, { active }),
    { invalidate: [NUMBERS_KEY] },
  );
  const remove = useAction(
    (id: string) => del<void>(`/pi/nori-board/numbers/${id}`),
    {
      invalidate: [NUMBERS_KEY],
      success: "Nori number removed",
      onSuccess: () => setRemoving(null),
    },
  );
  const numbers = query.data?.numbers ?? [];
  return (
    <section
      aria-label="Nori numbers"
      className="rounded-2xl border border-border bg-surface p-3"
    >
      <header className="mb-2 flex items-center gap-1.5">
        <Phone className="size-4 text-muted-foreground" aria-hidden />
        <h2 className="text-sm font-semibold">Nori numbers</h2>
        <span className="text-xs text-muted-foreground tabular-nums">
          {numbers.length}
        </span>
      </header>
      <p className="mb-3 text-[13px] text-muted-foreground">
        pi treats a message from one of these numbers as coming from that nori
        workspace and files it on this board.
      </p>
      {manage ? (
        <form
          noValidate
          aria-label="Add a nori number"
          className="mb-3 grid gap-2 sm:grid-cols-2"
          onSubmit={async (e) => {
            e.preventDefault();
            if (!phone.trim() || !workspace.trim()) {
              setError(
                "Add a phone number and the nori workspace it belongs to",
              );
              return;
            }
            setError(null);
            try {
              await add.mutateAsync(undefined);
            } catch (err) {
              setError(errorText(err));
            }
          }}
        >
          <Input
            aria-label="Phone number with country code"
            inputMode="tel"
            autoComplete="off"
            placeholder="+92 300 1234567"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
          />
          <Input
            aria-label="Nori workspace"
            autoComplete="off"
            maxLength={120}
            placeholder="Workspace"
            value={workspace}
            onChange={(e) => setWorkspace(e.target.value)}
          />
          <Input
            aria-label="Person"
            autoComplete="off"
            maxLength={120}
            placeholder="Person (optional)"
            value={person}
            onChange={(e) => setPerson(e.target.value)}
          />
          <Input
            aria-label="Department"
            autoComplete="off"
            maxLength={80}
            placeholder="Department (optional)"
            value={department}
            onChange={(e) => setDepartment(e.target.value)}
          />
          {error ? (
            <p className="text-[13px] text-danger sm:col-span-2" role="alert">
              {error}
            </p>
          ) : null}
          <div className="sm:col-span-2">
            <Button type="submit" loading={add.isPending}>
              <Plus className="size-4" aria-hidden /> Add number
            </Button>
          </div>
        </form>
      ) : null}
      {query.isError && !query.data ? (
        <ErrorState
          message={errorText(query.error)}
          onRetry={() => query.refetch()}
        />
      ) : !query.data ? (
        <Skeleton className="h-16 w-full" />
      ) : numbers.length === 0 ? (
        <p className="rounded-xl border border-dashed border-border px-3 py-5 text-center text-sm text-muted-foreground">
          No nori numbers yet. Add one so pi knows who is writing.
        </p>
      ) : (
        <ul className="divide-y divide-border rounded-xl border border-border">
          {numbers.map((n) => (
            <li key={n.id} className="flex flex-wrap items-center gap-2 p-3">
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium tabular-nums">
                  {n.phone}
                </span>
                <span className="block truncate text-[13px] text-muted-foreground">
                  {[n.workspace, n.person, n.department]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
              </span>
              {n.source === "nori" ? (
                <Badge tone="accent">From nori</Badge>
              ) : null}
              <Switch
                id={`nori-number-${n.id}`}
                label={`${n.active ? "Turn off" : "Turn on"} ${n.phone}`}
                checked={n.active}
                disabled={!manage || update.isPending}
                onCheckedChange={(active) =>
                  update.mutate({ id: n.id, active })
                }
              />
              {manage ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  aria-label={`Delete ${n.phone}`}
                  onClick={() => setRemoving(n)}
                >
                  <Trash2 className="size-4" aria-hidden />
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {removing ? (
        <Dialog
          open
          onOpenChange={(next) =>
            !next && !remove.isPending && setRemoving(null)
          }
        >
          <DialogContent
            title="Delete this nori number?"
            description={`${removing.phone} (${removing.workspace}) will no longer be recognised as a nori user. Messages already filed stay on the board.`}
          >
            <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <Button
                type="button"
                variant="secondary"
                onClick={() => setRemoving(null)}
                disabled={remove.isPending}
              >
                Cancel
              </Button>
              <Button
                type="button"
                variant="danger"
                loading={remove.isPending}
                onClick={() => remove.mutate(removing.id)}
              >
                Delete
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      ) : null}
    </section>
  );
}

/** A requirement the team adds by hand to the Nori Platform board. */
export function NewRequirementDialog({ onClose }: { onClose: () => void }) {
  const [title, setTitle] = React.useState("");
  const [text, setText] = React.useState("");
  const [kind, setKind] = React.useState<NoriItemKind>("feature");
  const [priority, setPriority] = React.useState<Priority>("normal");
  const [workspace, setWorkspace] = React.useState("");
  const [person, setPerson] = React.useState("");
  const [department, setDepartment] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const create = useAction(
    () =>
      post("/pi/nori-board/items", {
        title: title.trim(),
        text: text.trim() || undefined,
        kind,
        priority,
        workspace: workspace.trim() || undefined,
        person: person.trim() || undefined,
        department: department.trim() || undefined,
      }),
    {
      invalidate: [["team-board"]],
      success: "Requirement added to the Nori Platform board",
      silentError: true,
      onSuccess: onClose,
    },
  );
  return (
    <Dialog
      open
      onOpenChange={(next) => !next && !create.isPending && onClose()}
    >
      <DialogContent
        title="Add requirement"
        description="Something nori needs: a feature, a problem, feedback or a module idea."
      >
        <form
          noValidate
          className="space-y-4"
          onSubmit={async (e) => {
            e.preventDefault();
            if (!title.trim()) {
              setError("Give the requirement a title");
              return;
            }
            setError(null);
            try {
              await create.mutateAsync(undefined);
            } catch (err) {
              setError(errorText(err));
            }
          }}
        >
          <Field label="Title" htmlFor="nori-title" error={error}>
            <Input
              id="nori-title"
              autoComplete="off"
              maxLength={200}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </Field>
          <Field label="Details" htmlFor="nori-text" optional>
            <Textarea
              id="nori-text"
              rows={3}
              maxLength={2000}
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Type" htmlFor="nori-kind">
              <Select
                id="nori-kind"
                value={kind}
                onChange={(e) => setKind(e.target.value as NoriItemKind)}
              >
                {NORI_ITEM_KINDS.map((k) => (
                  <option key={k} value={k}>
                    {NORI_ITEM_LABEL[k]}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Priority" htmlFor="nori-priority">
              <Select
                id="nori-priority"
                value={priority}
                onChange={(e) => setPriority(e.target.value as Priority)}
              >
                <option value="low">Low</option>
                <option value="normal">Normal</option>
                <option value="high">High</option>
                <option value="urgent">Urgent</option>
              </Select>
            </Field>
          </div>
          <Field label="Nori workspace" htmlFor="nori-workspace" optional>
            <Input
              id="nori-workspace"
              autoComplete="off"
              maxLength={120}
              value={workspace}
              onChange={(e) => setWorkspace(e.target.value)}
            />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Person" htmlFor="nori-person" optional>
              <Input
                id="nori-person"
                autoComplete="off"
                maxLength={120}
                value={person}
                onChange={(e) => setPerson(e.target.value)}
              />
            </Field>
            <Field label="Department" htmlFor="nori-department" optional>
              <Input
                id="nori-department"
                autoComplete="off"
                maxLength={80}
                value={department}
                onChange={(e) => setDepartment(e.target.value)}
              />
            </Field>
          </div>
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button
              type="button"
              variant="secondary"
              onClick={onClose}
              disabled={create.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" loading={create.isPending}>
              Add requirement
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
