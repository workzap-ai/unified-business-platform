"use client";

import { useState } from "react";
import { Phone, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/controls";
import { Badge } from "@/components/ui/display";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/overlays";
import { ConfirmDialog, FormField } from "@/components/app/forms";
import { ErrorState, InlineError } from "@/components/app/states";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { errorMessage } from "@/services/api-client";
import {
  NORI_ITEM_KINDS,
  PRIORITIES,
  TEAM_BOARD_KEY,
  teamBoardService,
  type NoriItemKind,
  type NoriNumber,
  type Priority,
} from "../team-board-service";

export const NORI_ITEM_LABEL: Record<NoriItemKind, string> = {
  feature: "Feature",
  problem: "Problem",
  feedback: "Feedback",
  module: "Module idea",
  question: "Question",
  change: "Change",
  note: "Note",
};

const NUMBERS_KEY = [...TEAM_BOARD_KEY, "nori-numbers"];

/** Numbers pi recognises as nori users, with the nori workspace each belongs to. */
export function NoriNumbersPanel({ manage }: { manage: boolean }) {
  const query = useScopedQuery(NUMBERS_KEY, () =>
    teamBoardService.noriNumbers(),
  );
  const [phone, setPhone] = useState("");
  const [workspace, setWorkspace] = useState("");
  const [person, setPerson] = useState("");
  const [department, setDepartment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [removing, setRemoving] = useState<NoriNumber | null>(null);
  const add = useScopedMutation(teamBoardService.addNoriNumber, {
    invalidate: [NUMBERS_KEY],
    success: "Nori number added",
    toastErrors: false,
  });
  const update = useScopedMutation(teamBoardService.updateNoriNumber, {
    invalidate: [NUMBERS_KEY],
    error: "That number couldn't be changed. Please try again.",
  });
  const remove = useScopedMutation(teamBoardService.deleteNoriNumber, {
    invalidate: [NUMBERS_KEY],
    success: "Nori number removed",
    onSuccess: () => setRemoving(null),
  });
  const numbers = query.data?.numbers ?? [];
  return (
    <section
      aria-label="Nori numbers"
      className="rounded-lg border border-border bg-surface p-3"
    >
      <header className="mb-2 flex items-center gap-1.5">
        <Phone className="size-4 text-muted-foreground" aria-hidden="true" />
        <h2 className="text-[13px] font-semibold">Nori numbers</h2>
        <span className="text-xs text-muted-foreground tabular-nums">
          {numbers.length}
        </span>
      </header>
      <p className="mb-3 text-xs text-muted-foreground">
        pi treats a message from one of these numbers as coming from that nori
        workspace and files it on this board.
      </p>
      {manage && (
        <form
          noValidate
          aria-label="Add a nori number"
          className="mb-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-[1.2fr_1.2fr_1fr_1fr_auto]"
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
              await add.mutateAsync({
                phone: phone.trim(),
                workspace: workspace.trim(),
                person: person.trim() || undefined,
                department: department.trim() || undefined,
              });
              setPhone("");
              setWorkspace("");
              setPerson("");
              setDepartment("");
            } catch (err) {
              setError(errorMessage(err, "The number could not be added."));
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
          <Button type="submit" loading={add.isPending}>
            <Plus aria-hidden="true" /> Add number
          </Button>
          {error && (
            <div className="sm:col-span-2 xl:col-span-5">
              <InlineError message={error} />
            </div>
          )}
        </form>
      )}
      {query.isError && !query.data ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : !query.data ? (
        <p className="text-xs text-muted-foreground">Loading numbers…</p>
      ) : numbers.length === 0 ? (
        <p className="rounded-md border border-dashed border-border px-3 py-4 text-center text-xs text-muted-foreground">
          No nori numbers yet. Add one so pi knows who is writing.
        </p>
      ) : (
        <ul className="divide-y divide-border rounded-md border border-border">
          {numbers.map((n) => (
            <li key={n.id} className="flex flex-wrap items-center gap-2 p-2.5">
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium tabular-nums">
                  {n.phone}
                </span>
                <span className="block truncate text-xs text-muted-foreground">
                  {[n.workspace, n.person, n.department]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
              </span>
              {n.source === "nori" && <Badge tone="pi">From nori</Badge>}
              <Switch
                checked={n.active}
                disabled={!manage || update.isPending}
                aria-label={`${n.active ? "Turn off" : "Turn on"} ${n.phone}`}
                onCheckedChange={(active) =>
                  update.mutate({ id: n.id, active })
                }
              />
              {manage && (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-xs"
                  aria-label={`Delete ${n.phone}`}
                  onClick={() => setRemoving(n)}
                >
                  <Trash2 />
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      <ConfirmDialog
        open={removing !== null}
        onOpenChange={(open) => !open && !remove.isPending && setRemoving(null)}
        title="Delete this nori number?"
        description={
          removing
            ? `${removing.phone} (${removing.workspace}) will no longer be recognised as a nori user. Messages already filed stay on the board.`
            : undefined
        }
        confirmLabel="Delete"
        destructive
        loading={remove.isPending}
        onConfirm={() => removing && remove.mutate(removing.id)}
      />
    </section>
  );
}

/** A requirement the team adds by hand to the Nori Platform board. */
export function NewRequirementDialog({ onClose }: { onClose: () => void }) {
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [kind, setKind] = useState<NoriItemKind>("feature");
  const [priority, setPriority] = useState<Priority>("normal");
  const [workspace, setWorkspace] = useState("");
  const [person, setPerson] = useState("");
  const [department, setDepartment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const create = useScopedMutation(teamBoardService.addNoriItem, {
    invalidate: [TEAM_BOARD_KEY],
    success: "Requirement added to the Nori Platform board",
    toastErrors: false,
  });
  return (
    <Dialog
      open
      onOpenChange={(next) => !next && !create.isPending && onClose()}
    >
      <DialogContent size="sm">
        <DialogHeader
          title="Add requirement"
          description="Something nori needs: a feature, a problem, feedback or a module idea."
        />
        <form
          noValidate
          className="flex min-h-0 flex-1 flex-col"
          onSubmit={async (e) => {
            e.preventDefault();
            if (!title.trim()) {
              setError("Give the requirement a title");
              return;
            }
            setError(null);
            try {
              await create.mutateAsync({
                title: title.trim(),
                text: text.trim() || undefined,
                kind,
                priority,
                workspace: workspace.trim() || undefined,
                person: person.trim() || undefined,
                department: department.trim() || undefined,
              });
              onClose();
            } catch (err) {
              setError(
                errorMessage(err, "The requirement could not be added."),
              );
            }
          }}
        >
          <DialogBody className="space-y-4">
            <FormField label="Title" htmlFor="nori-title" required>
              <Input
                id="nori-title"
                autoComplete="off"
                maxLength={200}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </FormField>
            <FormField label="Details" htmlFor="nori-text" optional>
              <Textarea
                id="nori-text"
                rows={3}
                maxLength={2000}
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
            </FormField>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField label="Type" htmlFor="nori-kind">
                <NativeSelect
                  id="nori-kind"
                  value={kind}
                  onChange={(e) => setKind(e.target.value as NoriItemKind)}
                >
                  {NORI_ITEM_KINDS.map((k) => (
                    <option key={k} value={k}>
                      {NORI_ITEM_LABEL[k]}
                    </option>
                  ))}
                </NativeSelect>
              </FormField>
              <FormField label="Priority" htmlFor="nori-priority">
                <NativeSelect
                  id="nori-priority"
                  value={priority}
                  onChange={(e) => setPriority(e.target.value as Priority)}
                >
                  {PRIORITIES.map((p) => (
                    <option key={p} value={p}>
                      {p[0]!.toUpperCase() + p.slice(1)}
                    </option>
                  ))}
                </NativeSelect>
              </FormField>
            </div>
            <FormField label="Nori workspace" htmlFor="nori-workspace" optional>
              <Input
                id="nori-workspace"
                autoComplete="off"
                maxLength={120}
                value={workspace}
                onChange={(e) => setWorkspace(e.target.value)}
              />
            </FormField>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField label="Person" htmlFor="nori-person" optional>
                <Input
                  id="nori-person"
                  autoComplete="off"
                  maxLength={120}
                  value={person}
                  onChange={(e) => setPerson(e.target.value)}
                />
              </FormField>
              <FormField label="Department" htmlFor="nori-department" optional>
                <Input
                  id="nori-department"
                  autoComplete="off"
                  maxLength={80}
                  value={department}
                  onChange={(e) => setDepartment(e.target.value)}
                />
              </FormField>
            </div>
            {error && <InlineError message={error} />}
          </DialogBody>
          <DialogFooter>
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
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
