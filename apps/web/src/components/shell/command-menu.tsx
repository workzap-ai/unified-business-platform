"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { useRouter } from "next/navigation";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { Command } from "cmdk";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  Clock,
  CornerDownLeft,
  LogOut,
  Moon,
  Search,
  Sun,
} from "lucide-react";
import { Kbd } from "@/components/ui/controls";
import { Spinner } from "@/components/ui/display";
import { useSession } from "@/features/auth/session-provider";
import { MODULE_MANIFESTS } from "@/features/modules/manifests";
import { useNavigation } from "@/features/navigation/hooks";
import { NavIcon } from "@/features/navigation/icons";
import { readRecent } from "@/lib/recent";
import { useTheme } from "./theme";

type CommandMenuContext = { open: () => void };
const Context = createContext<CommandMenuContext>({ open: () => {} });
export const useCommandMenu = () => useContext(Context);

function useDebounced<T>(value: T, delay = 200) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

export function CommandMenuProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const show = useCallback(() => setOpen(true), []);
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((v) => !v);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return (
    <Context.Provider value={{ open: show }}>
      {children}
      <DialogPrimitive.Root open={open} onOpenChange={setOpen}>
        <DialogPrimitive.Portal>
          <DialogPrimitive.Overlay className="fixed inset-0 z-50 animate-fade-in bg-[rgb(8_16_13/0.45)]" />
          <DialogPrimitive.Content
            className="fixed top-[12vh] left-1/2 z-50 w-[calc(100vw-1.5rem)] max-w-xl -translate-x-1/2 animate-scale-in overflow-hidden rounded-xl border border-border bg-surface shadow-lg outline-none"
            aria-describedby={undefined}
          >
            <DialogPrimitive.Title className="sr-only">
              Search and commands
            </DialogPrimitive.Title>
            {open && <CommandPalette onDone={() => setOpen(false)} />}
          </DialogPrimitive.Content>
        </DialogPrimitive.Portal>
      </DialogPrimitive.Root>
    </Context.Provider>
  );
}

