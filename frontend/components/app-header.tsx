"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { BookOpen, Cpu, FileText, Key, LogIn, LogOut, Search, Upload as UploadIcon } from "lucide-react";
import { authApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store/auth";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type NavLink = { href: string; label: string; icon: typeof UploadIcon; public?: boolean; admin?: boolean };

const NAV_LINKS: NavLink[] = [
  { href: "/dashboard", label: "Upload", icon: UploadIcon },
  { href: "/jobs", label: "My Jobs", icon: Search },
  { href: "/api-keys", label: "API Keys", icon: Key },
  // Engines, GPUs and routes (spec 0003); the API enforces admin, this only hides the link.
  { href: "/admin", label: "Compute", icon: Cpu, admin: true },
  { href: "/docs", label: "Docs", icon: BookOpen, public: true },
];

/**
 * Header shared by every authenticated page, so the navigation is the same
 * wherever the user is. `/jobs/{id}` counts as "My Jobs". Logged out (only
 * possible on the public /docs page) it shows just the public links and Login.
 */
export function AppHeader({ className }: { className?: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const user = useAuthStore((state) => state.user);
  const clearAuth = useAuthStore((state) => state.clearAuth);
  const token = useAuthStore((state) => state.token);
  const setAuth = useAuthStore((state) => state.setAuth);

  // The saved session can be stale - a user promoted to admin (or demoted) after
  // logging in, or a session saved before `is_admin` existed: re-read the profile
  // (cached 5 min, again on window focus) and keep the store in step with it.
  const { data: profile } = useQuery({
    queryKey: ["auth-me", token],
    queryFn: () => authApi.me(),
    enabled: !!token && !!user,
    staleTime: 5 * 60 * 1000,
  });
  useEffect(() => {
    if (!profile || !token || !user) return;
    if (profile.is_admin !== user.is_admin || profile.username !== user.username || profile.email !== user.email) {
      setAuth(profile, token);
    }
  }, [profile, token, user, setAuth]);

  const handleLogout = () => {
    clearAuth();
    router.push("/login");
  };

  const isActive = (href: string) => pathname === href || pathname.startsWith(`${href}/`);

  return (
    <header
      className={cn(
        "border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60",
        className
      )}
    >
      <div className="container mx-auto px-4 py-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <Link href={user ? "/dashboard" : "/login"} className="flex items-center space-x-2">
            <FileText className="h-6 w-6 text-primary" />
            <span className="text-2xl font-bold">Ingestify</span>
          </Link>
          <nav className="flex flex-wrap items-center gap-2 sm:gap-4">
            {user && (
              <span className="hidden text-sm text-muted-foreground md:inline">
                Welcome, <span className="font-medium text-foreground">{user.username}</span>
              </span>
            )}
            {NAV_LINKS.filter((link) => (link.admin ? user?.is_admin === true : user || link.public)).map(({ href, label, icon: Icon }) => (
              <Button
                key={href}
                asChild
                variant={isActive(href) ? "secondary" : "outline"}
                size="sm"
              >
                <Link href={href} aria-current={isActive(href) ? "page" : undefined}>
                  <Icon className="h-4 w-4 mr-2" />
                  {label}
                </Link>
              </Button>
            ))}
            {user ? (
              <Button variant="ghost" size="sm" onClick={handleLogout}>
                <LogOut className="h-4 w-4 mr-2" />
                Logout
              </Button>
            ) : (
              <Button asChild variant="ghost" size="sm">
                <Link href="/login">
                  <LogIn className="h-4 w-4 mr-2" />
                  Login
                </Link>
              </Button>
            )}
          </nav>
        </div>
      </div>
    </header>
  );
}
