"use client";

import * as React from "react";
import { Download, Share, X } from "lucide-react";

import { Button } from "@/components/ui/button";

/** Set NEXT_PUBLIC_PWA=off to switch the service worker off (it then removes itself). */
const ENABLED = process.env.NEXT_PUBLIC_PWA !== "off";
const DISMISS_DAYS = 30;
const APP_NAME = "Owner OS";
const DISMISS_KEY = "pwa-dismissed:owner-os";

type InstallEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
};

function standalone() {
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    (navigator as Navigator & { standalone?: boolean }).standalone === true
  );
}

function iosSafari() {
  const ua = navigator.userAgent;
  return (
    /iphone|ipad|ipod/i.test(ua) &&
    /safari/i.test(ua) &&
    !/crios|fxios|edgios/i.test(ua)
  );
}

function dismissedRecently() {
  try {
    const at = Number(localStorage.getItem(DISMISS_KEY) ?? 0);
    return Date.now() - at < DISMISS_DAYS * 86_400_000;
  } catch {
    return false;
  }
}

/** Registers the service worker once in production (or removes it when PWA is off). */
export function useServiceWorker() {
  React.useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    if (!ENABLED) {
      void navigator.serviceWorker
        .getRegistrations()
        .then((all) => Promise.all(all.map((r) => r.unregister())))
        .catch(() => {});
      return;
    }
    if (process.env.NODE_ENV !== "production") return;
    void navigator.serviceWorker
      .register("/sw.js", { scope: "/" })
      .catch(() => {});
  }, []);
}

/**
 * Mounted once in the root layout so the worker is active on every page, including
 * /login (it never caches HTML or API responses, so this is safe before sign-in).
 */
export function ServiceWorker() {
  useServiceWorker();
  return null;
}

/**
 * A small, dismissible "Install Owner OS" card: the browser's own install dialog on
 * Android and desktop Chrome/Edge, and the Share → Add to Home Screen hint on iPhone
 * Safari. Mount it once for signed-in users.
 */
export function InstallPrompt() {
  const [event, setEvent] = React.useState<InstallEvent | null>(null);
  const [ios, setIos] = React.useState(false);
  const [hidden, setHidden] = React.useState(true);

  React.useEffect(() => {
    if (!ENABLED || standalone() || dismissedRecently()) return;
    const onPrompt = (e: Event) => {
      e.preventDefault();
      setEvent(e as InstallEvent);
      setHidden(false);
    };
    const onInstalled = () => setHidden(true);
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    // iPhone has no install event: show the Add to Home Screen hint after a moment.
    const timer = iosSafari()
      ? window.setTimeout(() => {
          setIos(true);
          setHidden(false);
        }, 4000)
      : undefined;
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("appinstalled", onInstalled);
      if (timer) window.clearTimeout(timer);
    };
  }, []);

  function dismiss() {
    try {
      localStorage.setItem(DISMISS_KEY, String(Date.now()));
    } catch {
      /* private mode: just hide for now */
    }
    setHidden(true);
  }

  async function install() {
    if (!event) return;
    await event.prompt();
    await event.userChoice.catch(() => undefined);
    setEvent(null);
    setHidden(true);
  }

  if (hidden || (!event && !ios)) return null;
  return (
    <div
      role="dialog"
      aria-label={`Install ${APP_NAME}`}
      className="fixed inset-x-3 top-[calc(3.75rem+env(safe-area-inset-top))] z-40 rounded-xl border border-border bg-surface p-4 shadow-lg md:inset-x-auto md:top-16 md:right-6 md:w-[360px]"
    >
      <div className="flex items-start gap-3">
        {/* eslint-disable-next-line @next/next/no-img-element -- the app's own icon */}
        <img
          src="/icons/owner-os-192.png"
          alt=""
          className="size-10 shrink-0 rounded-lg"
        />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold">Install {APP_NAME}</p>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {ios ? (
              <>
                Tap{" "}
                <Share
                  className="inline size-4 align-text-bottom"
                  aria-label="Share"
                />{" "}
                then <strong>Add to Home Screen</strong> to open {APP_NAME} like
                an app.
              </>
            ) : (
              <>
                Open your workspace, PI and the admin console from your home
                screen in one tap.
              </>
            )}
          </p>
        </div>
        <button
          type="button"
          onClick={dismiss}
          aria-label="Not now"
          className="-me-1 -mt-1 flex size-8 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-surface-muted"
        >
          <X className="size-4" aria-hidden />
        </button>
      </div>
      {!ios && (
        <div className="mt-3 flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={dismiss}>
            Not now
          </Button>
          <Button size="sm" onClick={install}>
            <Download className="size-4" aria-hidden />
            Install
          </Button>
        </div>
      )}
    </div>
  );
}
