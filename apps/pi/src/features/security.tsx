"use client";

/**
 * Two-step sign-in for the pi app: the password, then your face on the camera or,
 * optionally, your fingerprint. Also the "Sign-in & security" settings where you add up
 * to three faces (with your own password) and an optional fingerprint lock.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Copy,
  Fingerprint,
  Link2,
  Lock,
  MessageCircle,
  ScanFace,
  Trash2,
  Users,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import {
  Badge,
  Button,
  Card,
  CardSection,
  Dialog,
  DialogContent,
  Field,
  Input,
  Notice,
} from "@/components/ui";
import { FaceCamera, type FaceProbe } from "@/features/face-camera";
import { ApiError, del, errorText, get, post } from "@/lib/api";
import {
  addPasskey,
  fingerprintStep,
  passkeyError,
  passkeysAvailable,
  unlockName,
  type Passkey,
} from "@/lib/passkey";
import type { SessionView } from "@/lib/types";

/** The password was right, and this person also saved a face or a fingerprint. */
export interface SecondStep {
  mfa_required: true;
  ticket: string;
  methods: ("face" | "fingerprint")[];
  frames: number;
  name: string;
}

const when = (value: string | null) =>
  value
    ? new Date(value).toLocaleDateString(undefined, {
        day: "numeric",
        month: "short",
        year: "numeric",
      })
    : "never";

function useUnlockName(): string {
  const [name, setName] = React.useState("fingerprint");
  React.useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time capability probe
    setName(unlockName());
  }, []);
  return name;
}

