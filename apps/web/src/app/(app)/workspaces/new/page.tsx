"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { PageShell, PageHeader } from "@/components/app/page";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/display";
import { authService } from "@/features/auth/service";
import { useSession } from "@/features/auth/session-provider";
import { errorMessage } from "@/services/api-client";
import { isDemo } from "@/lib/data-mode";

export default function NewWorkspace() {
  const [name, setName] = useState("");
  const [businessType, setType] = useState<
    "service_business" | "product_business" | "hybrid_business"
  >("service_business");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const { switchWorkspace } = useSession();
  const router = useRouter();
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const next = await authService.createWorkspace(name, businessType);
      await switchWorkspace(next.tenant!.id, next.environment!.id);
      router.push("/");
    } catch (e) {
      setError(errorMessage(e, "Could not create the workspace."));
    } finally {
      setBusy(false);
    }
  }
  return (
    <PageShell width="narrow">
      <PageHeader
        title="Create a workspace"
        description="Create a separate business workspace under your current account. You will be its owner."
      />
      <Card className="p-6">
        <form onSubmit={submit} className="space-y-5">
          <div>
            <label
              htmlFor="workspace-name"
              className="mb-2 block text-sm font-medium"
            >
              Workspace name
            </label>
            <Input
              id="workspace-name"
              required
              maxLength={160}
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
            />
          </div>
          <div>
            <label
              htmlFor="business-type"
              className="mb-2 block text-sm font-medium"
            >
              Business type
            </label>
            <select
              id="business-type"
              className="h-10 w-full rounded-md border border-border bg-background px-3 text-sm"
              value={businessType}
              onChange={(e) => setType(e.target.value as typeof businessType)}
            >
              <option value="service_business">Service business</option>
              <option value="product_business">Product business</option>
              <option value="hybrid_business">Services and products</option>
            </select>
          </div>
          <p className="text-sm text-muted-foreground">
            The workspace starts with an empty Production environment.
            Customers, offerings and business records stay separate from your
            other workspaces.
          </p>
          {isDemo && (
            <p className="text-sm text-warning">
              Workspace creation requires a live API connection.
            </p>
          )}
          {error && (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          )}
          <Button type="submit" disabled={busy || isDemo || !name.trim()}>
            {busy ? "Creating…" : "Create workspace"}
          </Button>
        </form>
      </Card>
    </PageShell>
  );
}
