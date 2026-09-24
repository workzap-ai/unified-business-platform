"use client";

import { createContext, useContext, useEffect, useState } from "react";

type Theme = "light" | "dark";
const KEY = "platform.theme";
const Context = createContext<{ theme: Theme; setTheme: (t: Theme) => void }>({
  theme: "light",
  setTheme: () => {},
});

/** Runs before paint (inlined in <head>) so the saved theme never flashes. */
export const themeScript = `try{var t=localStorage.getItem("${KEY}");if(!t){t=matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"}document.documentElement.dataset.theme=t}catch(e){}`;

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>("light");
  useEffect(() => {
    const current = document.documentElement.dataset.theme;
    if (current === "dark" || current === "light") setThemeState(current);
  }, []);
  const setTheme = (next: Theme) => {
    setThemeState(next);
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem(KEY, next);
    } catch {
      /* ignore */
    }
  };
  return <Context.Provider value={{ theme, setTheme }}>{children}</Context.Provider>;
}

export const useTheme = () => useContext(Context);
