"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Copy, Plus, ShieldCheck, UserPlus } from "lucide-react";
import { toast } from "sonner";
import { EmptyState, ErrorState, Notice } from "@/components/app/states";
import { Button } from "@/components/ui/button";
import { Badge, Card } from "@/components/ui/display";
import { Input, NativeSelect } from "@/components/ui/input";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/overlays";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { WorkspaceWhatsAppDialog } from "./numbers-page";
import {
  Loading,
  OperatorShell,
  ReasonDialog,
  StateBadge,
} from "./operator-pages";
import {
  operatorService as api,
  type OperatorMe,
  type WorkspaceMember,
  type WorkspaceMembers,
} from "./service";

const date = (value: string | null | undefined) =>
  value
    ? new Date(value).toLocaleDateString(undefined, {
        day: "numeric",
        month: "short",
        year: "numeric",
      })
    : "—";

const BUSINESS_TYPES = [
  ["service_business", "Services"],
  ["product_business", "Products"],
  ["hybrid_business", "Products and services"],
] as const;

/** Shown once after inviting someone new, in case the email doesn't arrive. */
function InviteLink({ link }: { link: string }) {
  return (
    <Notice tone="success" title="Invitation sent">
      <p>
        We emailed a link to set a password. You can also share it yourself
        (valid for 7 days):
      </p>
      <div className="mt-2 flex min-w-0 items-center gap-2">
        <code className="min-w-0 flex-1 truncate rounded bg-surface-muted px-2 py-1 text-[12px]">
          {link}
        </code>
        <Button
          size="xs"
          variant="secondary"
          onClick={() =>
            void navigator.clipboard
              .writeText(link)
              .then(() => toast.success("Link copied"))
          }
        >
          <Copy aria-hidden /> Copy
        </Button>
      </div>
    </Notice>
  );
}

