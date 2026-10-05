"use client";

/**
 * pi Customer's check after the WhatsApp code (face on the camera or an optional
 * fingerprint), and the dashboard card to add them. Adding needs a fresh code.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Fingerprint, ScanFace, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button, Card, CardSection, Notice } from "@/components/ui";
import { FaceCamera } from "@/features/face-camera";
import { ApiError, errorText } from "@/lib/api";
import {
  customerDelete,
  customerGet,
  customerPost,
  type CustomerMe,
} from "@/lib/customer-api";
import {
  addPasskey,
  fingerprintStep,
  passkeyError,
  passkeysAvailable,
  unlockName,
  type Passkey,
} from "@/lib/passkey";

export interface CustomerSecondStep {
  mfa_required: true;
  ticket: string;
  methods: ("face" | "fingerprint")[];
  frames: number;
  phone: string;
}

const KEY = ["pi-customer", "security"] as const;

function useUnlock(): { ok: boolean; name: string } {
  const [state, setState] = useState({ ok: false, name: "fingerprint" });
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time capability probe
    setState({ ok: passkeysAvailable(), name: unlockName() });
  }, []);
  return state;
}

/** After a correct WhatsApp code: the face, or the fingerprint instead. */
export function CustomerSecondStepForm({
  step,
  onBack,
  onDone,
}: {
  step: CustomerSecondStep;
  onBack: () => void;
  onDone: (me: CustomerMe) => void;
}) {
  const hasFace = step.methods.includes("face");
  const hasFingerprint = step.methods.includes("fingerprint");
  const [mode, setMode] = useState<"face" | "fingerprint">(
    hasFace ? "face" : "fingerprint",
  );
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const unlock = useUnlock();

  function explain(e: unknown): string {
    if (e instanceof ApiError && e.code === "SIGN_IN_EXPIRED") onBack();
    return errorText(e);
  }

  async function withFingerprint() {
    setError(null);
    setBusy(true);
    try {
      onDone(await fingerprintStep<CustomerMe>(customerPost, "", step.ticket));
    } catch (e) {
      const message = e instanceof ApiError ? explain(e) : passkeyError(e);
      if (message) setError(message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <button
        type="button"
        onClick={onBack}
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden /> {step.phone}
      </button>
      <div>
        <h2 className="text-xl font-semibold">
          {mode === "face" ? "Show your face" : `Use your ${unlock.name}`}
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Your code was right; one more check keeps your chats private.
        </p>
      </div>
      {mode === "face" ? (
        <FaceCamera
          autoStart
          action="Check my face"
          onFrames={async (frames) => {
            try {
              onDone(
                await customerPost<CustomerMe>("/mfa/face", {
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
            size="lg"
            className="w-full"
            loading={busy}
            onClick={() => void withFingerprint()}
          >
            <Fingerprint className="size-4" aria-hidden /> Use {unlock.name}
          </Button>
        </div>
      )}
      {hasFace && hasFingerprint ? (
        <p className="text-center text-sm">
          <button
            type="button"
            className="font-medium text-accent hover:underline"
            onClick={() => {
              setError(null);
              setMode(mode === "face" ? "fingerprint" : "face");
            }}
          >
            {mode === "face"
              ? `Use ${unlock.name} instead`
              : "Use my face instead"}
          </button>
        </p>
      ) : null}
    </div>
  );
}

interface SecurityView {
  faces: {
    id: string;
    name: string;
    created_at: string;
    last_used_at: string | null;
  }[];
  fingerprints: Passkey[];
  max: number;
  fresh: boolean;
}

/** Dashboard card: Face ID (up to 3) and an optional fingerprint for the next sign-in. */
export function CustomerSecurityCard() {
  const client = useQueryClient();
  const data = useQuery({
    queryKey: KEY,
    queryFn: () => customerGet<SecurityView>("/faces"),
  });
  const [scanning, setScanning] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const unlock = useUnlock();
  const refresh = () => void client.invalidateQueries({ queryKey: KEY });
  const view = data.data;

  async function startFace() {
    setError(null);
    try {
      const started = await customerPost<{ ticket: string }>("/faces/start");
      setScanning(started.ticket);
    } catch (e) {
      setError(errorText(e));
    }
  }

  async function addFingerprint() {
    setError(null);
    setBusy(true);
    try {
      await addPasskey(customerPost, "/fingerprints", undefined, "");
      toast.success(`${unlock.name} added. It will be asked after your code.`);
      refresh();
    } catch (e) {
      const message = e instanceof ApiError ? errorText(e) : passkeyError(e);
      if (message) setError(message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(path: string) {
    try {
      await customerDelete(path);
      refresh();
    } catch (e) {
      toast.error(errorText(e));
    }
  }

  return (
    <Card>
      <CardSection className="space-y-3">
        <div>
          <h2 className="flex items-center gap-2 font-semibold">
            <ScanFace className="size-4 text-accent" aria-hidden /> Face ID
          </h2>
          <p className="text-sm text-muted-foreground">
            After your WhatsApp code, check your face too, so only you can open
            your chats.
          </p>
        </div>
        {error ? <Notice tone="danger">{error}</Notice> : null}
        {view && !view.fresh && !scanning ? (
          <Notice tone="info">
            To add Face ID or a fingerprint, sign out and sign in again with a
            new WhatsApp code.
          </Notice>
        ) : null}
        {scanning ? (
          <FaceCamera
            action="Scan and save"
            onFrames={async (frames) => {
              try {
                await customerPost("/faces", { ticket: scanning, frames });
              } catch (e) {
                throw new Error(errorText(e));
              }
              toast.success("Face saved. It will be checked after your code.");
              setScanning(null);
              refresh();
            }}
          />
        ) : null}
        {view?.faces.length || view?.fingerprints.length ? (
          <ul className="divide-y divide-border rounded-lg border border-border text-sm">
            {view.faces.map((f) => (
              <li key={f.id} className="flex items-center gap-2 px-3 py-2">
                <ScanFace className="size-4 text-accent" aria-hidden />
                <span className="min-w-0 flex-1 truncate">{f.name}</span>
                <Button
                  size="icon"
                  variant="ghost"
                  aria-label={`Remove ${f.name}`}
                  onClick={() => void remove(`/faces/${f.id}`)}
                >
                  <Trash2 className="size-4" aria-hidden />
                </Button>
              </li>
            ))}
            {view.fingerprints.map((k) => (
              <li key={k.id} className="flex items-center gap-2 px-3 py-2">
                <Fingerprint className="size-4 text-accent" aria-hidden />
                <span className="min-w-0 flex-1 truncate">{k.name}</span>
                <Button
                  size="icon"
                  variant="ghost"
                  aria-label={`Remove ${k.name}`}
                  onClick={() => void remove(`/fingerprints/${k.id}`)}
                >
                  <Trash2 className="size-4" aria-hidden />
                </Button>
              </li>
            ))}
          </ul>
        ) : null}
        {view && !scanning ? (
          <div className="flex flex-col gap-2">
            <Button
              onClick={() => void startFace()}
              disabled={!view.fresh || view.faces.length >= view.max}
            >
              <ScanFace className="size-4" aria-hidden /> Add a face (
              {view.faces.length}/{view.max})
            </Button>
            {unlock.ok ? (
              <Button
                variant="secondary"
                loading={busy}
                disabled={!view.fresh}
                onClick={() => void addFingerprint()}
              >
                <Fingerprint className="size-4" aria-hidden /> Add {unlock.name}{" "}
                (optional)
              </Button>
            ) : null}
            <p className="text-xs text-muted-foreground">
              Only an encrypted face code is kept, never a photo.
            </p>
          </div>
        ) : null}
      </CardSection>
    </Card>
  );
}
