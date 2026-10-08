"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  ChevronRight,
  Copy,
  Inbox,
  Languages,
  Link2,
  LogOut,
  MessageCircle,
  Search,
  Trash2,
} from "lucide-react";

import { errorText } from "@/lib/api";
import {
  customerDelete,
  customerGet,
  customerPost,
  customerPut,
  type CustomerConversationItem,
  type CustomerIssue,
  type CustomerMe,
  type CustomerPrefs,
  type CustomerShareLink,
  type IssueLink,
} from "@/lib/customer-api";
import { cn } from "@/lib/cn";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  Skeleton,
} from "@/components/ui";
import { CustomerSecurityCard } from "./security";
import { JourneyRoad, PriorityChart, ProblemMap } from "./visuals";
import {
  Avatar,
  LIST,
  ME,
  PREFS,
  TURN,
  ago,
  journeyPercent,
  nextStepLine,
  shortDay,
  turnOf,
  useLang,
  usePrefs,
  type Turn,
} from "./shared";

type Filter = "all" | Turn;
type Row = CustomerIssue & { conversation: CustomerConversationItem };

const FILTERS: { key: Filter; en: string; ur: string }[] = [
  { key: "all", en: "All", ur: "Sab" },
  { key: "you", en: TURN.you.en, ur: TURN.you.ur },
  { key: "us", en: TURN.us.en, ur: TURN.us.ur },
  { key: "other", en: TURN.other.en, ur: TURN.other.ur },
  { key: "done", en: TURN.done.en, ur: TURN.done.ur },
];

const ORDER: Record<Turn, number> = { you: 0, us: 1, other: 2, done: 3 };

