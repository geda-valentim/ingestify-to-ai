"use client";

import { useEffect, useRef } from "react";
import { authApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store/auth";
import { expireSession, tokenExpiresAt } from "@/lib/session";

// How often the session is checked while a tab is open.
const TICK_MS = 60_000;
// Renew once less than this is left on the token...
const REFRESH_WHEN_REMAINING_MS = 15 * 60_000;
// ...but only for someone who used the app recently. An idle tab is left to
// expire, so walking away still ends the session.
const ACTIVE_WITHIN_MS = 30 * 60_000;
// End the session slightly early rather than fire requests that will 401.
const EXPIRY_MARGIN_MS = 5_000;

/**
 * Keeps the login session honest, from any page:
 *
 * - renews the JWT (POST /auth/refresh) while the user is active, so working
 *   in the app never gets interrupted by the 60-minute token lifetime;
 * - ends the session and sends the user to /login (and back afterwards) once
 *   the token has expired, instead of leaving pages spinning on 401s;
 * - keeps tabs in step: logging in, out or renewing in one tab applies to all.
 *
 * Renders nothing.
 */
export function SessionHeartbeat() {
  const lastActivity = useRef(Date.now());
  const refreshing = useRef(false);

  useEffect(() => {
    const markActive = () => {
      lastActivity.current = Date.now();
    };

    const tick = async () => {
      const token = useAuthStore.getState().token;
      if (!token) return;

      const expiresAt = tokenExpiresAt(token);
      if (expiresAt === null) return;

      const now = Date.now();
      if (now >= expiresAt - EXPIRY_MARGIN_MS) {
        expireSession();
        return;
      }

      const recentlyActive = now - lastActivity.current < ACTIVE_WITHIN_MS;
      if (expiresAt - now < REFRESH_WHEN_REMAINING_MS && recentlyActive && !refreshing.current) {
        refreshing.current = true;
        try {
          const { access_token } = await authApi.refresh();
          // Only replace the token this refresh was for: a logout or another
          // login may have happened while the request was in flight.
          if (useAuthStore.getState().token === token) {
            useAuthStore.getState().setToken(access_token);
          }
        } catch {
          // A 401 already ended the session (lib/api.ts). Anything else is a
          // network blip: the next tick tries again while time remains.
        } finally {
          refreshing.current = false;
        }
      }
    };

    const onVisible = () => {
      if (document.visibilityState === "visible") {
        markActive();
        tick();
      }
    };

    // Another tab logged in, out or renewed: pick up its session.
    const onStorage = (e: StorageEvent) => {
      if (e.key === "auth-storage") useAuthStore.persist.rehydrate();
    };

    const activityEvents = ["pointerdown", "keydown", "scroll", "touchstart"] as const;
    activityEvents.forEach((ev) => window.addEventListener(ev, markActive, { passive: true }));
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onVisible);
    window.addEventListener("storage", onStorage);

    tick();
    const interval = setInterval(tick, TICK_MS);

    return () => {
      clearInterval(interval);
      activityEvents.forEach((ev) => window.removeEventListener(ev, markActive));
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onVisible);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  return null;
}
