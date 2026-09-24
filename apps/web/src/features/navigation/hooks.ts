"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { usePathname } from "next/navigation";
import { useSession } from "@/features/auth/session-provider";
import { navigationService } from "./service";
import type { NavItem, Navigation, SectionKey } from "./types";

export function useNavigationKey() {
  const { scopeKey, session } = useSession();
  // Navigation depends on permissions too (demo role switching, role changes).
  return [...scopeKey, "navigation", (session?.permissions ?? []).length, session?.roles.join(",")] as const;
}

export function useNavigation() {
  const { status } = useSession();
  return useQuery({
    queryKey: useNavigationKey(),
    queryFn: () => navigationService.get(),
    enabled: status === "ready",
    staleTime: 60_000,
  });
}

export function useNavOrderMutation() {
  const client = useQueryClient();
  const key = useNavigationKey();
  return useMutation({
    mutationFn: ({ section, order }: { section: SectionKey; order: string[] | null }) =>
      order ? navigationService.saveOrder(section, order) : navigationService.reset(section),
    onMutate: async ({ section, order }) => {
      await client.cancelQueries({ queryKey: key });
      const previous = client.getQueryData<Navigation>(key);
      if (previous && order) {
        client.setQueryData<Navigation>(key, {
          sections: previous.sections.map((s) =>
            s.key === section
              ? {
                  ...s,
                  customized: true,
                  items: order
                    .map((k) => s.items.find((i) => i.key === k))
                    .filter((i): i is NavItem => Boolean(i)),
                }
              : s,
          ),
        });
      }
      return { previous };
    },
    onError: (_error, _vars, context) => {
      if (context?.previous) client.setQueryData(key, context.previous);
    },
    onSuccess: (navigation) => client.setQueryData(key, navigation),
  });
}

function routeMatches(route: string, pathname: string) {
  if (route === "/") return pathname === "/";
  return pathname === route || pathname.startsWith(`${route}/`);
}

/** Deepest matching top-level item and child for the current URL. */
export function findActive(navigation: Navigation | undefined, pathname: string) {
  let best: { item: NavItem; child: NavItem | null; score: number } | null = null;
  for (const section of navigation?.sections ?? []) {
    for (const item of section.items) {
      if (routeMatches(item.route, pathname)) {
        const score = item.route.length;
        if (!best || score > best.score) best = { item, child: null, score };
      }
      for (const child of item.children) {
        if (routeMatches(child.route, pathname)) {
          const score = child.route.length + 0.5;
          if (!best || score > best.score) best = { item, child, score };
        }
      }
    }
  }
  return best;
}

export function useActiveNav() {
  const pathname = usePathname();
  const { data } = useNavigation();
  return findActive(data, pathname);
}
