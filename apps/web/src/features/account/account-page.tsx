"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { KeyRound, LogOut } from "lucide-react";
import { humanize } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Avatar,
  Badge,
  Card,
  CardBody,
  CardHeader,
} from "@/components/ui/display";
import { PageHeader, PageShell } from "@/components/app/page";
import { ConfirmDialog, FormField } from "@/components/app/forms";
import { InlineError } from "@/components/app/states";
import { PropertyList } from "@/components/app/record";
import { useScopedMutation } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import { authService } from "@/features/auth/service";
import { ApiError, errorMessage } from "@/services/api-client";

const passwordSchema = z
  .object({
    current: z.string().min(1, "Enter your current password"),
    next: z
      .string()
      .min(12, "Use at least 12 characters")
      .max(256, "Use at most 256 characters"),
    confirm: z.string().min(1, "Repeat the new password"),
  })
  .refine((v) => v.next === v.confirm, {
    path: ["confirm"],
    message: "Passwords don't match",
  })
  .refine((v) => !v.next || v.next !== v.current, {
    path: ["next"],
    message: "Choose a password different from the current one",
  });
type PasswordValues = z.infer<typeof passwordSchema>;
const EMPTY: PasswordValues = { current: "", next: "", confirm: "" };

export function AccountPage() {
  const { session } = useSession();
  if (!session) return null;
  const name = session.user.display_name;
  return (
    <PageShell width="default">
      <PageHeader
        title="Account & security"
        description="Your profile, password and signed-in devices."
      />
      <div className="grid gap-4 lg:grid-cols-[340px_minmax(0,1fr)]">
        <Card className="h-fit">
          <CardBody className="pt-5">
            <div className="flex items-center gap-3">
              <Avatar name={name} size="lg" />
              <div className="min-w-0">
                <p className="truncate text-[15px] font-semibold">{name}</p>
                <p className="truncate text-[13px] text-muted-foreground">
                  {session.user.email}
                </p>
              </div>
            </div>
            <PropertyList
              className="mt-4"
              items={[
                { label: "Workspace", value: session.tenant?.name ?? null },
                {
                  label: "Environment",
                  value: session.environment?.name ?? null,
                },
                ...(session.branch
                  ? [{ label: "Branch", value: session.branch.name }]
                  : []),
                {
                  label: "Roles",
                  value: session.roles.length ? (
                    <span className="flex flex-wrap justify-end gap-1">
                      {session.roles.map((r) => (
                        <Badge
                          key={r}
                          tone={r === "owner" ? "primary" : "neutral"}
                        >
                          {humanize(r)}
                        </Badge>
                      ))}
                    </span>
                  ) : null,
                },
              ]}
            />
            <p className="mt-3 text-xs text-muted-foreground">
              Roles are managed by a workspace administrator.
            </p>
          </CardBody>
        </Card>
        <div className="space-y-4">
          <ChangePasswordCard />
          <SignOutEverywhereCard />
        </div>
      </div>
    </PageShell>
  );
}

function ChangePasswordCard() {
  const form = useForm<PasswordValues>({
    resolver: zodResolver(passwordSchema),
    defaultValues: EMPTY,
  });
  const [serverError, setServerError] = useState<string | null>(null);
  const change = useScopedMutation(
    (v: PasswordValues) => authService.changePassword(v.current, v.next),
    { success: "Password changed" },
  );
  const e = form.formState.errors;
  const saving = change.isPending;
  const described = (name: keyof PasswordValues, help?: boolean) =>
    e[name] ? `pw-${name}-error` : help ? `pw-${name}-help` : undefined;

  return (
    <Card>
      <CardHeader
        title="Change password"
        description="Other devices stay signed in. Use “Sign out of all devices” if you think your password leaked."
        icon={<KeyRound />}
      />
      <CardBody>
        <form
          noValidate
          className="max-w-md space-y-4"
          onSubmit={form.handleSubmit(async (values) => {
            setServerError(null);
            try {
              await change.mutateAsync(values);
              form.reset(EMPTY);
            } catch (error) {
              const fields = error instanceof ApiError ? error.fields : {};
              if (fields.current_password)
                form.setError("current", {
                  type: "server",
                  message: fields.current_password,
                });
              if (fields.new_password)
                form.setError("next", {
                  type: "server",
                  message: fields.new_password,
                });
              if (!fields.current_password && !fields.new_password)
                setServerError(
                  errorMessage(error, "Your password could not be changed."),
                );
            }
          })}
        >
          <FormField
            label="Current password"
            htmlFor="pw-current"
            required
            error={e.current}
          >
            <Input
              id="pw-current"
              type="password"
              autoComplete="current-password"
              disabled={saving}
              aria-invalid={!!e.current || undefined}
              aria-describedby={described("current")}
              {...form.register("current")}
            />
          </FormField>
          <FormField
            label="New password"
            htmlFor="pw-next"
            required
            error={e.next}
            help="At least 12 characters. A short sentence is easy to remember and hard to guess."
          >
            <Input
              id="pw-next"
              type="password"
              autoComplete="new-password"
              disabled={saving}
              aria-invalid={!!e.next || undefined}
              aria-describedby={described("next", true)}
              {...form.register("next")}
            />
          </FormField>
          <FormField
            label="Confirm new password"
            htmlFor="pw-confirm"
            required
            error={e.confirm}
          >
            <Input
              id="pw-confirm"
              type="password"
              autoComplete="new-password"
              disabled={saving}
              aria-invalid={!!e.confirm || undefined}
              aria-describedby={described("confirm")}
              {...form.register("confirm")}
            />
          </FormField>
          {serverError && <InlineError message={serverError} />}
          <Button
            type="submit"
            loading={saving}
            disabled={!form.formState.isDirty}
          >
            Change password
          </Button>
        </form>
      </CardBody>
    </Card>
  );
}

function SignOutEverywhereCard() {
  const router = useRouter();
  const { logout } = useSession();
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function signOutEverywhere() {
    setPending(true);
    setError(null);
    try {
      await authService.logoutAll();
    } catch (err) {
      setPending(false);
      setError(
        errorMessage(err, "Couldn't sign out other devices. Please try again."),
      );
      return;
    }
    // This session ended too: clear local workspace data, then go to sign-in.
    await logout().catch(() => undefined);
    router.replace("/login");
  }

  return (
    <Card>
      <CardHeader
        title="Signed-in devices"
        description="End every session for your account, including this one."
        icon={<LogOut />}
      />
      <CardBody className="space-y-3">
        {error && <InlineError message={error} />}
        <Button variant="danger-outline" onClick={() => setOpen(true)}>
          <LogOut /> Sign out of all devices
        </Button>
      </CardBody>
      <ConfirmDialog
        open={open}
        onOpenChange={(next) => !pending && setOpen(next)}
        title="Sign out of all devices?"
        description="Use this if you lost a device or think someone else has your password."
        consequences={[
          "Every browser and device signed in to your account is signed out immediately, including this one.",
          "Unsaved work in open tabs is lost.",
          "You'll need your password to sign in again.",
        ]}
        confirmLabel="Sign out everywhere"
        destructive
        loading={pending}
        onConfirm={() => void signOutEverywhere()}
      />
    </Card>
  );
}
