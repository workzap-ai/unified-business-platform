"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import { APP_URL, PRODUCTS, TALK } from "./data";

type Item = { href: string; label: string };

const PLAIN: Item[] = [
  { href: "/company", label: "Company" },
  { href: "/contact", label: "Contact" },
];

function current(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`)
    ? ("page" as const)
    : undefined;
}

/**
 * The site header. The Products menu and the phone menu are disclosure buttons:
 * Enter or Space opens them, Escape closes them and returns focus to the button,
 * and a click elsewhere closes them. Both close by themselves on navigation, because
 * "open" is stored together with the path it was opened on.
 */
export function SiteNav({ logo }: { logo: React.ReactNode }) {
  const pathname = usePathname();
  const [menuAt, setMenuAt] = useState<string | null>(null);
  const [phoneAt, setPhoneAt] = useState<string | null>(null);
  const menuOpen = menuAt === pathname;
  const phoneOpen = phoneAt === pathname;
  const menuId = useId();
  const phoneId = useId();
  const menuBtn = useRef<HTMLButtonElement>(null);
  const phoneBtn = useRef<HTMLButtonElement>(null);
  const root = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!menuOpen && !phoneOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (menuOpen) {
        setMenuAt(null);
        menuBtn.current?.focus();
      }
      if (phoneOpen) {
        setPhoneAt(null);
        phoneBtn.current?.focus();
      }
    };
    const onClick = (e: MouseEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) {
        setMenuAt(null);
        setPhoneAt(null);
      }
    };
    const onFocus = (e: FocusEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) {
        setMenuAt(null);
      }
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    document.addEventListener("focusin", onFocus);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("focusin", onFocus);
    };
  }, [menuOpen, phoneOpen]);

  const productsActive =
    pathname === "/products" ||
    pathname.startsWith("/nori") ||
    pathname.startsWith("/pi");

  return (
    <header className="wz-header">
      <nav ref={root} className="wz-wrap wz-nav" aria-label="Workzap">
        <Link href="/" className="wz-brand" aria-label="Workzap, home">
          {logo}
        </Link>

        <ul className="wz-links">
          <li className="wz-has-menu">
            <button
              ref={menuBtn}
              type="button"
              className={productsActive ? "wz-link wz-link-active" : "wz-link"}
              aria-expanded={menuOpen}
              aria-controls={menuId}
              onClick={() => setMenuAt(menuOpen ? null : pathname)}
            >
              Products
              <svg
                className="wz-caret"
                width="12"
                height="12"
                viewBox="0 0 12 12"
                aria-hidden="true"
              >
                <path
                  d="M2.5 4.5 6 8l3.5-3.5"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
            <div id={menuId} className="wz-menu" hidden={!menuOpen}>
              <ul>
                {(["nori", "pi"] as const).map((k) => {
                  const p = PRODUCTS[k];
                  return (
                    <li key={k}>
                      <Link href={p.href} className={`wz-menu-item wz-m-${k}`}>
                        <span className="wz-menu-logo">
                          <Image
                            src={p.logo}
                            alt=""
                            width={p.width}
                            height={p.height}
                            unoptimized
                          />
                        </span>
                        <span>
                          <strong>{p.name}</strong>
                          <span>{p.menu}</span>
                        </span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
              <Link href="/products" className="wz-menu-all">
                Compare our products
                <span aria-hidden="true"> →</span>
              </Link>
            </div>
          </li>
          {PLAIN.map((l) => (
            <li key={l.href}>
              <Link
                href={l.href}
                className={
                  current(pathname, l.href)
                    ? "wz-link wz-link-active"
                    : "wz-link"
                }
                aria-current={current(pathname, l.href)}
              >
                {l.label}
              </Link>
            </li>
          ))}
        </ul>

        <div className="wz-nav-actions">
          <a href={APP_URL} className="wz-link wz-signin">
            Sign in
          </a>
          <Link href={TALK} className="wz-btn wz-btn-primary wz-btn-sm">
            Talk to pi
          </Link>
        </div>

        <button
          ref={phoneBtn}
          type="button"
          className="wz-burger"
          aria-expanded={phoneOpen}
          aria-controls={phoneId}
          onClick={() => setPhoneAt(phoneOpen ? null : pathname)}
        >
          <span className="wz-burger-label">Menu</span>
          <span className="wz-burger-icon" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
        </button>

        <div id={phoneId} className="wz-phone" hidden={!phoneOpen}>
          <p className="wz-phone-label">Products</p>
          <ul>
            <li>
              <Link href="/nori">
                <strong>nori</strong>
                <span>{PRODUCTS.nori.line}</span>
              </Link>
            </li>
            <li>
              <Link href="/pi">
                <strong>pi</strong>
                <span>{PRODUCTS.pi.line} Coming soon.</span>
              </Link>
            </li>
            <li>
              <Link href="/products">
                <strong>Compare our products</strong>
              </Link>
            </li>
          </ul>
          <ul className="wz-phone-plain">
            {PLAIN.map((l) => (
              <li key={l.href}>
                <Link href={l.href} aria-current={current(pathname, l.href)}>
                  <strong>{l.label}</strong>
                </Link>
              </li>
            ))}
            <li>
              <a href={APP_URL}>
                <strong>Sign in</strong>
              </a>
            </li>
          </ul>
          <Link href={TALK} className="wz-btn wz-btn-primary wz-phone-cta">
            Talk to pi
          </Link>
        </div>
      </nav>
    </header>
  );
}
