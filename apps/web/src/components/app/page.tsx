"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { useSession } from "@/features/auth/session-provider";
import { useNavigation } from "@/features/navigation/hooks";
import { NavIcon } from "@/features/navigation/icons";

/**
 * Page composition primitives. Typical page:
 *   <PageShell><PageHeader/><FilterBar/><DataTable/></PageShell>
 * or for records:
 *   <PageShell><RecordHeader/><Tabs/>…</PageShell>
 */
export function PageShell({
  children,
  className,
  width = "wide",
}: {
  children: React.ReactNode;
  className?: string;
  width?: "narrow" | "default" | "wide" | "full";
}) {
  const widths = {
    narrow: "max-w-3xl",
    default: "max-w-5xl",
    wide: "max-w-[1400px]",
    full: "max-w-none",
  };
  return (
    <div className={cn("mx-auto w-full px-4 py-5 sm:px-6 lg:px-8 lg:py-6", widths[width], className)}>
      {children}
    </div>
  );
}

export function PageHeader({
  title,
  description,
  actions,
  eyebrow,
  className,
  children,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  eyebrow?: React.ReactNode;
  className?: string;
  children?: React.ReactNode;
}) {
  return (
    <header className={cn("mb-5", className)}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          {eyebrow && (
            <div className="mb-1 text-xs font-medium text-muted-foreground">{eyebrow}</div>
          )}
          <h1 className="text-xl font-semibold tracking-tight text-foreground sm:text-[22px]">
            {title}
          </h1>
          {description && (
            <p className="mt-1 max-w-2xl text-[13.5px] text-muted-foreground">{description}</p>
          )}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {children}
    </header>
  );
}

export function SectionHeader({
  title,
  description,
  actions,
  className,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("mb-3 flex items-end justify-between gap-3", className)}>
      <div className="min-w-0">
        <h2 className="text-[15px] font-semibold tracking-tight">{title}</h2>
        {description && <p className="mt-0.5 text-[13px] text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}

/**
 * Module workspace tabs rendered from the navigation registry's child pages, so a
 * module's sub-navigation is registered once and also powers search and breadcrumbs.
 */
export function ModuleNav({ moduleKey, className }: { moduleKey: string; className?: string }) {
  const { data } = useNavigation();
  const pathname = usePathname();
  const module = data?.sections.flatMap((s) => s.items).find((i) => i.key === moduleKey);
  const children = module?.children ?? [];
  if (children.length < 2) return null;
  const activeRoute = children
    .filter((c) => pathname === c.route || pathname.startsWith(`${c.route}/`))
    .sort((a, b) => b.route.length - a.route.length)[0]?.route;
  return (
    <nav
      aria-label={`${module?.label ?? "Module"} sections`}
      className={cn("scrollbar-thin -mx-4 mb-5 overflow-x-auto border-b border-border px-4 sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8", className)}
    >
      <ul className="flex min-w-max items-center gap-1">
        {children.map((child) => {
          const active = child.route === activeRoute;
          return (
            <li key={child.key}>
              <Link
                href={child.route}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "relative -mb-px flex h-9 items-center gap-1.5 border-b-2 px-2.5 text-[13px] font-medium transition-colors",
                  active
                    ? "border-primary text-foreground"
                    : "border-transparent text-muted-foreground hover:text-foreground",
                )}
              >
                <NavIcon name={child.icon} className="size-3.5" />
                {child.label}
                {child.badge ? (
                  <span className="tabular rounded-full bg-pi-soft px-1.5 text-[10.5px] leading-4 font-semibold text-pi-soft-foreground">
                    {child.badge}
                  </span>
                ) : null}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

/** Renders children only for members holding the permission, else an explanation. */
export function RequirePermission({
  permission,
  children,
  area,
}: {
  permission: string | string[];
  children: React.ReactNode;
  area?: string;
}) {
  const { can, canAny } = useSession();
  const ok = Array.isArray(permission) ? canAny(...permission) : can(permission);
  if (ok) return <>{children}</>;
  return (
    <PageShell width="narrow">
      <div className="mt-10 rounded-xl border border-border bg-surface p-8 text-center shadow-sm">
        <div className="mx-auto flex size-10 items-center justify-center rounded-full bg-surface-muted">
          <NavIcon name="shield-check" className="size-5 text-muted-foreground" />
        </div>
        <h1 className="mt-4 text-base font-semibold">You don't have access to {area ?? "this area"}</h1>
        <p className="mt-1.5 text-sm text-muted-foreground">
          Your role doesn't include this permission. Ask a workspace administrator if you need
          access.
        </p>
        <Link href="/" className="mt-5 inline-block text-sm font-medium text-primary hover:underline">
          Back to overview
        </Link>
      </div>
    </PageShell>
  );
}
