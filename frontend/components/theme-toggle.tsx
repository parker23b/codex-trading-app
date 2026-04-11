"use client";

import { useEffect, useState } from "react";

type Theme = "light" | "dark";

const STORAGE_KEY = "trading-platform-theme";

function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme;
}

type ThemeToggleProps = {
  variant?: "floating" | "nav";
  className?: string;
};

function joinClasses(...values: Array<string | undefined | false>) {
  return values.filter(Boolean).join(" ");
}

export function ThemeToggle({ variant = "floating", className }: ThemeToggleProps) {
  const [theme, setTheme] = useState<Theme>("light");

  useEffect(() => {
    const storedTheme = window.localStorage.getItem(STORAGE_KEY) as Theme | null;
    const preferredTheme =
      storedTheme ??
      (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");

    setTheme(preferredTheme);
    applyTheme(preferredTheme);
  }, []);

  const handleToggle = () => {
    const nextTheme = theme === "light" ? "dark" : "light";
    setTheme(nextTheme);
    applyTheme(nextTheme);
    window.localStorage.setItem(STORAGE_KEY, nextTheme);
  };

  return (
    <button
      type="button"
      className={joinClasses(
        variant === "nav"
          ? "inline-flex h-9 w-9 items-center justify-center rounded-full border border-[color:var(--glass-stroke)] bg-[image:var(--glass-surface-soft)] text-[color:var(--text-secondary)] shadow-[var(--shadow-soft)] transition-[transform,background-color,color,box-shadow] duration-150 ease-out hover:-translate-y-px hover:text-[color:var(--text-primary)] hover:shadow-[var(--shadow-panel)]"
          : "fixed right-4 bottom-4 z-30 flex h-11 w-11 items-center justify-center rounded-full border border-[color:var(--glass-stroke)] bg-[image:var(--glass-surface)] text-[color:var(--text-primary)] shadow-[var(--shadow-panel)] backdrop-blur-[16px] transition-transform duration-150 ease-out hover:-translate-y-px hover:shadow-[var(--shadow-raised)]",
        className,
      )}
      onClick={handleToggle}
      aria-label={theme === "light" ? "Switch to dark mode" : "Switch to light mode"}
      title={theme === "light" ? "Switch to dark mode" : "Switch to light mode"}
    >
      {theme === "light" ? (
        <svg viewBox="0 0 24 24" aria-hidden="true" className="h-[18px] w-[18px]">
          <path
            d="M12 3.5a.75.75 0 0 1 .75.75v1.1a.75.75 0 0 1-1.5 0v-1.1A.75.75 0 0 1 12 3.5Zm0 14.05a.75.75 0 0 1 .75.75v1.45a.75.75 0 0 1-1.5 0V18.3a.75.75 0 0 1 .75-.75Zm8.5-5.3a.75.75 0 0 1-.75.75h-1.45a.75.75 0 0 1 0-1.5h1.45a.75.75 0 0 1 .75.75Zm-14.8 0a.75.75 0 0 1-.75.75H3.5a.75.75 0 0 1 0-1.5h1.45a.75.75 0 0 1 .75.75Zm10.59-5.89a.75.75 0 0 1 1.06 0l.77.77a.75.75 0 0 1-1.06 1.06l-.77-.77a.75.75 0 0 1 0-1.06Zm-10.2 10.2a.75.75 0 0 1 1.06 0l.77.77a.75.75 0 1 1-1.06 1.06l-.77-.77a.75.75 0 0 1 0-1.06Zm11.03 1.83a.75.75 0 0 1 0-1.06l.77-.77a.75.75 0 0 1 1.06 1.06l-.77.77a.75.75 0 0 1-1.06 0Zm-10.2-10.2a.75.75 0 0 1 0-1.06l.77-.77A.75.75 0 0 1 8.75 7.52l-.77.77a.75.75 0 0 1-1.06 0ZM12 8.1A4.15 4.15 0 1 1 7.85 12 4.16 4.16 0 0 1 12 8.1Zm0 1.5A2.65 2.65 0 1 0 14.65 12 2.65 2.65 0 0 0 12 9.6Z"
            fill="currentColor"
          />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" aria-hidden="true" className="h-[18px] w-[18px]">
          <path
            d="M14.96 3.82a.75.75 0 0 1 .85.98 7.42 7.42 0 0 0-.26 1.97 7.58 7.58 0 1 0 7.58 7.58 7.56 7.56 0 0 0-1.78-4.86.75.75 0 0 1 .85-1.17A9.08 9.08 0 1 1 13.8 2.95a.75.75 0 0 1 1.16.87Z"
            fill="currentColor"
          />
        </svg>
      )}
    </button>
  );
}
