"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/", label: "Ask" },
  { href: "/programs", label: "Programs" },
  { href: "/scholarships", label: "Scholarships" },
  { href: "/directory", label: "Contacts" },
  { href: "/onboarding", label: "Getting started" },
];

export function Header({ name = process.env.NEXT_PUBLIC_APP_NAME || "BU AI", tagline = "Intelligent Student Success Platform", onHome }: {
  name?: string; tagline?: string; onHome?: () => void;
}) {
  const path = usePathname();
  return (
    <header className="top">
      <Link className="brand" href="/" onClick={onHome} aria-label={`${name} home`}>
        <span className="mark" aria-hidden="true">B</span>
        <span><b>{name}</b><small>{tagline}</small></span>
      </Link>
      <nav className="nav" aria-label="Main">
        {NAV.map(n => (
          <Link key={n.href} href={n.href} className={path === n.href ? "on" : ""} aria-current={path === n.href ? "page" : undefined}>
            {n.label}
          </Link>
        ))}
      </nav>
      <span className="proto">Independent prototype</span>
    </header>
  );
}

/** A link that opens the assistant with a question already asked. */
export function AskLink({ q, children, cat = "" }: { q: string; children: React.ReactNode; cat?: string }) {
  const params = new URLSearchParams({ q, ...(cat ? { cat } : {}) });
  return <Link className="ghost sm" href={`/?${params.toString()}`}>{children}</Link>;
}
