"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BelaMark, Sparkle } from "./BelaMark";

const NAV = [
  { href: "/", label: "Ask" },
  { href: "/programs", label: "Programs" },
  { href: "/scholarships", label: "Scholarships" },
  { href: "/directory", label: "Contacts" },
  { href: "/onboarding", label: "Getting started" },
];

export function Header({ name = process.env.NEXT_PUBLIC_APP_NAME || "Bela", tagline = "Your Belhaven guide", onHome, thinking = false }: {
  name?: string; tagline?: string; onHome?: () => void; thinking?: boolean;
}) {
  const path = usePathname();
  const label = /^ask\b/i.test(name) ? name : `Ask ${name}`;
  return (
    <header className="top">
      <Link className="brand" href="/" onClick={onHome} aria-label={`${label} home`}>
        <BelaMark size={40} />
        <span><b>{label} <Sparkle size={18} active={thinking} /></b><small>{tagline}</small></span>
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