export function Dashboard({ me }: { me: CustomerMe }) {
  const client = useQueryClient();
  const lang = useLang();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const list = useQuery({
    queryKey: LIST,
    queryFn: () => customerGet<CustomerConversationItem[]>("/conversations"),
    refetchInterval: 20_000,
  });
  const signOut = useMutation({
    mutationFn: () => customerPost("/sign-out"),
    onSettled: () => {
      client.setQueryData(ME, null);
      client.removeQueries({ queryKey: ["pi-customer"] });
    },
  });
  useCatchUp(list.data);
  useMarkSeen();
  useLiveUpdates();
  const router = useRouter();

  const items = useMemo(() => list.data ?? [], [list.data]);
  // Every request across every chat: all numbers on this page count these.
  const rows: Row[] = useMemo(
    () =>
      items
        .flatMap((c) => c.issues.map((i) => ({ ...i, conversation: c })))
        .sort((a, b) => ORDER[turnOf(a)] - ORDER[turnOf(b)]),
    [items],
  );
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return rows.filter(
      (r) =>
        (filter === "all" || turnOf(r) === filter) &&
        (!q ||
          r.title.toLowerCase().includes(q) ||
          r.conversation.business.toLowerCase().includes(q)),
    );
  }, [rows, query, filter]);
  const reading = items.some((c) => !c.issues_fresh);
  const links: (IssueLink & { conversation: string })[] = useMemo(
    () =>
      items.flatMap((c) =>
        (c.links ?? []).map((l) => ({ ...l, conversation: c.id })),
      ),
    [items],
  );
  const notRelated = useMutation({
    mutationFn: (link: IssueLink & { conversation: string }) =>
      customerPost(`/conversations/${link.conversation}/links/not-related`, {
        a_title: link.a_title,
        b_title: link.b_title,
      }),
    onSuccess: () =>
      void client.invalidateQueries({ queryKey: ["pi-customer"] }),
  });

  return (
    <div className="mx-auto w-full max-w-6xl space-y-5 sm:space-y-6">
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm text-muted-foreground">
            {lang === "ur" ? "Sign in: " : "Signed in as "}
            <span className="font-medium">{me.phone}</span>
          </p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
            {lang === "ur" ? "Aap ke requests" : "Your requests"}
          </h1>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <LanguagePicker />
          <Button
            variant="secondary"
            size="sm"
            className="min-h-11 sm:min-h-10"
            aria-label="Sign out"
            onClick={() => signOut.mutate()}
            loading={signOut.isPending}
          >
            <LogOut className="size-4" aria-hidden />
            <span className="hidden sm:inline">Sign out</span>
          </Button>
        </div>
      </header>

      {list.isPending ? (
        <div className="space-y-3" role="status" aria-label="Loading">
          <Skeleton className="h-24 w-full rounded-2xl" />
          <Skeleton className="h-32 w-full rounded-2xl" />
          <Skeleton className="h-48 w-full rounded-2xl" />
        </div>
      ) : list.isError ? (
        <ErrorState
          message={errorText(list.error)}
          onRetry={() => list.refetch()}
        />
      ) : items.length === 0 ? (
        <Card>
          <EmptyState
            icon={<Inbox className="size-6" aria-hidden />}
            title={
              lang === "ur" ? "Abhi koi chat nahi" : "No conversations yet"
            }
          >
            {lang === "ur"
              ? "Jab aap pi wale kisi business ko WhatsApp karenge, aap ke requests yahan nazar aayenge."
              : "Your requests appear here when you message a business that uses pi on WhatsApp."}
          </EmptyState>
        </Card>
      ) : (
        <>
          <TurnBanner rows={rows} lang={lang} />

          {rows.length >= 2 && (
            <BigPicture
              rows={rows}
              links={links}
              lang={lang}
              onNotRelated={(link) =>
                notRelated.mutate(link as IssueLink & { conversation: string })
              }
              onOpen={(issue) => {
                const row = rows.find((r) => r.title === issue.title);
                if (row) router.push(`/customer/c/${row.conversation.id}`);
              }}
            />
          )}

          <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
            <section aria-label="Requests" className="min-w-0 space-y-4">
              <Card className="p-4 sm:p-5">
                <Progress rows={rows} lang={lang} reading={reading} />
                {rows.length > 0 && (
                  <div
                    className="-mx-4 mt-4 flex snap-x gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none] sm:mx-0 sm:px-0 [&::-webkit-scrollbar]:hidden"
                    role="tablist"
                    aria-label="Filter requests"
                  >
                    {FILTERS.map((f) => {
                      const count =
                        f.key === "all"
                          ? rows.length
                          : rows.filter((r) => turnOf(r) === f.key).length;
                      if (f.key !== "all" && count === 0) return null;
                      return (
                        <button
                          key={f.key}
                          type="button"
                          role="tab"
                          aria-selected={filter === f.key}
                          onClick={() => setFilter(f.key)}
                          className={cn(
                            "inline-flex min-h-10 shrink-0 snap-start items-center gap-1.5 rounded-full border px-3.5 text-sm font-medium transition-colors sm:min-h-9",
                            filter === f.key
                              ? "border-accent bg-accent text-accent-foreground"
                              : "border-border bg-surface text-foreground-secondary hover:bg-surface-muted",
                          )}
                        >
                          {f.key !== "all" && (
                            <span
                              className={cn(
                                "size-2 shrink-0 rounded-full",
                                TURN[f.key].dot,
                              )}
                              aria-hidden
                            />
                          )}
                          {f[lang]}
                          <span
                            className={cn(
                              "rounded-full px-1.5 text-xs tabular-nums",
                              filter === f.key
                                ? "bg-accent-foreground/20"
                                : "bg-surface-muted",
                            )}
                          >
                            {count}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                )}
                {rows.length > 6 && (
                  <label className="relative mt-3 block">
                    <span className="sr-only">Search requests</span>
                    <Search
                      className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
                      aria-hidden
                    />
                    <input
                      type="search"
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      placeholder={
                        lang === "ur"
                          ? "Request ya business dhoondein"
                          : "Search requests or businesses"
                      }
                      className="h-11 w-full rounded-xl border border-border-strong bg-surface pl-10 pr-3.5 text-base placeholder:text-muted-foreground/70 focus-visible:outline-2 focus-visible:outline-ring sm:text-[15px]"
                    />
                  </label>
                )}
                {rows.length > 0 && shown.length === 0 ? (
                  <EmptyState
                    icon={<Search className="size-6" aria-hidden />}
                    title={lang === "ur" ? "Kuch nahi mila" : "Nothing matches"}
                    action={
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => {
                          setQuery("");
                          setFilter("all");
                        }}
                      >
                        {lang === "ur" ? "Sab dikhayein" : "Show everything"}
                      </Button>
                    }
                  >
                    {lang === "ur"
                      ? "Koi aur search ya filter try karein."
                      : "Try another search or filter."}
                  </EmptyState>
                ) : (
                  <div className="mt-2">
                    <JourneyRoad
                      issues={shown}
                      lang={lang}
                      keepOrder
                      subtitle={
                        items.length > 1
                          ? (r) => r.conversation.business
                          : undefined
                      }
                      onOpen={(r) =>
                        router.push(`/customer/c/${r.conversation.id}`)
                      }
                    />
                  </div>
                )}
              </Card>

              {/* With one business every request already opens its chat. */}
              {items.length > 1 && (
                <>
                  <h2 className="text-sm font-semibold text-muted-foreground">
                    Chats ({items.length})
                  </h2>
                  <ul className="space-y-2.5">
                    {items.map((c) => (
                      <li key={c.id}>
                        <ChatCard c={c} />
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </section>

            <aside className="space-y-4 lg:sticky lg:top-6">
              <ShareCard lang={lang} />
              <CustomerSecurityCard />
            </aside>
          </div>
        </>
      )}
    </div>
  );
}

/** pi reads chats it hasn't read since their last message, a few at a time. */
function useCatchUp(items: CustomerConversationItem[] | undefined) {
  const client = useQueryClient();
  const asked = useRef(new Set<string>());
  useEffect(() => {
    const stale = (items ?? [])
      .filter((c) => !c.issues_fresh)
      .map((c) => `${c.id}@${c.last_message_at}`)
      .filter((key) => !asked.current.has(key))
      .slice(0, 4);
    if (!stale.length) return;
    stale.forEach((key) => asked.current.add(key));
    void (async () => {
      for (const key of stale) {
        try {
          await customerGet(`/conversations/${key.split("@")[0]}/issues`);
        } catch {
          // pi can't read it right now; the chat still shows.
        }
      }
      void client.invalidateQueries({ queryKey: LIST });
    })();
  }, [items, client]);
}

/** Server-sent events: redraw the moment pi or the team changes something. The
 * 20-second polling stays as the fallback when the stream can't connect. */
function useLiveUpdates() {
  const client = useQueryClient();
  useEffect(() => {
    if (typeof EventSource === "undefined") return;
    const source = new EventSource("/api/v1/pi-app/customer-portal/stream", {
      withCredentials: true,
    });
    source.addEventListener("update", () => {
      void client.invalidateQueries({ queryKey: ["pi-customer"] });
    });
    return () => source.close();
  }, [client]);
}

function useMarkSeen() {
  const done = useRef(false);
  useEffect(() => {
    if (done.current) return;
    done.current = true;
    void customerPost("/seen").catch(() => undefined);
  }, []);
}

function LanguagePicker() {
  const client = useQueryClient();
  const prefs = usePrefs();
  const save = useMutation({
    mutationFn: (language: CustomerPrefs["language"]) =>
      customerPut<CustomerPrefs>("/prefs", { language }),
    onSuccess: (data) => {
      client.setQueryData(PREFS, data);
      void client.invalidateQueries({ queryKey: ["pi-customer"] });
    },
  });
  return (
    <label className="relative inline-flex min-h-11 items-center rounded-xl border border-border bg-surface px-2.5 text-sm sm:min-h-10">
      <Languages className="size-4 text-muted-foreground" aria-hidden />
      <span className="sr-only">Language</span>
      <select
        className="ml-1.5 bg-transparent pr-1 text-sm focus-visible:outline-none"
        value={prefs.data?.language ?? "auto"}
        disabled={save.isPending}
        onChange={(e) =>
          save.mutate(e.target.value as CustomerPrefs["language"])
        }
      >
        <option value="auto">Auto</option>
        <option value="en">English</option>
        <option value="roman_ur">Roman Urdu</option>
        <option value="ur">اردو</option>
        <option value="ar">العربية</option>
      </select>
    </label>
  );
}

/** Always says what (if anything) the customer needs to do. */
function TurnBanner({ rows, lang }: { rows: Row[]; lang: "en" | "ur" }) {
  const yours = rows.filter((r) => turnOf(r) === "you");
  if (yours.length) {
    const first = yours[0];
    const text = first.open_question || nextStepLine(first, lang);
    return (
      <Card className="border-warning/40 bg-warning-soft/40 p-4 sm:p-5">
        <p className="text-sm font-semibold text-warning">
          {lang === "ur"
            ? `${yours.length} ${yours.length === 1 ? "cheez" : "cheezon"} pe aap ka jawab chahiye`
            : `${yours.length} ${yours.length === 1 ? "thing needs" : "things need"} your answer`}
        </p>
        <p className="mt-1.5 text-[15px] font-medium leading-snug">{text}</p>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {first.title} · {first.conversation.business}
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {first.conversation.whatsapp_link && (
            <Button asChild className="min-h-11 sm:min-h-10">
              <a
                href={first.conversation.whatsapp_link}
                target="_blank"
                rel="noreferrer"
              >
                <MessageCircle className="size-4" aria-hidden />
                {lang === "ur"
                  ? "WhatsApp pe jawab dein"
                  : "Answer on WhatsApp"}
              </a>
            </Button>
          )}
          <Button asChild variant="secondary" className="min-h-11 sm:min-h-10">
            <Link href={`/customer/c/${first.conversation.id}`}>
              {lang === "ur" ? "Tafseel" : "Details"}
            </Link>
          </Button>
        </div>
      </Card>
    );
  }
  const due = rows
    .filter((r) => turnOf(r) === "us" && r.next_update_by)
    .map((r) => r.next_update_by as string)
    .sort()[0];
  return (
    <Card className="flex items-start gap-3 p-4 sm:p-5">
      <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full bg-success-soft text-success">
        <Check className="size-4" aria-hidden />
      </span>
      <div>
        <p className="font-semibold">
          {lang === "ur"
            ? "Aap se abhi kuch nahi chahiye."
            : "Nothing needed from you."}
        </p>
        <p className="text-sm text-muted-foreground">
          {due
            ? lang === "ur"
              ? `Team ${shortDay(due)} tak update degi.`
              : `Next update from us by ${shortDay(due)}.`
            : lang === "ur"
              ? "Kuch naya hua to pi aap ko WhatsApp pe batayega."
              : "pi will message you on WhatsApp when something changes."}
        </p>
      </div>
    </Card>
  );
}

/** One line: how many requests, how far they have come (journey, not "% finished"). */
function Progress({
  rows,
  lang,
  reading,
}: {
  rows: Row[];
  lang: "en" | "ur";
  reading: boolean;
}) {
  const pct = journeyPercent(rows);
  const total = rows.length;
  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          {total
            ? lang === "ur"
              ? `${total} requests`
              : `${total} ${total === 1 ? "request" : "requests"}`
            : reading
              ? lang === "ur"
                ? "pi aap ki chats parh raha hai…"
                : "pi is reading your chats…"
              : lang === "ur"
                ? "Abhi koi request nahi."
                : "No requests yet."}
        </p>
        {pct !== null && (
          <p className="text-sm font-medium tabular-nums">
            {lang === "ur" ? `Safar ${pct}%` : `Journey ${pct}%`}
          </p>
        )}
      </div>
      {pct !== null && (
        <div
          className="mt-2 h-2 overflow-hidden rounded-full bg-surface-muted"
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Journey progress across your requests"
        >
          <div
            className="h-full rounded-full bg-accent transition-all"
            style={{ width: `${pct}%` }}
          />
        </div>
      )}
    </div>
  );
}

/** The map and "where to start" share one card: one picture at a time. */
function BigPicture({
  rows,
  links,
  lang,
  onNotRelated,
  onOpen,
}: {
  rows: Row[];
  links: IssueLink[];
  lang: "en" | "ur";
  onNotRelated: (link: IssueLink) => void;
  onOpen: (issue: CustomerIssue) => void;
}) {
  const [view, setView] = useState<"map" | "start">("map");
  const tabs = [
    { key: "map", en: "Problem map", ur: "Naqsha" },
    { key: "start", en: "Where to start", ur: "Kahan se shuru" },
  ] as const;
  return (
    <Card className="p-4 sm:p-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">
          {lang === "ur" ? "Poori tasveer" : "The big picture"}
        </h2>
        <div
          role="tablist"
          aria-label="Choose a view"
          className="inline-flex rounded-xl bg-surface-muted p-1"
        >
          {tabs.map((t) => (
            <button
              key={t.key}
              type="button"
              role="tab"
              aria-selected={view === t.key}
              onClick={() => setView(t.key)}
              className={cn(
                "min-h-9 rounded-lg px-3 text-sm font-medium transition-colors",
                view === t.key
                  ? "bg-surface text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {t[lang]}
            </button>
          ))}
        </div>
      </div>
      {view === "map" ? (
        <ProblemMap
          issues={rows}
          links={links}
          lang={lang}
          onNotRelated={onNotRelated}
          onOpen={onOpen}
        />
      ) : (
        <div className="mx-auto max-w-xl">
          <PriorityChart issues={rows} links={links} lang={lang} />
        </div>
      )}
    </Card>
  );
}

function ChatCard({ c }: { c: CustomerConversationItem }) {
  return (
    <Link
      href={`/customer/c/${c.id}`}
      className="group flex items-center gap-3 rounded-2xl border border-border bg-surface p-3.5 transition-colors hover:bg-surface-muted/60 focus-visible:outline-2 focus-visible:outline-ring"
    >
      <Avatar name={c.business} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-3">
          <p className="truncate text-[15px] font-semibold">{c.business}</p>
          <span className="shrink-0 text-xs text-muted-foreground">
            {ago(c.last_message_at)}
          </span>
        </div>
        <p className="mt-0.5 truncate text-sm text-muted-foreground">
          {c.headline || c.preview || "Conversation"}
        </p>
      </div>
      <ChevronRight
        className="size-4 shrink-0 text-muted-foreground"
        aria-hidden
      />
    </Link>
  );
}

/** A view-only link for a boss or partner: requests and next steps, no chat. */
function ShareCard({ lang }: { lang: "en" | "ur" }) {
  const client = useQueryClient();
  const [copied, setCopied] = useState<string | null>(null);
  const [fresh, setFresh] = useState<CustomerShareLink | null>(null);
  const links = useQuery({
    queryKey: ["pi-customer", "share"],
    queryFn: () => customerGet<CustomerShareLink[]>("/share"),
  });
  const create = useMutation({
    mutationFn: () => customerPost<CustomerShareLink>("/share", {}),
    onSuccess: (link) => {
      setFresh(link);
      void client.invalidateQueries({ queryKey: ["pi-customer", "share"] });
    },
  });
  const revoke = useMutation({
    mutationFn: (id: string) => customerDelete(`/share/${id}`),
    onSuccess: () => {
      setFresh(null);
      void client.invalidateQueries({ queryKey: ["pi-customer", "share"] });
    },
  });
  const url =
    fresh?.token && typeof window !== "undefined"
      ? `${window.location.origin}/customer/s/${fresh.token}`
      : "";
  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(url);
    } catch {
      setCopied(null);
    }
  }
  return (
    <Card className="p-4 sm:p-5">
      <h2 className="flex items-center gap-2 font-semibold">
        <Link2 className="size-4" aria-hidden />
        {lang === "ur" ? "Apni team ko dikhayein" : "Share with my team"}
      </h2>
      <p className="mt-1 text-sm text-muted-foreground">
        {lang === "ur"
          ? "Sirf dekhne wala link: requests aur agla qadam. Chat, files ya price nahi. 7 din mein khatam."
          : "A view-only link: requests and next steps. No chat, files or prices. Expires in 7 days."}
      </p>
      {url ? (
        <div className="mt-3 space-y-2">
          <input
            readOnly
            value={url}
            aria-label="Share link"
            className="h-10 w-full rounded-lg border border-border bg-surface-muted px-3 text-xs"
            onFocus={(e) => e.currentTarget.select()}
          />
          <Button size="sm" variant="secondary" onClick={copy}>
            {copied === url ? (
              <Check className="size-4" aria-hidden />
            ) : (
              <Copy className="size-4" aria-hidden />
            )}
            {copied === url
              ? lang === "ur"
                ? "Copy ho gaya"
                : "Copied"
              : lang === "ur"
                ? "Link copy karein"
                : "Copy link"}
          </Button>
        </div>
      ) : (
        <Button
          className="mt-3 min-h-11 sm:min-h-10"
          variant="secondary"
          loading={create.isPending}
          onClick={() => create.mutate()}
        >
          <Link2 className="size-4" aria-hidden />
          {lang === "ur" ? "Link banayein" : "Create link"}
        </Button>
      )}
      {create.isError && (
        <p className="mt-2 text-sm text-danger">{errorText(create.error)}</p>
      )}
      {!!links.data?.length && (
        <ul className="mt-3 space-y-1.5 border-t border-border pt-3 text-xs">
          {links.data.map((l) => (
            <li key={l.id} className="flex items-center justify-between gap-2">
              <span className="text-muted-foreground">
                {lang === "ur" ? "Khatam: " : "Expires "}
                {shortDay(l.expires_at)} · {l.views}{" "}
                {lang === "ur"
                  ? "baar dekha"
                  : l.views === 1
                    ? "view"
                    : "views"}
              </span>
              <button
                type="button"
                className="inline-flex min-h-8 items-center gap-1 rounded-md px-2 text-danger hover:bg-danger-soft"
                onClick={() => revoke.mutate(l.id)}
                disabled={revoke.isPending}
              >
                <Trash2 className="size-3.5" aria-hidden />
                {lang === "ur" ? "Band karein" : "Turn off"}
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
