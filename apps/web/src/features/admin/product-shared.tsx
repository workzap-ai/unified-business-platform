"use client";

import { useState } from "react";
import { Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/controls";
import { ConfirmDialog } from "@/components/app/forms";
import { StatusBadge } from "@/components/app/status-badge";
import { useScopedMutation } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import {
  productsService,
  type ProductState,
} from "@/features/products/service";

/** Product toggles change navigation and module access, so refresh those too. */
const INVALIDATE = [["products"], ["navigation"], ["overview"]];

export function InstallStatus({ product }: { product: ProductState }) {
  if (!product.tenant_status)
    return <StatusBadge status="draft" label="Not installed" />;
  return <StatusBadge status={product.tenant_status} />;
}

export function EnvironmentSwitch({
  product,
  id,
}: {
  product: ProductState;
  id: string;
}) {
  const { session } = useSession();
  const toggle = useScopedMutation(
    (enabled: boolean) => productsService.setEnabled(product.key, enabled),
    {
      invalidate: INVALIDATE,
      success: (list) =>
        `${product.name} ${list.find((p) => p.key === product.key)?.environment_enabled ? "enabled" : "disabled"} in ${session?.environment?.name ?? "this environment"}`,
    },
  );
  const installed = product.tenant_status === "installed";
  return (
    <div className="flex items-center justify-between gap-3">
      <label htmlFor={id} className="min-w-0 text-[13px]">
        <span className="block font-medium">
          Enabled in {session?.environment?.name ?? "this environment"}
        </span>
        <span className="block text-xs text-muted-foreground">
          {!product.tenant_status
            ? "Install the product first."
            : product.tenant_status === "suspended"
              ? "Suspended for this workspace."
              : product.environment_enabled
                ? "Available to members in this environment."
                : "Hidden and inactive in this environment."}
        </span>
      </label>
      <Switch
        id={id}
        checked={product.environment_enabled}
        disabled={!installed || toggle.isPending}
        onCheckedChange={(checked) => toggle.mutate(checked)}
        aria-label={`Enable ${product.name} in this environment`}
      />
    </div>
  );
}

export function InstallButton({
  product,
  size = "sm",
}: {
  product: ProductState;
  size?: "sm" | "default";
}) {
  const [open, setOpen] = useState(false);
  const { session } = useSession();
  const install = useScopedMutation(
    () => productsService.install(product.key),
    {
      invalidate: INVALIDATE,
      success: `${product.name} installed`,
      onSuccess: () => setOpen(false),
    },
  );
  if (product.tenant_status) return null;
  return (
    <>
      <Button size={size} onClick={() => setOpen(true)}>
        <Download /> Install
      </Button>
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title={`Install ${product.name}?`}
        description={product.description}
        consequences={[
          `${product.name} is added to ${session?.tenant?.name ?? "this workspace"} and enabled in ${session?.environment?.name ?? "the current environment"}.`,
          "Its pages appear in the sidebar for members whose roles include its permissions.",
          "Other environments stay unchanged until you enable it there.",
          "You can disable it per environment at any time; data it creates is kept.",
        ]}
        confirmLabel={`Install ${product.name}`}
        loading={install.isPending}
        onConfirm={() => install.mutate(undefined)}
      />
    </>
  );
}
