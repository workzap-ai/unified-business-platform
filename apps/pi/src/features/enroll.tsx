"use client";

/**
 * The page behind a shared pi enrollment link: only the account's email and password,
 * then this person's face (camera) or this phone's own lock. It never signs anyone in.
 */
import { CheckCircle2, Fingerprint, ScanFace } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import {
  Button,
  Card,
  CardSection,
  Field,
  Input,
  Notice,
} from "@/components/ui";
import { FaceCamera } from "@/features/face-camera";
import { probeFace } from "@/features/security";
import { ApiError, errorText, post } from "@/lib/api";
import {
  createCredential,
  deviceUnlockAvailable,
  passkeyError,
  unlockName,
} from "@/lib/passkey";

interface Started {
  ticket: string;
  name: string;
  faces_left: number;
}

export function EnrollForm({ token }: { token: string }) {
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [name, setName] = React.useState("");
  const [started, setStarted] = React.useState<Started | null>(null);
  const [mode, setMode] = React.useState<"choose" | "face" | "done">("choose");
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [phone, setPhone] = React.useState({ ok: false, name: "fingerprint" });

  React.useEffect(() => {
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
        await post<Started>("/auth/enroll/start", {
          token,
          email: email.trim(),
          password,
        }),
      );
      setPassword("");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  async function addPhoneLock() {
    if (!started) return;
    setError(null);
    setBusy(true);
    try {
      const options = await post<Record<string, unknown>>(
        "/auth/enroll/fingerprint/options",
        { ticket: started.ticket },
      );
      await post("/auth/enroll/fingerprint", {
        ticket: started.ticket,
        name: name.trim(),
        credential: await createCredential(options),
      });
      setMode("done");
    } catch (e) {
      const message = e instanceof ApiError ? errorText(e) : passkeyError(e);
      if (message) setError(message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-md px-4 py-10">
      <Card>
        <CardSection className="space-y-5">
          {mode === "done" ? (
            <div className="text-center">
              <CheckCircle2
                className="mx-auto size-12 text-success"
                aria-hidden
              />
              <h1 className="mt-3 text-2xl font-semibold">All set</h1>
              <p className="mt-2 text-sm text-muted-foreground">
                From now on, after the password, this face or this phone&apos;s
                lock opens the account.
              </p>
              <Button asChild className="mt-6">
                <Link href="/sign-in">Go to sign in</Link>
              </Button>
            </div>
          ) : !started ? (
            <>
              <div>
                <h1 className="text-2xl font-semibold">
                  Add your face or phone lock
                </h1>
                <p className="mt-1 text-sm text-muted-foreground">
                  Someone shared this link with you. Enter the account&apos;s
                  email and password to continue. This link works once.
                </p>
              </div>
              <form onSubmit={start} className="space-y-4" noValidate>
                {error ? <Notice tone="danger">{error}</Notice> : null}
                <Field label="Email" htmlFor="enroll-email">
                  <Input
                    id="enroll-email"
                    type="email"
                    autoComplete="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </Field>
                <Field label="Password" htmlFor="enroll-password">
                  <Input
                    id="enroll-password"
                    type="password"
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                </Field>
                <Button
                  type="submit"
                  className="w-full"
                  loading={busy}
                  disabled={!email.includes("@") || !password}
                >
                  Continue
                </Button>
              </form>
            </>
          ) : (
            <>
              <div>
                <h1 className="text-2xl font-semibold">
                  {mode === "face"
                    ? "Scan your face"
                    : "Choose how you'll unlock"}
                </h1>
                <p className="mt-1 text-sm text-muted-foreground">
                  For {started.name}&apos;s account. After the password, this
                  will be checked at sign-in.
                </p>
              </div>
              {error ? <Notice tone="danger">{error}</Notice> : null}
              <Field label="Your name (optional)" htmlFor="enroll-name">
                <Input
                  id="enroll-name"
                  maxLength={80}
                  placeholder="e.g. Sara"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </Field>
              {mode === "face" ? (
                <FaceCamera
                  probe={(frame) => probeFace(started.ticket, frame)}
                  action="Start face scan"
                  onFrames={async (frames) => {
                    try {
                      await post("/auth/enroll/face", {
                        ticket: started.ticket,
                        name: name.trim(),
                        frames,
                      });
                    } catch (e) {
                      throw new Error(errorText(e));
                    }
                    setMode("done");
                  }}
                />
              ) : (
                <div className="grid gap-3">
                  {phone.ok ? (
                    <Button loading={busy} onClick={() => void addPhoneLock()}>
                      <Fingerprint className="size-4" aria-hidden /> Use this
                      phone&apos;s {phone.name}
                    </Button>
                  ) : null}
                  <Button
                    variant={phone.ok ? "secondary" : "primary"}
                    disabled={started.faces_left === 0}
                    onClick={() => setMode("face")}
                  >
                    <ScanFace className="size-4" aria-hidden /> Scan my face
                    with the camera
                  </Button>
                  {started.faces_left === 0 ? (
                    <Notice tone="info">
                      This account already has 3 faces. Use the phone lock, or
                      ask them to remove a face first.
                    </Notice>
                  ) : null}
                </div>
              )}
            </>
          )}
        </CardSection>
      </Card>
    </div>
  );
}
