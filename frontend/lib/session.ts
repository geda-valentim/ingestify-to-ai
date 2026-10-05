/**
 * Session lifecycle helpers: token expiry, and what happens when a session ends.
 *
 * Kept free of React so lib/api.ts can end a session from any request that
 * comes back 401.
 */
import { useAuthStore } from "@/lib/store/auth";

// Pages that work without a session; an expiry there must not redirect.
const PUBLIC_PATHS = ["/login", "/register", "/docs"];

const EXPIRED_FLAG = "session-expired";

let expiring = false;

/** Milliseconds since epoch at which the JWT expires, or null if it has no readable `exp`. */
export function tokenExpiresAt(token: string): number | null {
  try {
    const payload = token.split(".")[1];
    const json = JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/")));
    return typeof json.exp === "number" ? json.exp * 1000 : null;
  } catch {
    return null;
  }
}

function isPublicPath(pathname: string) {
  return pathname === "/" ? false : PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

/** `/login`, remembering the current page so the user comes back to it after logging in. */
export function loginUrl(): string {
  if (typeof window === "undefined") return "/login";
  const { pathname, search } = window.location;
  if (pathname === "/" || isPublicPath(pathname)) return "/login";
  return `/login?next=${encodeURIComponent(pathname + search)}`;
}

/**
 * Only same-origin paths are accepted as a post-login destination, so a crafted
 * `?next=https://evil.example` link cannot bounce the user off-site.
 */
export function safeNextPath(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/login") ? next : "/dashboard";
}

/**
 * End the session because it is no longer valid (expired, revoked, 401).
 *
 * A full navigation rather than a router push: it also drops every cached
 * query of the old session, and it works from outside React (lib/api.ts).
 */
export function expireSession() {
  if (typeof window === "undefined" || expiring) return;
  const hadSession = useAuthStore.getState().token !== null;
  useAuthStore.getState().clearAuth();
  if (isPublicPath(window.location.pathname)) return;

  expiring = true;
  if (hadSession) {
    try {
      sessionStorage.setItem(EXPIRED_FLAG, "1");
    } catch {
      // Only costs the "session expired" notice on the login page.
    }
  }
  window.location.replace(loginUrl());
}

/** True once, right after `expireSession` sent the user to the login page. */
export function consumeExpiredFlag(): boolean {
  try {
    const expired = sessionStorage.getItem(EXPIRED_FLAG) === "1";
    sessionStorage.removeItem(EXPIRED_FLAG);
    return expired;
  } catch {
    return false;
  }
}
