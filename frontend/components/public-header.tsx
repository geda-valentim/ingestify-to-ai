"use client";

import { useEffect, useRef, type ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ArrowUpRight, Github, Menu } from "lucide-react";
import { Brand } from "./brand";
import { GITHUB } from "./landing/content";
import { useAuthStore } from "@/lib/store/auth";
import styles from "./public-header.module.css";

const LINKS = [
  { href: "/#operacoes", label: "Platform", path: "/" },
  { href: "/features", label: "Features", path: "/features" },
  { href: "/agents", label: "Agents", path: "/agents" },
  { href: "/business", label: "Business", path: "/business" },
  { href: "/docs", label: "Docs", path: "/docs" },
];

/** Shared public navigation; the native mobile menu also works without JavaScript. */
export function PublicHeader({ motionControl }: { motionControl?: ReactNode }) {
  const pathname = usePathname();
  const signedIn = useAuthStore(
    (state) => state._hasHydrated && !!state.token && !!state.user,
  );
  const menu = useRef<HTMLDetailsElement>(null);
  const closeMenu = () => {
    if (menu.current) menu.current.open = false;
  };

  useEffect(() => {
    if (menu.current) menu.current.open = false;
  }, [pathname]);

  useEffect(() => {
    const desktop = matchMedia("(min-width: 1000px)");
    const resize = () => {
      if (desktop.matches && menu.current) menu.current.open = false;
    };
    desktop.addEventListener("change", resize);
    return () => desktop.removeEventListener("change", resize);
  }, []);

  const links = LINKS.map(({ href, label, path }) => (
    <Link
      key={path}
      href={href}
      aria-current={
        pathname === path ||
        (path !== "/" && pathname.startsWith(`${path}/`)) ||
        (path === "/docs" && pathname.startsWith("/pt/docs"))
          ? "page"
          : undefined
      }
      onClick={closeMenu}
    >
      {label}
    </Link>
  ));

  const accountLink = (
    <Link
      className={styles.account}
      href={signedIn ? "/dashboard" : "/login"}
      onClick={closeMenu}
    >
      {signedIn ? "Open dashboard" : "Sign in"}
      <ArrowUpRight size={14} aria-hidden="true" />
    </Link>
  );

  return (
    <header className={styles.header} data-public-header lang="en">
      <Link className={styles.brand} href="/" aria-label="Ingestify home">
        <Brand />
      </Link>
      <div className={styles.controls}>
        {motionControl && <div className={styles.motion}>{motionControl}</div>}
        <nav className={styles.desktop} aria-label="Main navigation">
          {links}
          <a
            href={GITHUB}
            className={styles.github}
            aria-label="Ingestify on GitHub"
          >
            <Github size={18} aria-hidden="true" />
          </a>
          {accountLink}
        </nav>
        <details
          ref={menu}
          className={styles.mobile}
          onKeyDown={(event) => {
            if (event.key === "Escape" && menu.current?.open) {
              event.preventDefault();
              closeMenu();
              menu.current.querySelector("summary")?.focus();
            }
          }}
        >
          <summary
            role="button"
            aria-label="Menu"
            aria-controls="public-mobile-navigation"
          >
            <Menu size={19} aria-hidden="true" />
            <span>Menu</span>
          </summary>
          <nav id="public-mobile-navigation" aria-label="Mobile navigation">
            {links}
            <a href={GITHUB} onClick={closeMenu}>
              GitHub <Github size={16} aria-hidden="true" />
            </a>
            {accountLink}
          </nav>
        </details>
      </div>
    </header>
  );
}
