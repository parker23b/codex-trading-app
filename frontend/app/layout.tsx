import type { Metadata } from "next";
import type { ReactNode } from "react";

import { AppNav } from "@/components/app-nav";
import { ThemeToggle } from "@/components/theme-toggle";

import "./globals.css";

export const metadata: Metadata = {
  title: "Investmate",
  description: "Smart investing. Made simple.",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: ReactNode;
}>) {
  const themeInitScript = `
    (function () {
      var storageKey = "trading-platform-theme";
      var stored = window.localStorage.getItem(storageKey);
      var theme = stored || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
      document.documentElement.dataset.theme = theme;
    })();
  `;

  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body>
        <div className="app-shell">
          <header className="app-header">
            <div className="brand-lockup">
              <svg
                className="brand-mark"
                viewBox="0 0 72 72"
                aria-hidden="true">
                <path
                  d="M27.5 7.5h17l14.14 5.86 5.86 14.14v17L58.64 58.64 44.5 64.5h-17L13.36 58.64 7.5 44.5v-17l5.86-14.14L27.5 7.5Z"
                  className="brand-octagon"
                />
                <circle cx="36" cy="36" r="4.5" className="brand-center" />
                <circle cx="36" cy="18" r="3.2" className="brand-node" />
                <circle cx="48.7" cy="23.3" r="3.2" className="brand-node" />
                <circle cx="54" cy="36" r="3.2" className="brand-node" />
                <circle cx="48.7" cy="48.7" r="3.2" className="brand-node" />
                <circle cx="36" cy="54" r="3.2" className="brand-node" />
                <circle cx="23.3" cy="48.7" r="3.2" className="brand-node" />
                <circle cx="18" cy="36" r="3.2" className="brand-node" />
                <circle cx="23.3" cy="23.3" r="3.2" className="brand-node" />
                <line x1="36" y1="36" x2="36" y2="18" className="brand-link" />
                <line
                  x1="36"
                  y1="36"
                  x2="48.7"
                  y2="23.3"
                  className="brand-link"
                />
                <line x1="36" y1="36" x2="54" y2="36" className="brand-link" />
                <line
                  x1="36"
                  y1="36"
                  x2="48.7"
                  y2="48.7"
                  className="brand-link"
                />
                <line x1="36" y1="36" x2="36" y2="54" className="brand-link" />
                <line
                  x1="36"
                  y1="36"
                  x2="23.3"
                  y2="48.7"
                  className="brand-link"
                />
                <line x1="36" y1="36" x2="18" y2="36" className="brand-link" />
                <line
                  x1="36"
                  y1="36"
                  x2="23.3"
                  y2="23.3"
                  className="brand-link"
                />
              </svg>
              <div>
                <h1>Investmate</h1>
                <p className="muted">Smart investing. Made simple.</p>
              </div>
            </div>
            <AppNav />
          </header>
          {children}
        </div>
        <ThemeToggle />
      </body>
    </html>
  );
}
