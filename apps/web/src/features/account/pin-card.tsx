"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound } from "lucide-react";
import { toast } from "sonner";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge, Card, CardBody, CardHeader } from "@/components/ui/display";
import { FormField } from "@/components/app/forms";
import { useSession } from "@/features/auth/session-provider";
import { isDemo } from "@/lib/data-mode";
import { apiRequest, errorMessage } from "@/services/api-client";

const pinSchema = z.object({ set: z.boolean() });

/** An optional 6-digit PIN, asked after the password on any computer. */
export function PinCard() {
  const { session } = useSession();
  const client = useQueryClient();
  const key = ["sign-in-pin", session?.user.id];
  const status = useQuery({
    queryKey: key,
    queryFn: () => apiRequest("GET", "/auth/pin", pinSchema),
    enabled: Boolean(session) && !isDemo,
  });
  const [open, setOpen] = useState<"set" | "remove" | null>(null);
  const [password, setPassword] = useState("");
  const [pin, setPin] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function close() {
    setOpen(null);
    setPassword("");
    setPin("");
    setError(null);
  }

  async function submit() {
    setError(null);
    setBusy(true);
    try {
      if (open === "set") {
        await apiRequest("PUT", "/auth/pin", pinSchema, {
          body: { password, pin },
        });
        toast.success("PIN saved. You can use it after your password.");
      } else {
        await apiRequest("POST", "/auth/pin/remove", pinSchema, {
          body: { password },
        });
        toast.success("PIN removed");
      }
      close();
      await client.invalidateQueries({ queryKey: key });
    } catch (e) {
      setError(errorMessage(e, "That didn't work. Try again."));
    } finally {
      setBusy(false);
    }
  }

  const isSet = status.data?.set ?? false;
  return (
    <Card>
      <CardHeader
        title="Sign-in PIN"
        icon={<KeyRound />}
        description="A 6-digit PIN after your password, for computers without Windows Hello or a fingerprint"
        actions={isSet ? <Badge tone="success">On</Badge> : <Badge>Off</Badge>}
      />
      <CardBody className="space-y-3">
        {open ? (
          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              void submit();
            }}
          >
            <FormField
              label="Your password"
              htmlFor="pin-password"
              error={error ?? undefined}
            >
              <Input
                id="pin-password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoFocus
              />
            </FormField>
            {open === "set" ? (
              <FormField
                label="New 6-digit PIN"
                htmlFor="pin-new"
                help="Not a run or a repeat like 123456 or 111111."
              >
                <Input
                  id="pin-new"
                  type="password"
                  inputMode="numeric"
                  autoComplete="new-password"
                  maxLength={6}
                  value={pin}
                  onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))}
                />
              </FormField>
            ) : null}
            <div className="flex flex-wrap gap-2">
              <Button
                type="submit"
                loading={busy}
                variant={open === "remove" ? "danger" : "default"}
                disabled={!password || (open === "set" && pin.length !== 6)}
              >
                {open === "set" ? "Save PIN" : "Remove PIN"}
              </Button>
              <Button type="button" variant="ghost" onClick={close}>
                Cancel
              </Button>
            </div>
          </form>
        ) : (
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              disabled={isDemo || status.isPending}
              onClick={() => setOpen("set")}
            >
              {isSet ? "Change PIN" : "Set a PIN"}
            </Button>
            {isSet ? (
              <Button variant="ghost" onClick={() => setOpen("remove")}>
                Remove
              </Button>
            ) : null}
          </div>
        )}
      </CardBody>
    </Card>
  );
}
