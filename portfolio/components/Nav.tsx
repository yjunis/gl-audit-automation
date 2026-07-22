"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

const LINKS = [
  { href: "/", label: "소개" },
  { href: "/dashboard", label: "대시보드" },
  { href: "/report", label: "보고서(PDF)" },
  { href: "/case-study", label: "탐지 사례" },
  { href: "/methodology", label: "분석 방법" },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname.startsWith(href);
}

export default function Nav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-50 border-b border-line bg-white">
      <nav className="container-page flex h-[72px] items-center justify-between">
        <Link href="/" className="flex items-center gap-2.5" onClick={() => setOpen(false)}>
          <span className="h-4 w-4 bg-rail" aria-hidden />
          <span className="text-sm font-bold tracking-tight text-ink">
            GL 감사 자동화
          </span>
        </Link>

        <ul className="hidden items-center gap-6 md:flex">
          {LINKS.map((l) => {
            const active = isActive(pathname, l.href);
            return (
              <li key={l.href}>
                <Link
                  href={l.href}
                  aria-current={active ? "page" : undefined}
                  className={`relative py-6 text-sm font-semibold transition-colors ${
                    active ? "text-ink" : "text-muted hover:text-ink"
                  }`}
                >
                  {l.label}
                  {active && (
                    <span
                      className="absolute inset-x-0 bottom-0 h-0.5 bg-rail"
                      aria-hidden
                    />
                  )}
                </Link>
              </li>
            );
          })}
        </ul>

        <button
          type="button"
          className="border border-ink px-3 py-1.5 text-sm font-semibold text-ink md:hidden"
          aria-label={open ? "메뉴 닫기" : "메뉴 열기"}
          aria-expanded={open}
          aria-controls="mobile-menu"
          onClick={() => setOpen((v) => !v)}
        >
          메뉴
        </button>
      </nav>

      {open && (
        <ul id="mobile-menu" className="container-page flex flex-col border-t border-line pb-2 md:hidden">
          {LINKS.map((l) => {
            const active = isActive(pathname, l.href);
            return (
              <li key={l.href}>
                <Link
                  href={l.href}
                  onClick={() => setOpen(false)}
                  aria-current={active ? "page" : undefined}
                  className={`block border-l-2 px-3 py-2.5 text-sm font-semibold ${
                    active ? "border-rail text-ink" : "border-transparent text-muted"
                  }`}
                >
                  {l.label}
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </header>
  );
}
