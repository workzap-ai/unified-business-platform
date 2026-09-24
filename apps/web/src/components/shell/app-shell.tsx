"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import { usePathname, useRouter } from "next/navigation";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { FlaskConical, Menu } from "lucide-react";
import { cn } from "@/lib/utils";
import { isDemo } from "@/lib/data-mode";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/display";
import { SheetContent, Tooltip } from "@/components/ui/overlays";
import { useLocalStorageState } from "@/hooks/use-local-storage";
import { useSession } from "@/features/auth/session-provider";
import { Breadcrumbs, BreadcrumbProvider } from "./breadcrumbs";
import { CommandMenuProvider } from "./command-menu";
import { NotificationCenter } from "./notification-center";
import { Sidebar } from "./sidebar";
import { QuickCreate, UserMenu } from "./user-menu";
import { EnvironmentSwitcher } from "./workspace-switcher";

const COLLAPSE_KEY = "platform.sidebar.collapsed";

function useMediaQuery(query: string) {
  return useSyncExternalStore(
    (notify) => {
      const list = window.matchMedia(query);
      list.addEventListener("change", notify);
      return () => list.removeEventListener("change", notify);
    },
    () => window.matchMedia(query).matches,
    () => true,
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { status, session, retry } = useSession();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (status === "anonymous") {
      router.replace(
        `/login${pathname && pathname !== "/" ? `?next=${encodeURIComponent(pathname)}` : ""}`,
      );
    }
  }, [status, router, pathname]);

  if (status === "loading" || status === "anonymous") return <ShellSkeleton />;
  if (status === "error") {
    return (
      <div className="flex min-h-dvh items-center justify-center p-6">
        <div className="max-w-sm text-center">
          <h1 className="text-lg font-semibold">
            We couldn’t reach your workspace
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            The service may be restarting or your connection dropped. Your data
            is safe.
          </p>
          <Button className="mt-5" onClick={retry}>
            Try again
          </Button>
        </div>
      </div>
    );
  }
  if (!session?.tenant) return <NoWorkspace />;
  return (
    <CommandMenuProvider>
      <BreadcrumbProvider>
        <ShellFrame>{children}</ShellFrame>
      </BreadcrumbProvider>
    </CommandMenuProvider>
  );
}

function ShellFrame({ children }: { children: React.ReactNode }) {
  const wide = useMediaQuery("(min-width: 1024px)");
  const tablet = useMediaQuery("(min-width: 768px)");
  const [userCollapsed, setUserCollapsed] = useLocalStorageState<boolean>(
    COLLAPSE_KEY,
    false,
  );
  // The mobile drawer closes through the sidebar's onNavigate when a link is chosen.
  const [mobileOpen, setMobileOpen] = useState(false);

  const collapsed = !wide || Boolean(userCollapsed);
  const toggle = () => setUserCollapsed((current) => !current);

  return (
    <div className="flex min-h-dvh">
      <a
        href="#main"
        className="sr-only z-[80] rounded-md bg-surface px-3 py-2 shadow-md focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
      >
        Skip to content
      </a>
      {tablet && (
        <aside
          className={cn(
            "sticky top-0 h-dvh shrink-0 border-r border-sidebar-border transition-[width] duration-200",
            collapsed ? "w-[60px]" : "w-[248px]",
          )}
          aria-label="Sidebar"
        >
          <Sidebar
            collapsed={collapsed}
            onToggleCollapsed={wide ? toggle : undefined}
          />
        </aside>
      )}
      <DialogPrimitive.Root open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent
          side="left"
          width="sm"
          className="w-[86vw] max-w-[300px] border-sidebar-border bg-sidebar p-0 [&>button]:text-sidebar-muted"
        >
          <DialogPrimitive.Title className="sr-only">
            Navigation
          </DialogPrimitive.Title>
          <DialogPrimitive.Description className="sr-only">
            Main and admin navigation
          </DialogPrimitive.Description>
          <Sidebar variant="mobile" onNavigate={() => setMobileOpen(false)} />
        </SheetContent>
      </DialogPrimitive.Root>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-13 shrink-0 items-center gap-2 border-b border-border bg-surface/95 px-3 backdrop-blur supports-[backdrop-filter]:bg-surface/85 sm:px-5">
          {!tablet && (
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => setMobileOpen(true)}
              aria-label="Open navigation"
            >
              <Menu />
            </Button>
          )}
          <div className="min-w-0 flex-1">
            <Breadcrumbs />
          </div>
          <div className="flex shrink-0 items-center gap-1.5 sm:gap-2">
            {isDemo && (
              <Tooltip content="You're viewing fictional sample data. Nothing here is real business data, and changes reset when the page reloads.">
                <span className="hidden items-center gap-1 rounded-full border border-dashed border-pi/50 px-2 py-0.5 text-2xs font-semibold text-pi md:inline-flex">
                  <FlaskConical className="size-3" aria-hidden="true" /> Sample
                  data
                </span>
              </Tooltip>
            )}
            <EnvironmentSwitcher />
            <QuickCreate />
            <NotificationCenter />
            <UserMenu />
          </div>
        </header>
        <main id="main" className="min-w-0 flex-1" tabIndex={-1}>
          {children}
        </main>
      </div>
    </div>
  );
}

function ShellSkeleton() {
  return (
    <div
      className="flex min-h-dvh"
      aria-busy="true"
      aria-label="Loading workspace"
    >
      <div className="hidden w-[248px] shrink-0 bg-sidebar p-3 md:block">
        <div className="flex items-center gap-2.5 p-1.5">
          <Skeleton className="size-8 bg-sidebar-hover" />
          <Skeleton className="h-3 w-28 bg-sidebar-hover" />
        </div>
        <div className="mt-6 space-y-2.5 px-2">
          {Array.from({ length: 11 }, (_, i) => (
            <Skeleton
              key={i}
              className="h-3.5 bg-sidebar-hover"
              style={{ width: `${55 + ((i * 17) % 35)}%` }}
            />
          ))}
        </div>
      </div>
      <div className="flex-1">
        <div className="h-13 border-b border-border bg-surface" />
        <div className="space-y-4 p-6">
          <Skeleton className="h-7 w-56" />
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} className="h-24" />
            ))}
          </div>
          <Skeleton className="h-72" />
        </div>
      </div>
    </div>
  );
}

function NoWorkspace() {
  const { logout } = useSession();
  const router = useRouter();
  return (
    <div className="flex min-h-dvh items-center justify-center p-6">
      <div className="max-w-md rounded-xl border border-border bg-surface p-8 text-center shadow-sm">
        <h1 className="text-lg font-semibold">No workspace yet</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Your account isn’t a member of any active workspace. Ask an
          administrator to invite you, or create a new workspace.
        </p>
        <div className="mt-6 flex justify-center gap-2">
          <Button
            variant="secondary"
            onClick={() => void logout().then(() => router.push("/login"))}
          >
            Sign out
          </Button>
          <Button onClick={() => router.push("/register")}>
            Create workspace
          </Button>
        </div>
      </div>
    </div>
  );
}
