"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { adminSectionsFor } from "@/lib/admin-nav";
import { useAuthStore } from "@/lib/store/auth";

/**
 * /admin opens the first section the viewer may see (spec 0014 §4.10); with none,
 * the layout already renders the forbidden card.
 */
export default function AdminIndex() {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const first = adminSectionsFor(user)[0];
  useEffect(() => {
    if (first) router.replace(first);
  }, [first, router]);
  return null;
}
