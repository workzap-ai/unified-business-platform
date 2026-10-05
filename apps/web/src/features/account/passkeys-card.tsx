"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ScanFace, Trash2 } from "lucide-react";
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
import {
  deviceUnlockAvailable,
  passkeyApi,
  passkeyError,
  passkeysAvailable,
  unlockName,
  type Passkey,
} from "@/features/auth/passkey";
import { isDemo } from "@/lib/data-mode";
import { ApiError, errorMessage } from "@/services/api-client";

const when = (value: string | null) =>
  value
    ? new Date(value).toLocaleDateString(undefined, {
        day: "numeric",
        month: "short",
        year: "numeric",
      })
    : "never";

/** Face ID / Touch ID / Windows Hello / fingerprint sign-in, managed per device. */
export function PasskeysCard() {
  const { session } = useSession();
  const client = useQueryClient();
  const key = ["passkeys", session?.user.id];
  const list = useQuery({
    queryKey: key,
    queryFn: passkeyApi.list,
    enabled: Boolean(session) && !isDemo,
  });
  const [support, setSupport] = useState({
    browser: false,
    unlock: false,
    name: "Face ID",
  });
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<Passkey | null>(null);

  useEffect(() => {
    const browser = passkeysAvailable();
    void deviceUnlockAvailable().then((unlock) =>
      setSupport({ browser, unlock, name: unlockName() }),
    );
  }, []);

  async function remove(item: Passkey) {
    try {
      await passkeyApi.remove(item.id);
      toast.success("Passkey removed");
      await client.invalidateQueries({ queryKey: key });
    } catch (e) {
      toast.error(errorMessage(e, "Couldn't remove the passkey"));
    } finally {
      setRemoving(null);
    }
  }

  return (
    <Card>
      <CardHeader
        title="Face ID & passkeys"
        description="Sign in with your face or fingerprint instead of typing a password. It's faster and phishing-proof."
      />
      <CardBody className="space-y-3">
        {isDemo ? (
          <Notice tone="info">Passkeys need a live API connection.</Notice>
        ) : !support.browser ? (
          <Notice tone="warning">
            This browser can&apos;t use passkeys. Try the latest Safari, Chrome
            or Edge on a secure (https) address.
          </Notice>
        ) : null}
        {list.isError ? (
          <InlineError
            message={errorMessage(list.error, "Couldn't load your passkeys")}
          />
        ) : null}
        {list.data?.length ? (
          <ul className="divide-y divide-border rounded-lg border border-border">
            {list.data.map((p) => (
              <li key={p.id} className="flex items-center gap-3 px-3 py-2.5">
                <ScanFace
                  className="size-5 shrink-0 text-primary"
                  aria-hidden
                />
                <div className="min-w-0 flex-1">
                  <p className="flex flex-wrap items-center gap-1.5 text-[13px] font-medium">
                    <span className="truncate">{p.name}</span>
                    {p.synced ? <Badge tone="neutral">Synced</Badge> : null}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Added {when(p.created_at)} · last used{" "}
                    {when(p.last_used_at)}
                  </p>
                </div>
                <Button
                  size="xs"
                  variant="ghost"
                  aria-label={`Remove ${p.name}`}
                  onClick={() => setRemoving(p)}
                >
                  <Trash2 aria-hidden />
                </Button>
              </li>
            ))}
          </ul>
        ) : list.isSuccess ? (
          <p className="text-[13px] text-muted-foreground">
            No passkeys yet. Add one on each phone or computer you use.
          </p>
        ) : null}
        {support.browser && !isDemo ? (
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <Button onClick={() => setAdding(true)}>
              <ScanFace aria-hidden />
              {support.unlock ? `Add ${support.name}` : "Add a passkey"}
            </Button>
            <p className="text-xs text-muted-foreground">
              Your face or fingerprint stays on this device; Owner OS only keeps
              a public key.
            </p>
          </div>
        ) : null}
      </CardBody>
      <AddPasskeyDialog
        open={adding}
        onOpenChange={setAdding}
        unlock={support.name}
        onAdded={() => void client.invalidateQueries({ queryKey: key })}
      />
      <ConfirmDialog
        open={Boolean(removing)}
        onOpenChange={(v) => (!v ? setRemoving(null) : undefined)}
        title={`Remove ${removing?.name ?? "this passkey"}?`}
        description="You won't be able to sign in with it any more. You can add it again later."
        confirmLabel="Remove"
        destructive
        onConfirm={() => removing && remove(removing)}
      />
    </Card>
  );
}

function AddPasskeyDialog({
  open,
  onOpenChange,
  unlock,
  onAdded,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  unlock: string;
  onAdded: () => void;
}) {
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function close(next: boolean) {
    if (!next) {
      setPassword("");
      setName("");
      setError(null);
    }
    onOpenChange(next);
  }

  async function add() {
    setError(null);
    setBusy(true);
    try {
      await passkeyApi.add(password, name.trim());
      toast.success(`${unlock} is ready. Use it next time you sign in.`);
      onAdded();
      close(false);
    } catch (e) {
      if (e instanceof ApiError) {
        setError(
          e.code === "PASSWORD_INCORRECT"
            ? "That password isn't right."
            : errorMessage(e, "Couldn't add the passkey"),
        );
      } else {
        const message = passkeyError(e);
        if (message) setError(message);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent>
        <DialogHeader
          title={`Add ${unlock}`}
          description="Confirm your password, then your device will ask for your face, fingerprint or PIN."
        />
        <DialogBody className="space-y-3">
          {error ? <InlineError message={error} /> : null}
          <FormField label="Your password" htmlFor="passkey-password">
            <Input
              id="passkey-password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && password) void add();
              }}
            />
          </FormField>
          <FormField label="Name (optional)" htmlFor="passkey-name">
            <Input
              id="passkey-name"
              placeholder="e.g. My iPhone"
              maxLength={80}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </FormField>
        </DialogBody>
        <DialogFooter>
          <Button variant="ghost" onClick={() => close(false)}>
            Cancel
          </Button>
          <Button
            disabled={!password}
            loading={busy}
            onClick={() => void add()}
          >
            <ScanFace aria-hidden /> Continue
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
