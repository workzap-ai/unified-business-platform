"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { CheckCircle2, Fingerprint, ScanFace } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormField } from "@/components/app/forms";
import { InlineError, Notice } from "@/components/app/states";
import { apiRequest, errorMessage } from "@/services/api-client";
import { FaceCamera } from "./face-camera";
import {
  deviceUnlockAvailable,
  enrollPhoneLock,
  passkeyError,
  probeFace,
  unlockName,
} from "./passkey";

interface Started {
  ticket: string;
  name: string;
  faces_left: number;
}

/**
 * The page behind a shared enrollment link: only the account's email and password,
 * then this person's face (camera) or this phone's own lock. It never signs anyone in.
 */
export function EnrollForm({ token }: { token: string }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [started, setStarted] = useState<Started | null>(null);
  const [mode, setMode] = useState<"choose" | "face" | "done">("choose");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [phone, setPhone] = useState({ ok: false, name: "fingerprint" });

  useEffect(() => {
    void deviceUnlockAvailable().then((ok) =>
      setPhone({ ok, name: unlockName() }),
    );
  }, []);

  async function start(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      setStarted(
        await apiRequest<Started>("POST", "/auth/enroll/start", null, {
          body: { token, email: email.trim(), password },
        }),
      );
      setPassword("");
    } catch (e) {
      setError(
        errorMessage(e, "That didn't work. Check the email and password."),
      );
    } finally {
      setBusy(false);
    }
  }

  async function addPhoneLock() {
    if (!started) return;
    setError(null);
    setBusy(true);
    try {
      await enrollPhoneLock(started.ticket, name.trim());
      setMode("done");
    } catch (e) {
      const message =
        e instanceof DOMException
          ? passkeyError(e)
          : errorMessage(e, "That didn't work.");
      if (message) setError(message);
    } finally {
      setBusy(false);
    }
  }

  if (mode === "done")
    return (
      <div className="text-center">
        <CheckCircle2 className="mx-auto size-12 text-success" aria-hidden />
        <h1 className="mt-3 text-2xl font-semibold tracking-tight">All set</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          From now on, after the password, this face or this phone&apos;s lock
          opens the account.
        </p>
        <Button asChild className="mt-6">
          <Link href="/login">Go to sign in</Link>
        </Button>
      </div>
    );

  if (!started)
    return (
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Add your face or phone lock
        </h1>
        <p className="mt-1.5 text-sm text-muted-foreground">
          Someone shared this link with you. Enter the account&apos;s email and
          password to continue. This link works once.
        </p>
        <form onSubmit={start} className="mt-6 space-y-4" noValidate>
          {error ? <InlineError message={error} /> : null}
          <FormField label="Email" htmlFor="enroll-email">
            <Input
              id="enroll-email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </FormField>
          <FormField label="Password" htmlFor="enroll-password">
            <Input
              id="enroll-password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </FormField>
          <Button
            type="submit"
            size="lg"
            className="w-full"
            loading={busy}
            disabled={!email.includes("@") || !password}
          >
            Continue
          </Button>
        </form>
      </div>
    );

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">
        {mode === "face" ? "Scan your face" : "Choose how you'll unlock"}
      </h1>
      <p className="mt-1.5 text-sm text-muted-foreground">
        For {started.name}&apos;s account. After the password, this will be
        checked at sign-in.
      </p>
      <div className="mt-6 space-y-4">
        {error ? <InlineError message={error} /> : null}
        <FormField label="Your name (optional)" htmlFor="enroll-name">
          <Input
            id="enroll-name"
            maxLength={80}
            placeholder="e.g. Sara"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </FormField>
        {mode === "face" ? (
          <FaceCamera
            probe={(frame) => probeFace(started.ticket, frame)}
            action="Start face scan"
            onFrames={async (frames) => {
              try {
                await apiRequest("POST", "/auth/enroll/face", null, {
                  body: { ticket: started.ticket, name: name.trim(), frames },
                });
              } catch (e) {
                throw new Error(errorMessage(e, "We couldn't save your face."));
              }
              setMode("done");
            }}
          />
        ) : (
          <div className="grid gap-3">
            {phone.ok ? (
              <Button
                size="lg"
                loading={busy}
                onClick={() => void addPhoneLock()}
              >
                <Fingerprint aria-hidden /> Use this phone&apos;s {phone.name}
              </Button>
            ) : null}
            <Button
              size="lg"
              variant={phone.ok ? "secondary" : "default"}
              disabled={started.faces_left === 0}
              onClick={() => setMode("face")}
            >
              <ScanFace aria-hidden /> Scan my face with the camera
            </Button>
            {started.faces_left === 0 ? (
              <Notice tone="info">
                This account already has 3 faces. Use the phone lock, or ask
                them to remove a face first.
              </Notice>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}
