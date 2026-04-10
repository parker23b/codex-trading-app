import type { Metadata } from "next";
import type { ReactNode } from "react";

import { AppNav } from "@/components/app-nav";
import { ThemeToggle } from "@/components/theme-toggle";

import "./globals.css";

export const metadata: Metadata = {
  title: "Investmate Ops",
  description: "Operator console for supervising an autonomous trading system.",
};

export default function RootLayout({
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
        <div className="console-app">
          <header className="console-app__header">
            <AppNav />
          </header>
          <div className="console-app__workspace">{children}</div>
        </div>
        <ThemeToggle />
      </body>
    </html>
  );
}
