"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Lock, ScanFace, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge, Card, CardBody, CardHeader } from "@/components/ui/display";
import { ConfirmDialog, FormField } from "@/components/app/forms";
import { InlineError, Notice } from "@/components/app/states";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/overlays";
import { useSession } from "@/features/auth/session-provider";
import { FaceCamera } from "@/features/auth/face-camera";
import { isDemo } from "@/lib/data-mode";
import { ApiError, apiRequest, errorMessage } from "@/services/api-client";

interface SavedFace {
  id: string;
  name: string;
  created_at: string;
  last_used_at: string | null;
}
interface FacesView {
  faces: SavedFace[];
  max: number;
  locked_until: string | null;
}

const when = (value: string | null) =>
  value
    ? new Date(value).toLocaleDateString(undefined, {
        day: "numeric",
        month: "short",
        year: "numeric",
      })
    : "never";

/** Face ID for the second sign-in step: up to three faces, added with your password. */
export function FaceIdCard() {
  const { session } = useSession();
  const client = useQueryClient();
  const key = ["faces", session?.user.id];
  const list = useQuery({
    queryKey: key,
    queryFn: () => apiRequest<FacesView>("GET", "/auth/faces", null),
    enabled: Boolean(session) && !isDemo,
  });
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<SavedFace | null>(null);
  const refresh = () => void client.invalidateQueries({ queryKey: key });
  const data = list.data;
  const full = data ? data.faces.length >= data.max : false;

  return (
    <Card>
      <CardHeader
        title="Face ID"
        description="After your password, Owner OS checks your face on the camera. Save up to 3 faces (for example with and without glasses)."
      />
      <CardBody className="space-y-3">
        {isDemo ? (
          <Notice tone="info">Face ID needs a live API connection.</Notice>
        ) : null}
        {list.isError ? (
          <InlineError
            message={errorMessage(list.error, "Couldn't load your faces")}
          />
        ) : null}
        {data?.locked_until ? (
          <Notice tone="warning" icon={Lock}>
            Too many wrong tries. Face and fingerprint sign-in is locked until{" "}
            {new Date(data.locked_until).toLocaleTimeString()}.
          </Notice>
        ) : null}
        {data?.faces.length ? (
          <ul className="divide-y divide-border rounded-lg border border-border">
            {data.faces.map((f) => (
              <li key={f.id} className="flex items-center gap-3 px-3 py-2.5">
                <ScanFace
                  className="size-5 shrink-0 text-primary"
                  aria-hidden
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13px] font-medium">{f.name}</p>
                  <p className="text-xs text-muted-foreground">
                    Added {when(f.created_at)} · last used{" "}
                    {when(f.last_used_at)}
                  </p>
                </div>
                <Button
                  size="xs"
                  variant="ghost"
                  aria-label={`Remove ${f.name}`}
                  onClick={() => setRemoving(f)}
                >
                  <Trash2 aria-hidden />
                </Button>
              </li>
            ))}
          </ul>
        ) : list.isSuccess ? (
          <p className="text-[13px] text-muted-foreground">
            No face saved yet. Your password alone signs you in.
          </p>
        ) : null}
        {!isDemo ? (
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <Button onClick={() => setAdding(true)} disabled={full || !data}>
              <ScanFace aria-hidden /> Add a face
            </Button>
            <p className="text-xs text-muted-foreground">
              {data ? `${data.faces.length} of ${data.max} saved. ` : ""}
              Only an encrypted face code is kept, never a photo.
            </p>
          </div>
        ) : null}
      </CardBody>
      <AddFaceDialog
        open={adding}
        onOpenChange={setAdding}
        count={data?.faces.length ?? 0}
        onAdded={refresh}
      />
      <ConfirmDialog
        open={Boolean(removing)}
        onOpenChange={(v) => (!v ? setRemoving(null) : undefined)}
        title={`Remove ${removing?.name ?? "this face"}?`}
        description="It won't be checked at sign-in any more. If no face or fingerprint is left, your password alone signs you in."
        confirmLabel="Remove"
        destructive
        onConfirm={async () => {
          if (!removing) return;
          try {
            await apiRequest("DELETE", `/auth/faces/${removing.id}`, null);
            toast.success("Face removed");
            refresh();
          } catch (e) {
            toast.error(errorMessage(e, "Couldn't remove the face"));
          } finally {
            setRemoving(null);
          }
        }}
      />
    </Card>
  );
}

function AddFaceDialog({
  open,
  onOpenChange,
  count,
  onAdded,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  count: number;
  onAdded: () => void;
}) {
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [ticket, setTicket] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function close(next: boolean) {
    if (!next) {
      setPassword("");
      setName("");
      setTicket(null);
      setError(null);
    }
    onOpenChange(next);
  }

  async function confirm() {
    setError(null);
    setBusy(true);
    try {
      const started = await apiRequest<{ ticket: string }>(
        "POST",
        "/auth/faces/start",
        null,
        { body: { password } },
      );
      setPassword("");
      setTicket(started.ticket);
    } catch (e) {
      setError(
        e instanceof ApiError && e.code === "PASSWORD_INCORRECT"
          ? "That password isn't right."
          : errorMessage(e, "Couldn't start. Please try again."),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent>
        <DialogHeader
          title={ticket ? "Scan your face" : "Add a face"}
          description={
            ticket
              ? "Look at the camera, then move a little closer when asked."
              : "First confirm it's you with your own password."
          }
        />
        <DialogBody className="space-y-3">
          {ticket ? (
            <FaceCamera
              action="Scan and save"
              onFrames={async (frames) => {
                try {
                  await apiRequest("POST", "/auth/faces", null, {
                    body: { ticket, name: name.trim(), frames },
                  });
                } catch (e) {
                  if (e instanceof ApiError && e.code === "FACE_EXPIRED") {
                    setTicket(null);
                    throw new Error(
                      "That took too long. Enter your password again.",
                    );
                  }
                  throw new Error(
                    errorMessage(e, "We couldn't save your face."),
                  );
                }
                toast.success(
                  "Face saved. It will be checked after your password.",
                );
                onAdded();
                close(false);
              }}
            />
          ) : (
            <>
              {error ? <InlineError message={error} /> : null}
              <FormField label="Your password" htmlFor="face-password">
                <Input
                  id="face-password"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && password) void confirm();
                  }}
                />
              </FormField>
              <FormField label="Name (optional)" htmlFor="face-name">
                <Input
                  id="face-name"
                  placeholder={`Face ${count + 1}`}
                  maxLength={80}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </FormField>
              <p className="text-xs text-muted-foreground">
                <Badge tone="neutral">Private</Badge> The camera pictures go
                only to Owner OS, are turned into an encrypted code, and are
                then thrown away.
              </p>
            </>
          )}
        </DialogBody>
        {ticket ? null : (
          <DialogFooter>
            <Button variant="ghost" onClick={() => close(false)}>
              Cancel
            </Button>
            <Button
              disabled={!password}
              loading={busy}
              onClick={() => void confirm()}
            >
              Continue
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
}
