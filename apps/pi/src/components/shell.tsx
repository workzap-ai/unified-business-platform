"use client";

import * as Menu from "@radix-ui/react-dropdown-menu";
import {
  Bot,
  ArrowUpRight,
  Check,
  ChevronRight,
  ChevronsUpDown,
  Home,
  Inbox,
  LogOut,
  Plus,
  Settings,
  Sparkles,
  Users,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import * as React from "react";

import { Wordmark } from "@/components/brand";
import { NotificationBell } from "@/features/journey";
import { Badge, Button, ErrorState, Spinner, cn } from "@/components/ui";
import { errorText } from "@/lib/api";
import { STATE_LABEL } from "@/lib/format";
import { useSession, useSignOut, useSwitchBusiness } from "@/lib/session";
import s from "./product.module.css";

const NAV = [
  { href: "/home", label: "Home", icon: Home },
  { href: "/inbox", label: "Inbox", icon: Inbox },
  { href: "/customers", label: "Customers", icon: Users },
  { href: "/my-pi", label: "My Pi", icon: Bot },
  { href: "/settings", label: "Settings", icon: Settings },
];

function useActive() {
  const pathname = usePathname();
  return (href: string) => pathname === href || pathname.startsWith(href + "/");
}

function BusinessMenu() {
  const { data } = useSession();
  const switcher = useSwitchBusiness();
  const signOut = useSignOut();
  const router = useRouter();
  if (!data?.business) return null;
  const state = STATE_LABEL[data.business.setup_state];
  return (
    <Menu.Root>
      <Menu.Trigger asChild>
        <button
          className="flex w-full min-w-0 items-center gap-3 rounded-lg px-2 py-2 text-start hover:bg-surface-muted"
          aria-label={`Business: ${data.business.name}. Switch business or sign out`}
        >
          <span className="flex size-9 shrink-0 items-center justify-center rounded-md bg-accent-soft text-sm font-semibold text-accent-soft-foreground">
            {data.business.name.slice(0, 1).toUpperCase()}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-semibold">
              {data.business.name}
            </span>
            <span className="block truncate text-xs text-muted-foreground">
              {data.business.environment === "test"
                ? "Test mode"
                : state?.label}
            </span>
          </span>
          <ChevronsUpDown
            className="size-4 shrink-0 text-muted-foreground"
            aria-hidden
          />
        </button>
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Content
          align="start"
          sideOffset={6}
          className="z-50 w-64 rounded-lg border border-border bg-surface p-1 shadow-md animate-fade-in"
        >
          <Menu.Label className="px-2 py-1.5 text-xs text-muted-foreground">
            {data.user.email}
          </Menu.Label>
          {data.businesses.map((business) => (
            <Menu.Item
              key={business.id}
              onSelect={() => {
                if (business.id !== data.business?.id) {
                  switcher.mutate(
                    { business_id: business.id },
                    { onSuccess: () => router.push("/home") },
                  );
                }
              }}
              className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-2 text-sm outline-none data-[highlighted]:bg-surface-muted"
            >
              <span className="flex-1 truncate">{business.name}</span>
              {business.id === data.business?.id ? (
                <Check className="size-4 text-accent" aria-hidden />
              ) : null}
            </Menu.Item>
          ))}
          <Menu.Item
            onSelect={() => router.push("/setup/new")}
            className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-2 text-sm outline-none data-[highlighted]:bg-surface-muted"
          >
            <Plus className="size-4" aria-hidden /> Add another business
          </Menu.Item>
          <Menu.Separator className="my-1 h-px bg-border" />
          <Menu.Item
            onSelect={() => signOut.mutate()}
            className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-2 text-sm outline-none data-[highlighted]:bg-surface-muted"
          >
            <LogOut className="size-4" aria-hidden /> Sign out
          </Menu.Item>
        </Menu.Content>
      </Menu.Portal>
    </Menu.Root>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const session = useSession();
  const router = useRouter();
  const pathname = usePathname();
  const active = useActive();

  React.useEffect(() => {
    if (session.data === null) {
      router.replace(`/sign-in?next=${encodeURIComponent(pathname)}`);
    } else if (
      session.data &&
      !session.data.business &&
      !pathname.startsWith("/setup/new")
    ) {
      router.replace("/setup/new");
    }
  }, [session.data, pathname, router]);

  if (session.isPending || session.data === null) {
    return (
      <div className="flex min-h-dvh items-center justify-center">
        <Spinner label="Opening Pi" />
      </div>
    );
  }
  if (session.isError) {
    return (
      <div className="mx-auto max-w-md p-6">
        <ErrorState
          message={errorText(session.error)}
          onRetry={() => session.refetch()}
        />
      </div>
    );
  }
  const business = session.data.business;
  const testMode = business?.environment === "test";

  return (
    <div className="flex min-h-dvh">
      <aside
        className={cn(
          "sticky top-0 hidden h-dvh shrink-0 flex-col border-e border-border md:flex",
          s.sidebar,
        )}
      >
        <Link href="/home" className={s.brand} aria-label="Pi home">
          <Wordmark />
          <span className={s.brandCaption}>
            YOUR BUSINESS
            <br />
            ASSISTANT
          </span>
        </Link>
        <div className={s.business}>
          <BusinessMenu />
        </div>
        <nav aria-label="Main" className={cn("space-y-1", s.nav)}>
          {NAV.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              aria-current={active(href) ? "page" : undefined}
              className={cn(
                "flex h-11 items-center gap-3 rounded-lg px-3 text-[15px] font-medium text-foreground-secondary transition-colors hover:bg-surface-muted hover:text-foreground",
                active(href) &&
                  "bg-accent-soft text-accent-soft-foreground hover:bg-accent-soft",
              )}
            >
              <Icon className="size-5" aria-hidden />
              {label}
            </Link>
          ))}
        </nav>
        {business && business.setup_state !== "active" ? (
          <div className="mt-auto rounded-lg border border-border bg-surface-muted p-3 text-sm">
            <Badge tone={STATE_LABEL[business.setup_state]?.tone}>
              {STATE_LABEL[business.setup_state]?.label}
            </Badge>
            <p className="mt-2 text-muted-foreground">
              Pi isn&apos;t replying to customers yet.
            </p>
            <Button
              asChild
              size="sm"
              variant="secondary"
              className="mt-3 w-full"
            >
              <Link href="/setup">Continue setup</Link>
            </Button>
          </div>
        ) : null}
        {business?.setup_state === "active" ? (
          <div className={s.sidebarNote}>
            <Sparkles size={18} aria-hidden />
            <h2>A little more you.</h2>
            <p>
              Give Pi the knowledge and personality that make your business
              yours.
            </p>
            <Link href="/my-pi">
              Personalize your Pi
              <ArrowUpRight size={15} aria-hidden />
            </Link>
          </div>
        ) : null}
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <div className={s.topbar}>
          <div className={s.crumb}>
            <span>Workspace</span>
            <ChevronRight size={12} aria-hidden />
            <strong>
              {pathname.startsWith("/setup")
                ? "Getting started"
                : pathname.startsWith("/notifications")
                  ? "Notifications"
                  : (NAV.find((item) => active(item.href))?.label ?? "Pi")}
            </strong>
          </div>
          <div className="flex items-center gap-2">
            <NotificationBell />
            <Link href="/my-pi/test" className={s.tryLink}>
              <Sparkles size={14} aria-hidden />
              Try your Pi
              <ArrowUpRight size={13} aria-hidden />
            </Link>
          </div>
        </div>
        <header className="sticky top-0 z-30 flex items-center gap-2 border-b border-border bg-surface/95 px-3 py-2 backdrop-blur md:hidden">
          <div className="min-w-0 flex-1">
            <BusinessMenu />
          </div>
          <NotificationBell />
        </header>
        {testMode ? (
          <div
            className="bg-warning-soft px-4 py-2 text-center text-sm text-warning"
            role="status"
          >
            Test mode: messages and numbers here are separate from your live
            business.
          </div>
        ) : null}
        <main
          id="main"
          className="mx-auto w-full max-w-6xl flex-1 px-4 pb-28 pt-6 sm:px-6 md:pb-10"
        >
          {children}
        </main>
        <nav
          aria-label="Main"
          className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t border-border bg-surface pb-[env(safe-area-inset-bottom)] md:hidden"
        >
          {NAV.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              aria-current={active(href) ? "page" : undefined}
              className={cn(
                "flex min-h-14 flex-col items-center justify-center gap-0.5 text-[11px] font-medium text-muted-foreground",
                active(href) && "text-accent",
              )}
            >
              <Icon className="size-5" aria-hidden />
              {label}
            </Link>
          ))}
        </nav>
      </div>
    </div>
  );
}

export function SubNav({
  items,
}: {
  items: { href: string; label: string }[];
}) {
  const active = useActive();
  return (
    <nav
      aria-label="Section"
      className={cn("-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0", s.sectionNav)}
    >
      <div className="flex w-max gap-1 rounded-lg border border-border bg-surface p-1">
        {items.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active(item.href) ? "page" : undefined}
            className={cn(
              "flex h-9 items-center whitespace-nowrap rounded-md px-3 text-sm font-medium text-foreground-secondary hover:text-foreground",
              active(item.href) && "bg-accent-soft text-accent-soft-foreground",
            )}
          >
            {item.label}
          </Link>
        ))}
      </div>
    </nav>
  );
}
