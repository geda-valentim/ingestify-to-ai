"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useMemo } from "react";
import { useAuthStore } from "@/lib/store/auth";
import { Toaster } from "@/components/ui/toaster";
import { SessionHeartbeat } from "@/components/session-heartbeat";

let nextCacheId = 0;

export function Providers({ children }: { children: React.ReactNode }) {
  const subject = useAuthStore((s) => s.user?.id);
  const authenticated = useAuthStore((s) => !!s.token);
  const queryClient = useMemo(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60 * 1000, // 1 minute
            refetchOnWindowFocus: false,
          },
        },
      }),
    [subject, authenticated],
  );
  const cacheKey = useMemo(() => ++nextCacheId, [queryClient]);
  // A different login gets a different cache before children render, with no
  // inherited admin data. Dispose requests and data belonging to the old session.
  // Token renewal keeps the same session mounted, preserving live capture/forms.
  useEffect(() => () => queryClient.clear(), [queryClient]);

  return (
    <QueryClientProvider key={cacheKey} client={queryClient}>
      <SessionHeartbeat />
      {children}
      <Toaster />
    </QueryClientProvider>
  );
}