/** Step two of signing in: the face on the camera, or the fingerprint instead. */
export function SecondStepForm({
  step,
  onBack,
  onDone,
}: {
  step: SecondStep;
  onBack: () => void;
  onDone: (session: SessionView) => Promise<void> | void;
}) {
  const hasFace = step.methods.includes("face");
  const hasFingerprint = step.methods.includes("fingerprint");
  const [mode, setMode] = React.useState<"face" | "fingerprint">(
    // The phone's own lock first (one touch, like banking apps); the camera otherwise.
    hasFingerprint ? "fingerprint" : "face",
  );
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const unlock = useUnlockName();

  function explain(e: unknown): string {
    if (e instanceof ApiError && e.code === "SIGN_IN_EXPIRED") {
      onBack();
      return "That took too long. Enter your password again.";
    }
    return errorText(e);
  }

  async function withFingerprint() {
    setError(null);
    setBusy(true);
    try {
      await onDone(
        await fingerprintStep<SessionView>(post, "/auth", step.ticket),
      );
    } catch (e) {
      const message = e instanceof ApiError ? explain(e) : passkeyError(e);
      if (message) setError(message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <button
        type="button"
        onClick={onBack}
        className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden /> Back
      </button>
      <h2 className="text-xl font-semibold">
        {mode === "face" ? "Show your face" : `Use your ${unlock}`}
      </h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Hi {step.name}. Your password was right; one more check keeps your
        business safe.
      </p>
      <div className="mt-5">
        {mode === "face" ? (
          <FaceCamera
            probe={(frame) => probeFace(step.ticket, frame)}
            autoStart
            action="Check my face"
            onFrames={async (frames) => {
              try {
                await onDone(
                  await post<SessionView>("/auth/mfa/face", {
                    ticket: step.ticket,
                    frames,
                  }),
                );
              } catch (e) {
                throw new Error(explain(e));
              }
            }}
          />
        ) : (
          <div className="space-y-3 text-center">
            <div className="mx-auto flex size-20 items-center justify-center rounded-full bg-accent-soft text-accent">
              <Fingerprint className="size-10" aria-hidden />
            </div>
            {error ? <Notice tone="danger">{error}</Notice> : null}
            <Button
              className="w-full"
              loading={busy}
              onClick={() => void withFingerprint()}
            >
              <Fingerprint className="size-4" aria-hidden /> Use {unlock}
            </Button>
          </div>
        )}
      </div>
      {hasFace && hasFingerprint ? (
        <p className="mt-5 text-center text-sm">
          <button
            type="button"
            className="font-medium text-accent hover:underline"
            onClick={() => {
              setError(null);
              setMode(mode === "face" ? "fingerprint" : "face");
            }}
          >
            {mode === "face"
              ? `Use your phone lock (${unlock}) instead`
              : "Use the camera face check instead"}
          </button>
        </p>
      ) : null}
    </div>
  );
}

interface SavedFace {
  id: string;
  name: string;
  created_at: string;
  last_used_at: string | null;
}

/** Settings → Sign-in & security. */
export function SignInSecurity() {
  return (
    <div className="space-y-4">
      <FingerprintCard />
      <FacesCard />
      <EnrollLinkCard />
    </div>
  );
}

function FacesCard() {
  const client = useQueryClient();
  const faces = useQuery({
    queryKey: ["faces"],
    queryFn: () =>
      get<{ faces: SavedFace[]; max: number; locked_until: string | null }>(
        "/auth/faces",
      ),
  });
  const [adding, setAdding] = React.useState(false);
  const refresh = () => void client.invalidateQueries({ queryKey: ["faces"] });
  const data = faces.data;
  return (
    <Card>
      <CardSection>
        <h2 className="font-semibold">Camera face check</h2>
        <p className="text-sm text-muted-foreground">
          For phones and computers without a fingerprint: after your password,
          the camera checks your face live. Save up to 3 faces (yours, with
          glasses, or a colleague&apos;s).
        </p>
        <div className="mt-4 space-y-3">
          {faces.isError ? (
            <Notice tone="danger">{errorText(faces.error)}</Notice>
          ) : null}
          {data?.locked_until ? (
            <Notice tone="warning" title="Locked for now">
              Too many wrong tries. Face and fingerprint sign-in opens again at{" "}
              {new Date(data.locked_until).toLocaleTimeString()}.
            </Notice>
          ) : null}
          {data?.faces.length ? (
            <ul className="divide-y divide-border rounded-lg border border-border">
              {data.faces.map((f) => (
                <li key={f.id} className="flex items-center gap-3 px-3 py-2.5">
                  <ScanFace
                    className="size-5 shrink-0 text-accent"
                    aria-hidden
                  />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{f.name}</p>
                    <p className="text-xs text-muted-foreground">
                      Added {when(f.created_at)} · last used{" "}
                      {when(f.last_used_at)}
                    </p>
                  </div>
                  <Button
                    size="icon"
                    variant="ghost"
                    aria-label={`Remove ${f.name}`}
                    onClick={async () => {
                      try {
                        await del(`/auth/faces/${f.id}`);
                        toast.success("Face removed");
                        refresh();
                      } catch (e) {
                        toast.error(errorText(e));
                      }
                    }}
                  >
                    <Trash2 className="size-4" aria-hidden />
                  </Button>
                </li>
              ))}
            </ul>
          ) : faces.isSuccess ? (
            <p className="text-sm text-muted-foreground">
              No face saved yet. Your password alone signs you in.
            </p>
          ) : null}
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <Button
              onClick={() => setAdding(true)}
              disabled={!data || data.faces.length >= data.max}
            >
              <ScanFace className="size-4" aria-hidden /> Add a face
            </Button>
            <p className="text-xs text-muted-foreground">
              {data ? `${data.faces.length} of ${data.max} saved. ` : ""}Only an
              encrypted face code is kept, never a photo.
            </p>
          </div>
        </div>
      </CardSection>
      <AddFaceDialog
        open={adding}
        onOpenChange={setAdding}
        count={data?.faces.length ?? 0}
        onAdded={refresh}
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
  const [password, setPassword] = React.useState("");
  const [name, setName] = React.useState("");
  const [ticket, setTicket] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

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
      const started = await post<{ ticket: string }>("/auth/faces/start", {
        password,
      });
      setPassword("");
      setTicket(started.ticket);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent
        title={ticket ? "Scan your face" : "Add a face"}
        description={
          ticket
            ? "Look at the camera, then move a little closer when asked."
            : "First confirm it's you with your own password."
        }
      >
        {ticket ? (
          <FaceCamera
            probe={(frame) => probeFace(ticket, frame)}
            action="Start face scan"
            onFrames={async (frames) => {
              try {
                await post("/auth/faces", {
                  ticket,
                  name: name.trim(),
                  frames,
                });
              } catch (e) {
                if (e instanceof ApiError && e.code === "FACE_EXPIRED") {
                  setTicket(null);
                }
                throw new Error(errorText(e));
              }
              toast.success(
                "Face saved. It will be checked after your password.",
              );
              onAdded();
              close(false);
            }}
          />
        ) : (
          <div className="space-y-4">
            {error ? <Notice tone="danger">{error}</Notice> : null}
            <Field label="Your password" htmlFor="face-password">
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
            </Field>
            <Field label="Name (optional)" htmlFor="face-name">
              <Input
                id="face-name"
                placeholder={`Face ${count + 1}`}
                maxLength={80}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </Field>
            <p className="text-xs text-muted-foreground">
              <Badge tone="neutral">Private</Badge> Camera pictures go only to
              pi, become an encrypted code, and are then thrown away.
            </p>
            <div className="flex justify-end gap-2">
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
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function FingerprintCard() {
  const client = useQueryClient();
  const keys = useQuery({
    queryKey: ["passkeys"],
    queryFn: () => get<Passkey[]>("/auth/passkeys"),
  });
  const [supported, setSupported] = React.useState(false);
  const unlock = useUnlockName();
  const [open, setOpen] = React.useState(false);
  const [password, setPassword] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  React.useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time capability probe
    setSupported(passkeysAvailable());
  }, []);
  const refresh = () =>
    void client.invalidateQueries({ queryKey: ["passkeys"] });

  async function add() {
    setError(null);
    setBusy(true);
    try {
      await addPasskey(post, "/auth/passkeys", { password }, "");
      toast.success(
        `${unlock} is ready. It will be offered after your password.`,
      );
      setOpen(false);
      setPassword("");
      refresh();
    } catch (e) {
      const message = e instanceof ApiError ? errorText(e) : passkeyError(e);
      if (message) setError(message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardSection>
        <h2 className="flex items-center gap-2 font-semibold">
          <Lock className="size-4" aria-hidden /> Phone lock (recommended)
        </h2>
        <p className="text-sm text-muted-foreground">
          After your password, unlock with the fingerprint or face unlock
          already set up on this phone (Face ID, Touch ID, Windows Hello). One
          touch, like banking apps.
        </p>
        <div className="mt-4 space-y-3">
          {!supported ? (
            <Notice tone="info">
              This browser can&apos;t use a fingerprint lock. Try the latest
              Chrome, Edge or Safari.
            </Notice>
          ) : null}
          {keys.data?.length ? (
            <ul className="divide-y divide-border rounded-lg border border-border">
              {keys.data.map((k) => (
                <li key={k.id} className="flex items-center gap-3 px-3 py-2.5">
                  <Fingerprint
                    className="size-5 shrink-0 text-accent"
                    aria-hidden
                  />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{k.name}</p>
                    <p className="text-xs text-muted-foreground">
                      Added {when(k.created_at)} · last used{" "}
                      {when(k.last_used_at)}
                    </p>
                  </div>
                  <Button
                    size="icon"
                    variant="ghost"
                    aria-label={`Remove ${k.name}`}
                    onClick={async () => {
                      try {
                        await del(`/auth/passkeys/${k.id}`);
                        toast.success("Fingerprint removed");
                        refresh();
                      } catch (e) {
                        toast.error(errorText(e));
                      }
                    }}
                  >
                    <Trash2 className="size-4" aria-hidden />
                  </Button>
                </li>
              ))}
            </ul>
          ) : keys.isSuccess ? (
            <p className="text-sm text-muted-foreground">
              No fingerprint added.
            </p>
          ) : null}
          {supported ? (
            <Button variant="secondary" onClick={() => setOpen(true)}>
              <Fingerprint className="size-4" aria-hidden /> Add {unlock}
            </Button>
          ) : null}
        </div>
      </CardSection>
      <Dialog
        open={open}
        onOpenChange={(v) => {
          setOpen(v);
          if (!v) {
            setPassword("");
            setError(null);
          }
        }}
      >
        <DialogContent
          title={`Add ${unlock}`}
          description="Confirm your own password, then your device will ask for your fingerprint."
        >
          <div className="space-y-4">
            {error ? <Notice tone="danger">{error}</Notice> : null}
            <Field label="Your password" htmlFor="finger-password">
              <Input
                id="finger-password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </Field>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button
                disabled={!password}
                loading={busy}
                onClick={() => void add()}
              >
                Continue
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

/** Live camera guidance during a sign-in, an add-a-face or an enrollment link. */
export function probeFace(ticket: string, frame: string) {
  return post<FaceProbe>("/auth/face/probe", { ticket, frame });
}

/** A one-time link for someone else (or another phone) to add a face or phone lock. */
function EnrollLinkCard() {
  const [link, setLink] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  async function create() {
    setBusy(true);
    try {
      setLink((await post<{ link: string }>("/auth/enroll-links")).link);
    } catch (e) {
      toast.error(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  const message = link
    ? `Open this link to add your face or phone lock to our pi account (works once, for 30 minutes): ${link}`
    : "";
  return (
    <Card>
      <CardSection className="space-y-3">
        <div>
          <h2 className="flex items-center gap-2 font-semibold">
            <Users className="size-4" aria-hidden /> Add someone else, or
            another phone
          </h2>
          <p className="text-sm text-muted-foreground">
            Make a one-time link. Whoever opens it enters this account&apos;s
            email and password, then scans their face or uses their phone&apos;s
            fingerprint.
          </p>
        </div>
        {link ? (
          <>
            <div className="flex min-w-0 items-center gap-2 rounded-lg border border-border bg-surface-muted px-3 py-2">
              <Link2
                className="size-4 shrink-0 text-muted-foreground"
                aria-hidden
              />
              <code className="min-w-0 flex-1 truncate text-xs">{link}</code>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                variant="secondary"
                onClick={() =>
                  void navigator.clipboard
                    .writeText(link)
                    .then(() => toast.success("Link copied"))
                }
              >
                <Copy className="size-4" aria-hidden /> Copy link
              </Button>
              <Button variant="secondary" asChild>
                <a
                  href={`https://wa.me/?text=${encodeURIComponent(message)}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  <MessageCircle className="size-4" aria-hidden /> Share on
                  WhatsApp
                </a>
              </Button>
              <Button
                variant="ghost"
                loading={busy}
                onClick={() => void create()}
              >
                New link
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Works once and for 30 minutes. Only share it with someone you
              trust: they will be able to sign in to this account.
            </p>
          </>
        ) : (
          <Button loading={busy} onClick={() => void create()}>
            <Users className="size-4" aria-hidden /> Make a link
          </Button>
        )}
      </CardSection>
    </Card>
  );
}
