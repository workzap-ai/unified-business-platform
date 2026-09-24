"use client";

import { createContext, useContext, useEffect, useState } from "react";
import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { useSession } from "@/features/auth/session-provider";
import { useActiveNav } from "@/features/navigation/hooks";
import { pushRecent } from "@/lib/recent";

type Crumb = { label: string; href?: string };
const Context = createContext<{
  record: Crumb[];
  setRecord: (c: Crumb[]) => void;
}>({
  record: [],
  setRecord: () => {},
});

export function BreadcrumbProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [record, setRecord] = useState<Crumb[]>([]);
  return (
    <Context.Provider value={{ record, setRecord }}>
      {children}
    </Context.Provider>
  );
}

/**
 * Pages add record-level crumbs (e.g. a customer's name). Section/page crumbs come from
 * the navigation registry, so there is no second route list to maintain.
 * Passing `recent` also records the page in the command menu's recent items.
 */
export function useBreadcrumbs(
  crumbs: Crumb[],
  recent?: { href: string; kind: string },
) {
  const { setRecord } = useContext(Context);
  const { scopeKey } = useSession();
  const serialized = JSON.stringify(crumbs);
  useEffect(() => {
    const parsed = JSON.parse(serialized) as Crumb[];
    setRecord(parsed);
    const last = parsed[parsed.length - 1];
    if (recent && last)
      pushRecent(scopeKey.join(":"), {
        href: recent.href,
        kind: recent.kind,
        title: last.label,
      });
    return () => setRecord([]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serialized, setRecord]);
}

export function Breadcrumbs() {
  const active = useActiveNav();
  const { record } = useContext(Context);
  if (!active) return null;
  const trail: Crumb[] = [
    { label: active.item.label, href: active.item.route },
  ];
  if (active.child && active.child.route !== active.item.route) {
    trail.push({ label: active.child.label, href: active.child.route });
  }
  trail.push(...record);
  return (
    <nav aria-label="Breadcrumb" className="min-w-0">
      <ol className="flex min-w-0 items-center gap-1 text-[13px]">
        {trail.map((crumb, index) => {
          const last = index === trail.length - 1;
          return (
            <li
              key={`${crumb.label}-${index}`}
              className={
                last
                  ? "min-w-0 truncate"
                  : "hidden shrink-0 items-center gap-1 sm:flex"
              }
            >
              {last || !crumb.href ? (
                <span
                  aria-current={last ? "page" : undefined}
                  className="truncate font-medium text-foreground"
                >
                  {crumb.label}
                </span>
              ) : (
                <>
                  <Link
                    href={crumb.href}
                    className="text-muted-foreground hover:text-foreground"
                  >
                    {crumb.label}
                  </Link>
                  <ChevronRight
                    className="size-3.5 text-border-strong"
                    aria-hidden="true"
                  />
                </>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
