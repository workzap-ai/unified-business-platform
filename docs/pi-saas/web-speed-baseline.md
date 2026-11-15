# Owner OS web: speed baseline (measured 2026-11-16)

Measured from `next build` (Next 16.4.2, Turbopack) of main `b0cfb7c8`, `apps/web`. Not a browser trace: no
Lighthouse numbers exist yet (they need the web app running against the disposable stack).

- 134 pages, 175 JavaScript chunks, about 5.8 MB raw and 1.84 MB gzipped in total across all routes. Turbopack already
  splits per route, so no single route loads that much.
- The largest chunk (385 KB raw, 109 KB gzipped) is the charts library. It is NOT in the root layout's first-load
  files; `components/app/charts.tsx` already loads it with `next/dynamic`.
- Query defaults already set `refetchOnWindowFocus: false` (only the session query turns it on) and 30 s `staleTime`.
- `(app)/layout.tsx` already wraps the page in `Suspense` with `PageSkeleton`; the shell shows `ShellSkeleton` until the
  session answers.

What the code reading predicted but the measurement did not support: "heavy libraries are not lazy-loaded" (charts are).

What stays true and still costs time: the browser fetches `/auth/session` only after the page's JavaScript has hydrated,
and every page's data query key depends on that answer, so first data waits for HTML, then JS, then the session, then the
page's own request.

Decisions taken from this:

- **No global `placeholderData: keepPreviousData`.** Workspace queries are keyed by tenant and environment; keeping the
  previous result across a key change would show the previous workspace's data for a moment after a workspace switch.
  Use it per query where the key only changes by filter or page (21 files already do).
- **Session in `sessionStorage` as a first paint** is the next candidate (render the shell at once with the last
  session, revalidate immediately, purge workspace data if the answer differs). It touches sign-in, so it is not done
  without a browser test against the local stack.
- Done: `(app)/error.tsx`, so a crash in one page keeps the sidebar and header.