/** Super admins and admins set up a workspace for someone; that person becomes its owner. */
export function NewWorkspaceDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const router = useRouter();
  const [name, setName] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [ownerName, setOwnerName] = React.useState("");
  const [type, setType] = React.useState<string>("service_business");
  const [invite, setInvite] = React.useState<{
    id: string;
    link: string;
  } | null>(null);
  const create = useScopedMutation(
    () =>
      api.createWorkspace({
        name: name.trim(),
        owner_email: email.trim(),
        owner_name: ownerName.trim(),
        business_type: type,
      }),
    {
      invalidate: [["operator"]],
      success: "Workspace created",
      onSuccess: (result) => {
        if (result.invite_link)
          setInvite({ id: result.id, link: result.invite_link });
        else {
          close(false);
          router.push(`/operator/workspaces/${result.id}`);
        }
      },
    },
  );
  function close(next: boolean) {
    if (!next) {
      setName("");
      setEmail("");
      setOwnerName("");
      setInvite(null);
    }
    onOpenChange(next);
  }
  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent>
        <DialogHeader
          title="New workspace"
          description="Set up an Owner OS workspace for someone. They become its owner."
        />
        <DialogBody className="space-y-3">
          {invite ? (
            <InviteLink link={invite.link} />
          ) : (
            <>
              <Field label="Workspace name" id="ws-name">
                <Input
                  id="ws-name"
                  value={name}
                  maxLength={120}
                  placeholder="Crescent Traders"
                  onChange={(e) => setName(e.target.value)}
                />
              </Field>
              <Field label="Owner's email" id="ws-email">
                <Input
                  id="ws-email"
                  type="email"
                  value={email}
                  placeholder="owner@company.com"
                  onChange={(e) => setEmail(e.target.value)}
                />
              </Field>
              <Field label="Owner's name (if they are new)" id="ws-owner">
                <Input
                  id="ws-owner"
                  value={ownerName}
                  maxLength={160}
                  onChange={(e) => setOwnerName(e.target.value)}
                />
              </Field>
              <Field label="What the business sells" id="ws-type">
                <NativeSelect
                  id="ws-type"
                  value={type}
                  onChange={(e) => setType(e.target.value)}
                >
                  {BUSINESS_TYPES.map(([key, text]) => (
                    <option key={key} value={key}>
                      {text}
                    </option>
                  ))}
                </NativeSelect>
              </Field>
              <p className="text-[12px] text-muted-foreground">
                Someone without an account gets an email to set a password.
              </p>
            </>
          )}
        </DialogBody>
        <DialogFooter>
          {invite ? (
            <Button
              onClick={() => {
                const id = invite.id;
                close(false);
                router.push(`/operator/workspaces/${id}`);
              }}
            >
              Open workspace
            </Button>
          ) : (
            <>
              <Button variant="ghost" onClick={() => close(false)}>
                Cancel
              </Button>
              <Button
                disabled={name.trim().length < 2 || !email.includes("@")}
                loading={create.isPending}
                onClick={() => create.mutate(undefined)}
              >
                <Plus aria-hidden /> Create workspace
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Field({
  label,
  id,
  children,
}: {
  label: string;
  id: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="text-[13px] font-medium">
        {label}
      </label>
      {children}
    </div>
  );
}

export function OperatorWorkspaceDetailPage({ id }: { id: string }) {
  return (
    <OperatorShell
      title="Workspace"
      description="Who belongs to this workspace and what they can do. No business records or customer content."
    >
      {(me) => <WorkspaceAdmin id={id} me={me} />}
    </OperatorShell>
  );
}

function WorkspaceAdmin({ id, me }: { id: string; me: OperatorMe }) {
  const detail = useScopedQuery(["operator", "workspace", id], () =>
    api.workspace(id),
  );
  const members = useScopedQuery(["operator", "workspace", id, "members"], () =>
    api.workspaceMembers(id),
  );
  const [suspending, setSuspending] = React.useState(false);
  const [whatsapp, setWhatsapp] = React.useState(false);
  const canManage = me.capabilities.includes("operator.workspaces.manage");
  const status = useScopedMutation(
    ({ next, reason }: { next: "active" | "inactive"; reason: string }) =>
      api.workspaceStatus(id, next, reason),
    {
      invalidate: [["operator"]],
      success: "Workspace updated",
      onSuccess: () => setSuspending(false),
    },
  );

  if (detail.isPending) return <Loading />;
  if (detail.isError)
    return <ErrorState error={detail.error} onRetry={() => detail.refetch()} />;
  const w = detail.data;
  const yours = members.data?.members.some(
    (m) => m.is_you && m.status === "active",
  );
  return (
    <div className="space-y-4">
      <Link
        href="/operator/workspaces"
        className="inline-flex items-center gap-1 text-[13px] text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden /> All workspaces
      </Link>
      <Card className="p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
          <div className="min-w-0 flex-1">
            <h2 className="truncate text-lg font-semibold">{w.name}</h2>
            <p className="text-[13px] text-muted-foreground">
              {w.slug} · since {date(w.created_at)} · {w.members} active member
              {w.members === 1 ? "" : "s"}
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <StateBadge value={w.status} />
              <Badge tone={w.pi_business ? "pi" : "outline"}>
                {w.pi_business ? "Pi business" : "Owner OS"}
              </Badge>
              {w.environments.map((e) => (
                <Badge key={e.key} tone="outline">
                  {e.name}
                </Badge>
              ))}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {w.pi_business ? (
              <Button size="sm" variant="secondary" asChild>
                <Link href={`/operator/businesses/${w.id}`}>Pi business</Link>
              </Button>
            ) : null}
            <Button
              size="sm"
              variant="secondary"
              onClick={() => setWhatsapp(true)}
            >
              WhatsApp
            </Button>
            {canManage && !yours ? (
              <Button
                size="sm"
                variant={w.status === "active" ? "danger-outline" : "secondary"}
                onClick={() => setSuspending(true)}
              >
                {w.status === "active" ? "Suspend" : "Reactivate"}
              </Button>
            ) : null}
          </div>
        </div>
      </Card>

      {members.isPending ? (
        <Loading />
      ) : members.isError ? (
        <ErrorState
          error={members.error}
          onRetry={() => void members.refetch()}
        />
      ) : (
        <Members id={id} data={members.data} />
      )}

      <ReasonDialog
        open={suspending}
        onOpenChange={setSuspending}
        title={
          w.status === "active" ? `Suspend ${w.name}?` : `Reactivate ${w.name}?`
        }
        description={
          w.status === "active"
            ? "Members lose access and Pi stops sending. Data is kept."
            : "Members regain access. Pi stays paused until resumed."
        }
        confirm={w.status === "active" ? "Suspend" : "Reactivate"}
        tone={w.status === "active" ? "danger" : "default"}
        loading={status.isPending}
        onConfirm={(reason) =>
          status.mutate({
            next: w.status === "active" ? "inactive" : "active",
            reason,
          })
        }
      />
      <WorkspaceWhatsAppDialog
        tenant={whatsapp ? { id: w.id, name: w.name } : null}
        onOpenChange={(open) => !open && setWhatsapp(false)}
      />
    </div>
  );
}

function Members({ id, data }: { id: string; data: WorkspaceMembers }) {
  const [email, setEmail] = React.useState("");
  const [name, setName] = React.useState("");
  const [role, setRole] = React.useState("member");
  const [invite, setInvite] = React.useState<string | null>(null);
  const [removing, setRemoving] = React.useState<WorkspaceMember | null>(null);
  const roleName = (key: string) =>
    data.roles.find((r) => r.key === key)?.name ?? key;
  // Admins can't hand out or take away ownership; only a super admin can.
  const choices = data.roles.filter(
    (r) => r.key !== "owner" || data.can_manage_owners,
  );
  const invalidate = [["operator", "workspace", id]];
  const add = useScopedMutation(
    () =>
      api.addWorkspaceMember(id, {
        email: email.trim(),
        display_name: name.trim(),
        role,
      }),
    {
      invalidate,
      success: "Member added",
      onSuccess: (result) => {
        setEmail("");
        setName("");
        setInvite(result.invite_link);
      },
    },
  );
  const change = useScopedMutation(
    ({ membership, next }: { membership: string; next: string }) =>
      api.workspaceMemberRole(id, membership, next),
    { invalidate, success: "Role changed" },
  );
  const remove = useScopedMutation(
    (membership: string) => api.removeWorkspaceMember(id, membership),
    { invalidate, success: "Removed", onSuccess: () => setRemoving(null) },
  );
  const active = data.members.filter((m) => m.status === "active");
  const former = data.members.filter((m) => m.status !== "active");

  return (
    <div className="space-y-4">
      {data.can_manage ? (
        <Card className="p-4">
          <h3 className="mb-1 font-semibold">Add a member</h3>
          <p className="mb-3 text-[13px] text-muted-foreground">
            Someone new gets an email to set a password. Someone with an account
            just sees this workspace next time they sign in.
          </p>
          <div className="grid grid-cols-1 gap-2 md:grid-cols-[1fr_1fr_13rem_auto]">
            <Input
              aria-label="Email"
              type="email"
              placeholder="name@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <Input
              aria-label="Name"
              placeholder="Name (if they are new)"
              value={name}
              maxLength={160}
              onChange={(e) => setName(e.target.value)}
            />
            <NativeSelect
              aria-label="Role"
              value={role}
              onChange={(e) => setRole(e.target.value)}
            >
              {choices.map((r) => (
                <option key={r.key} value={r.key}>
                  {r.name}
                </option>
              ))}
            </NativeSelect>
            <Button
              disabled={!email.includes("@")}
              loading={add.isPending}
              onClick={() => add.mutate(undefined)}
            >
              <UserPlus aria-hidden /> Add
            </Button>
          </div>
          <p className="mt-2 text-[12px] text-muted-foreground">
            {data.roles.find((r) => r.key === role)?.description}
          </p>
          {invite ? (
            <div className="mt-3">
              <InviteLink link={invite} />
            </div>
          ) : null}
          {!data.can_manage_owners ? (
            <p className="mt-2 text-[12px] text-muted-foreground">
              Only a super admin can add, change or remove an owner.
            </p>
          ) : null}
        </Card>
      ) : null}

      <Card>
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h3 className="font-semibold">Members</h3>
          <span className="text-[13px] text-muted-foreground">
            {active.length} active
          </span>
        </div>
        {active.length === 0 ? (
          <EmptyState
            icon={ShieldCheck}
            title="No active members"
            description="Add someone to give this workspace an owner again."
          />
        ) : (
          <ul className="divide-y divide-border">
            {active.map((m) => {
              const owner = m.roles.includes("owner");
              const locked =
                !data.can_manage ||
                m.is_you ||
                (owner && !data.can_manage_owners);
              return (
                <li
                  key={m.id}
                  className="flex flex-col gap-2 px-4 py-3 md:flex-row md:items-center"
                >
                  <div className="min-w-0 flex-1">
                    <p className="flex flex-wrap items-center gap-1.5 font-medium">
                      <span className="truncate">{m.name}</span>
                      {m.is_you ? <Badge tone="outline">You</Badge> : null}
                      {m.account_status !== "active" ? (
                        <Badge tone="danger">Account disabled</Badge>
                      ) : null}
                    </p>
                    <p className="truncate text-[12px] text-muted-foreground">
                      {m.email} · joined {date(m.joined_at)} · last seen{" "}
                      {date(m.last_seen_at)}
                    </p>
                  </div>
                  {locked ? (
                    <Badge tone={owner ? "info" : "outline"}>
                      {m.roles.map(roleName).join(", ") || "No role"}
                    </Badge>
                  ) : (
                    <NativeSelect
                      aria-label={`Role for ${m.name}`}
                      value={m.roles[0] ?? ""}
                      disabled={change.isPending}
                      onChange={(e) =>
                        change.mutate({
                          membership: m.id,
                          next: e.target.value,
                        })
                      }
                      className="md:w-52"
                    >
                      {m.roles.length === 0 ? (
                        <option value="">No role</option>
                      ) : null}
                      {choices.map((r) => (
                        <option key={r.key} value={r.key}>
                          {r.name}
                        </option>
                      ))}
                    </NativeSelect>
                  )}
                  {!locked ? (
                    <Button
                      size="xs"
                      variant="ghost"
                      onClick={() => setRemoving(m)}
                    >
                      Remove
                    </Button>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
        {former.length ? (
          <details className="border-t border-border px-4 py-3 text-[13px]">
            <summary className="cursor-pointer text-muted-foreground">
              {former.length} former member{former.length === 1 ? "" : "s"}
            </summary>
            <ul className="mt-2 space-y-1">
              {former.map((m) => (
                <li key={m.id} className="truncate text-muted-foreground">
                  {m.name} · {m.email}
                </li>
              ))}
            </ul>
          </details>
        ) : null}
      </Card>

      <Dialog
        open={Boolean(removing)}
        onOpenChange={(v) => (!v ? setRemoving(null) : null)}
      >
        <DialogContent>
          <DialogHeader
            title={`Remove ${removing?.name ?? ""}?`}
            description="They lose access to this workspace straight away. Their account and other workspaces aren't affected."
          />
          <DialogFooter>
            <Button variant="ghost" onClick={() => setRemoving(null)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              loading={remove.isPending}
              onClick={() => removing && remove.mutate(removing.id)}
            >
              Remove
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
