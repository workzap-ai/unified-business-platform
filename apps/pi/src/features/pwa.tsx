"use client";

import * as React from "react";
import { Download, Share, X } from "lucide-react";

import { Button } from "@/components/ui";

/** Set NEXT_PUBLIC_PWA=off to switch the service worker off (it then removes itself). */
const ENABLED = process.env.NEXT_PUBLIC_PWA !== "off";
const DISMISS_DAYS = 30;

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

function dismissedRecently(key: string) {
  try {
    const at = Number(localStorage.getItem(key) ?? 0);
    return Date.now() - at < DISMISS_DAYS * 86_400_000;
  } catch {
    return false;
  }
}

/** Registers the service worker once (or removes it when PWA is switched off). */
export function useServiceWorker() {
  React.useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    if (!ENABLED) {
      void navigator.serviceWorker
        .getRegistrations()
        .then((all) => Promise.all(all.map((r) => r.unregister())));
      return;
    }
    if (process.env.NODE_ENV !== "production") return;
    void navigator.serviceWorker
      .register("/sw.js", { scope: "/" })
      .catch(() => {});
  }, []);
}

/**
 * A small, dismissible "Install" card: the browser's own install dialog on Android and
 * desktop Chrome/Edge, and the Share → Add to Home Screen hint on iPhone Safari.
 */
export function InstallPrompt({ appName }: { appName: string }) {
  useServiceWorker();
  const key = `pwa-dismissed:${appName}`;
  const [event, setEvent] = React.useState<InstallEvent | null>(null);
  const [ios, setIos] = React.useState(false);
  const [hidden, setHidden] = React.useState(true);

  React.useEffect(() => {
    if (!ENABLED || standalone() || dismissedRecently(key)) return;
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
  }, [key]);

  function dismiss() {
    try {
      localStorage.setItem(key, String(Date.now()));
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
      aria-label={`Install ${appName}`}
      className="fixed inset-x-3 top-[calc(4rem+env(safe-area-inset-top))] z-40 rounded-2xl border border-border bg-surface p-4 shadow-lg md:inset-x-auto md:right-6 md:top-20 md:w-[360px]"
    >
      <div className="flex items-start gap-3">
        {/* eslint-disable-next-line @next/next/no-img-element -- the app's own icon */}
        <img
          src={
            appName === "pi Customer"
              ? "/icons/customer-192.png"
              : "/icons/pi-192.png"
          }
          alt=""
          className="size-11 shrink-0 rounded-xl"
        />
        <div className="min-w-0 flex-1">
          <p className="font-semibold">Install {appName}</p>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {ios ? (
              <>
                Tap{" "}
                <Share
                  className="inline size-4 align-text-bottom"
                  aria-label="Share"
                />{" "}
                then <strong>Add to Home Screen</strong> to open {appName} like
                an app.
              </>
            ) : (
              <>Open {appName} from your home screen in one tap, full screen.</>
            )}
          </p>
        </div>
        <button
          type="button"
          onClick={dismiss}
          aria-label="Not now"
          className="-me-1 -mt-1 flex size-9 shrink-0 items-center justify-center rounded-lg text-muted-foreground hover:bg-surface-muted"
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
