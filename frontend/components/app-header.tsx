"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import * as Dialog from "@radix-ui/react-dialog";
import { useQuery } from "@tanstack/react-query";
import {
  LayoutDashboard,
  BookOpen,
  ChevronDown,
  Cpu,
  Key,
  Menu,
  Mic,
  LogIn,
  LogOut,
  Search,
  Upload as UploadIcon,
  UserRound,
  X,
} from "lucide-react";
import { authApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store/auth";
import { Button } from "@/components/ui/button";
import { Brand } from "@/components/brand";
import { cn } from "@/lib/utils";

type NavLink = { href: string; label: string; icon: typeof UploadIcon };

const PRIMARY_LINKS: NavLink[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/convert", label: "Convert", icon: UploadIcon },
  { href: "/live", label: "Live", icon: Mic },
  { href: "/jobs", label: "My Jobs", icon: Search },
];
const DOCS_LINK: NavLink = { href: "/docs", label: "Docs", icon: BookOpen };
const LINK_STYLE =
  "flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

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
  const [mobileOpen, setMobileOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
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
    if (
      profile.is_admin !== user.is_admin ||
      profile.username !== user.username ||
      profile.email !== user.email ||
      JSON.stringify(profile.permissions) !==
        JSON.stringify(user.permissions) ||
      profile.engine_access_enabled !== user.engine_access_enabled
    ) {
      setAuth(profile, token);
    }
  }, [profile, token, user, setAuth]);

  useEffect(() => {
    setMobileOpen(false);
    setAccountOpen(false);
  }, [pathname, user?.id]);

  // A drawer opened on a phone must release its focus trap after resizing.
  useEffect(() => {
    const desktop = window.matchMedia("(min-width: 1280px)");
    const closeOnResize = () => {
      setMobileOpen(false);
      setAccountOpen(false);
    };
    desktop.addEventListener("change", closeOnResize);
    return () => desktop.removeEventListener("change", closeOnResize);
  }, []);

  const handleLogout = () => {
    setMobileOpen(false);
    setAccountOpen(false);
    clearAuth();
    router.push("/login");
  };

  const isActive = (href: string) =>
    pathname === href || pathname.startsWith(`${href}/`);
  const accountLinks: NavLink[] = [
    { href: "/api-keys", label: "API Keys", icon: Key },
    ...(user?.is_admin === true || !!user?.permissions?.length
      ? [{ href: "/admin", label: "Admin", icon: Cpu }]
      : []),
  ];
  const renderLink = (
    { href, label, icon: Icon }: NavLink,
    close?: () => void,
  ) => (
    <Link
      key={href}
      href={href}
      onClick={close}
      aria-current={isActive(href) ? "page" : undefined}
      className={cn(
        LINK_STYLE,
        isActive(href)
          ? "bg-secondary text-secondary-foreground"
          : "text-muted-foreground",
      )}
    >
      <Icon aria-hidden="true" className="h-4 w-4 shrink-0" />
      {label}
    </Link>
  );

  return (
    <header
      className={cn(
        "border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60",
        className,
      )}
    >
      <div className="container mx-auto flex h-16 items-center gap-6 px-4">
        <Link
          href={user ? "/dashboard" : "/login"}
          className="flex shrink-0 items-center gap-2 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Brand />
        </Link>

        {user && (
          <nav
            aria-label="Main navigation"
            className="hidden items-center gap-1 xl:flex"
          >
            {PRIMARY_LINKS.map((link) => renderLink(link))}
          </nav>
        )}

        <div className="ml-auto hidden items-center gap-3 xl:flex">
          {renderLink(DOCS_LINK)}
          {user ? (
            <DropdownMenu.Root open={accountOpen} onOpenChange={setAccountOpen}>
              <DropdownMenu.Trigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  className="gap-2"
                  aria-label={`Account menu for ${user.username}`}
                >
                  <UserRound aria-hidden="true" className="h-4 w-4" />
                  <span className="max-w-32 truncate">{user.username}</span>
                  <ChevronDown aria-hidden="true" className="h-3 w-3" />
                </Button>
              </DropdownMenu.Trigger>
              <DropdownMenu.Portal>
                <DropdownMenu.Content
                  align="end"
                  sideOffset={8}
                  className="z-50 min-w-56 rounded-lg border bg-popover p-1 text-popover-foreground shadow-md"
                >
                  <DropdownMenu.Label className="max-w-72 truncate px-3 py-2 text-xs text-muted-foreground">
                    {user.email}
                  </DropdownMenu.Label>
                  {accountLinks.map((link) => (
                    <DropdownMenu.Item
                      key={link.href}
                      asChild
                      className="data-[highlighted]:bg-accent data-[highlighted]:text-accent-foreground"
                    >
                      {renderLink(link)}
                    </DropdownMenu.Item>
                  ))}
                  <DropdownMenu.Separator className="my-1 h-px bg-border" />
                  <DropdownMenu.Item
                    onSelect={handleLogout}
                    className={cn(
                      LINK_STYLE,
                      "cursor-pointer outline-none data-[highlighted]:bg-accent",
                    )}
                  >
                    <LogOut aria-hidden="true" className="h-4 w-4" /> Logout
                  </DropdownMenu.Item>
                </DropdownMenu.Content>
              </DropdownMenu.Portal>
            </DropdownMenu.Root>
          ) : (
            <Button asChild variant="ghost" size="sm">
              <Link href="/login">
                <LogIn aria-hidden="true" className="mr-2 h-4 w-4" />
                Login
              </Link>
            </Button>
          )}
        </div>

        <Dialog.Root open={mobileOpen} onOpenChange={setMobileOpen}>
          <Dialog.Trigger asChild>
            <Button
              variant="ghost"
              size="sm"
              className="ml-auto gap-2 xl:hidden"
            >
              <Menu aria-hidden="true" className="h-5 w-5" />
              Menu
            </Button>
          </Dialog.Trigger>
          <Dialog.Portal>
            <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
            <Dialog.Content
              aria-describedby={undefined}
              className="fixed inset-y-0 right-0 z-50 flex w-80 max-w-[90vw] flex-col overflow-y-auto border-l bg-background p-4 shadow-xl"
            >
              <div className="mb-5 flex h-8 items-center justify-between">
                <Dialog.Title className="text-lg font-semibold">
                  Menu
                </Dialog.Title>
                <Dialog.Close asChild>
                  <Button variant="ghost" size="icon" aria-label="Close menu">
                    <X aria-hidden="true" className="h-5 w-5" />
                  </Button>
                </Dialog.Close>
              </div>
              <nav aria-label="Mobile navigation" className="space-y-1">
                {user &&
                  PRIMARY_LINKS.map((link) =>
                    renderLink(link, () => setMobileOpen(false)),
                  )}
                {renderLink(DOCS_LINK, () => setMobileOpen(false))}
              </nav>
              <div className="mt-5 space-y-1 border-t pt-4">
                {user ? (
                  <>
                    <p className="truncate px-3 pb-2 text-sm font-medium">
                      {user.username}
                    </p>
                    {accountLinks.map((link) =>
                      renderLink(link, () => setMobileOpen(false)),
                    )}
                    <button
                      type="button"
                      onClick={handleLogout}
                      className={cn(LINK_STYLE, "w-full text-muted-foreground")}
                    >
                      <LogOut aria-hidden="true" className="h-4 w-4" />
                      Logout
                    </button>
                  </>
                ) : (
                  renderLink(
                    { href: "/login", label: "Login", icon: LogIn },
                    () => setMobileOpen(false),
                  )
                )}
              </div>
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>
      </div>
    </header>
  );
}
