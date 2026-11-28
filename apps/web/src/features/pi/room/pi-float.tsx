"use client";

import { useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { PictureInPicture2 } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * Keeps pi in view while someone shares their screen. The person sharing looks at their own work,
 * not at the room, so pi, its state ("listening", "thinking", "speaking") and the words it says
 * would be out of sight. This opens a small window that stays on top of every other window and tab
 * (the browser's Document Picture-in-Picture), and draws pi into it. It goes with the person while
 * they move between windows, and closes when they close it or leave the call.
 *
 * It needs a click to open (the browser insists) and exists only in desktop Chrome and Edge: where
 * it is missing the button is not shown. The window holds what the room already shows (pi's face,
 * its state, the latest lines); nothing is sent anywhere.
 */

type PipApi = {
  requestWindow: (options?: {
    width?: number;
    height?: number;
  }) => Promise<Window>;
};

function pipApi(): PipApi | null {
  if (typeof window === "undefined") return null;
  const api = (window as unknown as { documentPictureInPicture?: PipApi })
    .documentPictureInPicture;
  return api ?? null;
}

/** The page's styles, copied into the floating window so pi looks the same there. */
function copyStyles(target: Window) {
  for (const sheet of Array.from(document.styleSheets)) {
    try {
      const css = Array.from(sheet.cssRules)
        .map((rule) => rule.cssText)
        .join("\n");
      const style = target.document.createElement("style");
      style.textContent = css;
      target.document.head.appendChild(style);
    } catch {
      if (sheet.href) {
        const link = target.document.createElement("link");
        link.rel = "stylesheet";
        link.href = sheet.href;
        target.document.head.appendChild(link);
      }
    }
  }
  target.document.documentElement.className =
    document.documentElement.className;
  target.document.body.className = document.body.className;
  target.document.body.style.margin = "0";
}

export function PiFloat({ children }: { children: ReactNode }) {
  const [win, setWin] = useState<Window | null>(null);
  const [failed, setFailed] = useState(false);
  const api = pipApi();

  // close the floating window when this goes away (the person left the call)
  useEffect(() => () => win?.close(), [win]);
  if (!api) return null;

  async function open() {
    setFailed(false);
    try {
      const next = await api!.requestWindow({ width: 320, height: 360 });
      copyStyles(next);
      next.addEventListener("pagehide", () => setWin(null));
      setWin(next);
    } catch {
      setFailed(true);
    }
  }

  return (
    <>
      <div className="flex items-center justify-end gap-2">
        {failed && (
          <span className="text-xs text-muted-foreground">
            The browser did not open it. Try again.
          </span>
        )}
        <Button
          variant="secondary"
          size="sm"
          aria-pressed={win !== null}
          onClick={() => (win ? win.close() : void open())}
        >
          <PictureInPicture2 />{" "}
          {win ? "Bring pi back here" : "Keep pi with me while I share"}
        </Button>
      </div>
      {win && createPortal(children, win.document.body)}
    </>
  );
}
