"use client";

import { useQuery } from "@tanstack/react-query";
import { projectsApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store/auth";
import type { ProjectRef } from "@/types/api";

/** `GET /projects?include=folders`, shared by the upload form, /jobs and /api-keys. */
export function useProjects({ refetchInterval }: { refetchInterval?: number } = {}) {
  const token = useAuthStore((state) => state.token);
  return useQuery({
    queryKey: ["projects", token],
    queryFn: () => projectsApi.list(true),
    enabled: !!token,
    staleTime: 30_000,
    refetchInterval,
  });
}

// The last project this user uploaded to. It is the only thing the upload form
// may start with besides the URL: the form never picks a project on its own.
const lastProjectKey = (userId: string) => `ingestify:last-project:${userId}`;

export function readLastProject(userId: string): ProjectRef | null {
  try {
    const raw = localStorage.getItem(lastProjectKey(userId));
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return typeof parsed?.id === "string" && typeof parsed?.name === "string"
      ? { id: parsed.id, name: parsed.name }
      : null;
  } catch {
    return null;
  }
}

export function writeLastProject(userId: string, project: ProjectRef) {
  try {
    localStorage.setItem(lastProjectKey(userId), JSON.stringify({ id: project.id, name: project.name }));
  } catch {
    // Storage blocked: the form simply starts empty next time.
  }
}

export function forgetLastProject(userId: string) {
  try {
    localStorage.removeItem(lastProjectKey(userId));
  } catch {
    // Nothing to do.
  }
}
