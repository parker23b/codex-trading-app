import type { Metadata } from "next";
import type { ReactNode } from "react";

import { AimeeShell } from "@/components/aimee/aimee-shell";
import { AppNav } from "@/components/app-nav";

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
        <div className="min-h-screen">
          <header className="fixed inset-x-0 top-0 z-20 h-[var(--nav-height)] border-b border-[color:var(--border)] bg-[color:color-mix(in_srgb,var(--bg-shell)_95%,transparent)] shadow-[0_8px_24px_rgba(0,0,0,0.12)] backdrop-blur-[18px]">
            <AppNav />
          </header>
          <div className="min-h-[calc(100vh-var(--nav-height))] pt-[var(--nav-height)]">{children}</div>
        </div>
        <AimeeShell />
      </body>
    </html>
  );
}
