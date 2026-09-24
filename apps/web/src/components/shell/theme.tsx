"use client";

import { createContext, useContext, useSyncExternalStore } from "react";

type Theme = "light" | "dark";
const KEY = "platform.theme";
const Context = createContext<{ theme: Theme; setTheme: (t: Theme) => void }>({
  theme: "light",
  setTheme: () => {},
});

/** Runs before paint (inlined in <head>) so the saved theme never flashes. */
export const themeScript = `try{var t=localStorage.getItem("${KEY}");if(!t){t=matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"}document.documentElement.dataset.theme=t}catch(e){}`;

// The <html data-theme> attribute is the source of truth; React subscribes to it.
function subscribe(notify: () => void) {
  const observer = new MutationObserver(notify);
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["data-theme"],
  });
  return () => observer.disconnect();
}

const readTheme = (): Theme =>
  document.documentElement.dataset.theme === "dark" ? "dark" : "light";

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const theme = useSyncExternalStore(
    subscribe,
    readTheme,
    () => "light" as Theme,
  );
  const setTheme = (next: Theme) => {
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem(KEY, next);
    } catch {
      /* storage unavailable: the choice lasts until reload */
    }
  };
  return (
    <Context.Provider value={{ theme, setTheme }}>{children}</Context.Provider>
  );
}

export const useTheme = () => useContext(Context);
