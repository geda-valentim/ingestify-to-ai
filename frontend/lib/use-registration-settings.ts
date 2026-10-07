"use client";

import { useQuery } from "@tanstack/react-query";
import { platformSettingsApi } from "@/lib/api";

export function useRegistrationSettings() {
  return useQuery({
    queryKey: ["registration-settings"],
    queryFn: platformSettingsApi.registration,
    staleTime: 0,
    refetchOnMount: "always",
    refetchInterval: 30_000,
    retry: 1,
  });
}