function CommandPalette({ onDone }: { onDone: () => void }) {
  const router = useRouter();
  const { can, scopeKey, logout } = useSession();
  const { theme, setTheme } = useTheme();
  const navigation = useNavigation();
  const [query, setQuery] = useState("");
  const term = useDebounced(query.trim());
  const scope = scopeKey.join(":");

  const providers = useMemo(
    () =>
      MODULE_MANIFESTS.flatMap((m) =>
        m.search && can(m.search.permission) ? [m.search] : [],
      ),
    [can],
  );
  const records = useQuery({
    queryKey: [...scopeKey, "command-search", term],
    queryFn: async () => {
      const results = await Promise.allSettled(
        providers.map((p) => p.search(term)),
      );
      return providers.map((provider, i) => ({
        provider,
        results:
          results[i]?.status === "fulfilled"
            ? results[i].value.slice(0, 5)
            : [],
      }));
    },
    enabled: term.length >= 2,
    staleTime: 30_000,
  });

  const go = (href: string) => {
    onDone();
    router.push(href);
  };

  const pages = (navigation.data?.sections ?? []).flatMap((section) =>
    section.items.flatMap((item) => [
      {
        key: item.key,
        label: item.label,
        route: item.route,
        icon: item.icon,
        parent: null as string | null,
        keywords: item.keywords,
      },
      ...item.children
        .filter((c) => c.route !== item.route)
        .map((c) => ({
          key: c.key,
          label: c.label,
          route: c.route,
          icon: c.icon,
          parent: item.label,
          keywords: c.keywords,
        })),
    ]),
  );
  const actions = MODULE_MANIFESTS.flatMap((m) => m.actions ?? []).filter(
    (a) => !a.permission || can(a.permission),
  );
  const recent = typeof window === "undefined" ? [] : readRecent(scope);

  const item =
    "flex cursor-pointer items-center gap-2.5 rounded-md px-2.5 py-2 text-[13.5px] text-foreground aria-selected:bg-surface-muted [&_svg]:size-4 [&_svg]:shrink-0 [&_svg]:text-muted-foreground";
  const group =
    "px-1.5 pb-1 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:pt-2.5 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:text-2xs [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:tracking-wide [&_[cmdk-group-heading]]:text-muted-foreground [&_[cmdk-group-heading]]:uppercase";

  return (
    <Command label="Search and commands" loop shouldFilter>
      <div className="flex items-center gap-2 border-b border-border px-3.5">
        <Search className="size-4 text-muted-foreground" aria-hidden="true" />
        <Command.Input
          value={query}
          onValueChange={setQuery}
          placeholder="Search pages, records and actions…"
          className="h-12 flex-1 bg-transparent text-[15px] outline-none placeholder:text-muted-foreground"
        />
        {records.isFetching && <Spinner />}
        <Kbd>Esc</Kbd>
      </div>
      <Command.List className="scrollbar-thin max-h-[min(60vh,440px)] overflow-y-auto py-1">
        <Command.Empty className="px-4 py-10 text-center text-sm text-muted-foreground">
          {term.length >= 2 && records.isFetching
            ? "Searching…"
            : "No matches. Try a customer, SKU or order number."}
        </Command.Empty>

        {query.length === 0 && recent.length > 0 && (
          <Command.Group heading="Recent" className={group}>
            {recent.map((r) => (
              <Command.Item
                key={r.href}
                value={`recent ${r.title} ${r.kind}`}
                onSelect={() => go(r.href)}
                className={item}
              >
                <Clock />
                <span className="flex-1 truncate">{r.title}</span>
                <span className="text-xs text-muted-foreground">{r.kind}</span>
              </Command.Item>
            ))}
          </Command.Group>
        )}

        {(records.data ?? []).map(({ provider, results }) =>
          results.length ? (
            <Command.Group
              key={provider.key}
              heading={provider.label}
              className={group}
              forceMount
            >
              {results.map((r) => (
                <Command.Item
                  key={r.id}
                  value={`${provider.key} ${r.title} ${r.subtitle ?? ""} ${term}`}
                  onSelect={() => go(r.href)}
                  className={item}
                >
                  <provider.icon />
                  <span className="min-w-0 flex-1 truncate">{r.title}</span>
                  {r.subtitle && (
                    <span className="max-w-40 truncate text-xs text-muted-foreground">
                      {r.subtitle}
                    </span>
                  )}
                </Command.Item>
              ))}
            </Command.Group>
          ) : null,
        )}

        {actions.length > 0 && (
          <Command.Group heading="Actions" className={group}>
            {actions.map((a) => (
              <Command.Item
                key={a.id}
                value={`action ${a.label} ${(a.keywords ?? []).join(" ")}`}
                onSelect={() => go(a.href)}
                className={item}
              >
                <a.icon />
                <span className="flex-1">{a.label}</span>
                <CornerDownLeft className="!size-3.5 opacity-0 [[aria-selected=true]_&]:opacity-100" />
              </Command.Item>
            ))}
          </Command.Group>
        )}

        <Command.Group heading="Go to" className={group}>
          {pages.map((p) => (
            <Command.Item
              key={p.key}
              value={`page ${p.parent ?? ""} ${p.label} ${p.keywords.join(" ")}`}
              onSelect={() => go(p.route)}
              className={item}
            >
              <NavIcon name={p.icon} />
              <span className="flex-1">
                {p.parent && (
                  <span className="text-muted-foreground">{p.parent} / </span>
                )}
                {p.label}
              </span>
              <ArrowRight className="!size-3.5 opacity-0 [[aria-selected=true]_&]:opacity-100" />
            </Command.Item>
          ))}
        </Command.Group>

        <Command.Group heading="Preferences" className={group}>
          <Command.Item
            value="theme toggle dark light appearance"
            onSelect={() => {
              setTheme(theme === "dark" ? "light" : "dark");
              onDone();
            }}
            className={item}
          >
            {theme === "dark" ? <Sun /> : <Moon />}
            Switch to {theme === "dark" ? "light" : "dark"} theme
          </Command.Item>
          <Command.Item
            value="sign out log out"
            onSelect={() => {
              onDone();
              void logout().then(() => router.push("/login"));
            }}
            className={item}
          >
            <LogOut />
            Sign out
          </Command.Item>
        </Command.Group>
      </Command.List>
      <div className="flex items-center gap-3 border-t border-border bg-surface-muted/60 px-3.5 py-2 text-2xs text-muted-foreground">
        <span className="flex items-center gap-1">
          <Kbd>↑</Kbd>
          <Kbd>↓</Kbd> navigate
        </span>
        <span className="flex items-center gap-1">
          <Kbd>↵</Kbd> open
        </span>
        <span className="ml-auto">Type 2+ characters to search records</span>
      </div>
    </Command>
  );
}
