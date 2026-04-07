"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/", label: "Dashboard" },
  { href: "/events", label: "Events" },
  { href: "/reviewer", label: "AI Reviewer" },
  { href: "/strategies", label: "Strategies" },
];

export function AppNav() {
  const pathname = usePathname();

  return (
    <nav>
      {links.map((link) => {
        const isActive = pathname === link.href;
        return (
          <Link key={link.href} href={link.href} className={`nav-link ${isActive ? "is-active" : ""}`.trim()}>
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
