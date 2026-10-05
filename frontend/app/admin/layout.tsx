"use client";

import { useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Activity, Cpu, MemoryStick, Route, Server } from "lucide-react";
import { authApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store/auth";
import { loginUrl } from "@/lib/session";
import { cn } from "@/lib/utils";
import { AppHeader } from "@/components/app-header";
import { ForbiddenCard, LoadingCards } from "@/components/admin/compute-ui";

const TABS = [
  { href: "/admin/engines", label: "Engines", icon: Server },
  { href: "/admin/gpus", label: "GPUs", icon: MemoryStick },
  { href: "/admin/routing", label: "Routing", icon: Route },
  { href: "/admin/status", label: "Status", icon: Activity },
];

/**
 * The Compute area (spec 0003, slice 5): read-only views of engines, GPUs, routes and
 * the dispatcher. The guard here is cosmetic; every /admin endpoint checks
 * `require_admin` itself, and a 403 from any of them renders the same card.
 */
export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const setAuth = useAuthStore((s) => s.setAuth);
  const hasHydrated = useAuthStore((s) => s._hasHydrated);
  const isAuthenticated = token !== null && user !== null;

  useEffect(() => {
    if (hasHydrated && !isAuthenticated) router.replace(loginUrl());
  }, [hasHydrated, isAuthenticated, router]);

  // The stored user may predate `is_admin` or a promotion/demotion: ask the API.
  const me = useQuery({
    queryKey: ["auth-me", token],
    queryFn: () => authApi.me(),
    enabled: !!token,
    staleTime: 5 * 60 * 1000,
  });

  useEffect(() => {
    if (me.data && token && me.data.is_admin !== user?.is_admin) setAuth(me.data, token);
  }, [me.data, token, user?.is_admin, setAuth]);

  const isAdmin = me.data?.is_admin ?? user?.is_admin;

  let body: React.ReactNode;
  if (!hasHydrated || !isAuthenticated || (isAdmin === undefined && me.isLoading)) {
    body = <LoadingCards label="Checking access" />;
  } else if (!isAdmin) {
    body = <ForbiddenCard />;
  } else {
    body = (
      <>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-3xl font-bold flex items-center gap-2">
              <Cpu className="h-8 w-8" aria-hidden />
              Compute
            </h1>
            <p className="text-muted-foreground mt-1">
              Where heavy work runs. Read-only: each screen shows the command that changes it.
            </p>
          </div>
        </div>
        <nav aria-label="Compute sections" className="flex flex-wrap gap-1 rounded-lg bg-muted p-1 w-fit">
          {TABS.map(({ href, label, icon: Icon }) => {
            const active = pathname === href || pathname.startsWith(`${href}/`);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  active ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
                )}
              >
                <Icon className="h-4 w-4" aria-hidden />
                {label}
              </Link>
            );
          })}
        </nav>
        {children}
      </>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-background via-background to-muted">
      <AppHeader />
      <main className="container mx-auto px-4 py-8 sm:py-12">
        <div className="max-w-6xl mx-auto space-y-6">{body}</div>
      </main>
    </div>
  );
}
