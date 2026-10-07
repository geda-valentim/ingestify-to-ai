"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { authApi } from "@/lib/api";
import { adminSectionsFor } from "@/lib/admin-nav";
import { useAuthStore } from "@/lib/store/auth";

/**
 * /admin opens the first section the viewer may see (spec 0014 §4.10); with none,
 * the layout already renders the forbidden card. It waits for the layout's fresh
 * `/auth/me` (same query key, deduplicated): the stored profile may predate a
 * grant, revoke or demotion.
 */
export default function AdminIndex() {
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const me = useQuery({
    queryKey: ["auth-me", token],
    queryFn: () => authApi.me(),
    enabled: !!token,
    staleTime: 5 * 60 * 1000,
  });
  const first = me.data ? adminSectionsFor(me.data)[0] : undefined;
  useEffect(() => {
    if (first) router.replace(first);
  }, [first, router]);
  return null;
}
