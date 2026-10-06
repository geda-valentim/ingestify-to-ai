"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  FileText,
  Loader2,
  Plus,
  Search,
} from "lucide-react";
import { format, formatDistanceToNow } from "date-fns";
import { jobsApi, tagsApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store/auth";
import { loginUrl } from "@/lib/session";
import { cn, formatApiError, parseApiDate } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";
import { AppHeader } from "@/components/app-header";
import { JobsFilters, STATUS_TABS, KINDS } from "./filters";
import { JobRow } from "./job-row";
import { JobTagEditor } from "./tag-editor";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useProjects } from "@/components/projects/use-projects";
import {
  ProjectSelects,
  ProjectSidebar,
  ROOT_FOLDER,
  filterProject,
  filterTitle,
  type LocationFilter,
} from "@/components/projects/project-sidebar";
import type { JobListItem } from "@/types/api";

const PAGE_SIZE = 20;

function relative(date?: string | null) {
  if (!date) return null;
  const d = parseApiDate(date);
  return isNaN(d.getTime()) ? null : { text: formatDistanceToNow(d, { addSuffix: true }), full: format(d, "PPpp") };
}

export default function JobsPage() {
  // useSearchParams needs a Suspense boundary in the App Router.
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      }
    >
      <JobsList />
    </Suspense>
  );
}

function JobsList() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const token = useAuthStore((state) => state.token);
  const isAuthenticated = useAuthStore((state) => state.token !== null && state.user !== null);
  const hasHydrated = useAuthStore((state) => state._hasHydrated);

  // Filters live in the URL: back/forward, reload and shared links all keep them.
  const status = STATUS_TABS.find(item => item.value === searchParams.get("status"))?.value ?? "all";
  const kind = KINDS.find(item => item.value === searchParams.get("kind"))?.value ?? "all";
  const tags = [...new Set(searchParams.getAll("tag").filter(Boolean))];
  const q = searchParams.get("q") ?? "";
  const contentMode = searchParams.get("in") === "content";
  const requestedPage = Number(searchParams.get("page") ?? 1);
  const page = Number.isSafeInteger(requestedPage) && requestedPage >= 1 && requestedPage <= 1_000_000 ? requestedPage - 1 : 0;
  const paramsRef = useRef(searchParams);
  paramsRef.current = searchParams;
  const projectId = searchParams.get("project_id");
  const folderId = searchParams.get("folder_id");
  const location: LocationFilter = { projectId, folderId };

  const [searchDraft, setSearchDraft] = useState(q);
  const [jobToTag, setJobToTag] = useState<JobListItem | null>(null);
  const [jobToDelete, setJobToDelete] = useState<JobListItem | null>(null);

  useEffect(() => {
    if (hasHydrated && !isAuthenticated) router.replace(loginUrl());
  }, [isAuthenticated, hasHydrated, router]);

  const setParams = (updates: Record<string, string | string[] | null>, { replace = false } = {}) => {
    const next = new URLSearchParams(paramsRef.current.toString());
    for (const [key, value] of Object.entries(updates)) {
      next.delete(key);
      if (Array.isArray(value)) value.forEach((v) => next.append(key, v));
      else if (value) next.set(key, value);
    }
    // Any filter change starts again from the first page.
    if (!("page" in updates)) next.delete("page");
    const url = `/jobs${next.toString() ? `?${next}` : ""}`;
    if (replace) router.replace(url, { scroll: false });
    else router.push(url, { scroll: false });
  };

  // Typing updates the URL after a pause, without a history entry per key.
  useEffect(() => {
    if (searchDraft.trim() === q) return;
    const t = setTimeout(() => setParams({ q: searchDraft.trim() || null }, { replace: true }), 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchDraft]);

  useEffect(() => setSearchDraft(q), [q]);

  const jobsQuery = useQuery({
    queryKey: ["jobs", { status, kind, tags, q, page, projectId, folderId }, token],
    queryFn: () =>
      jobsApi.list({
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
        status: status === "all" ? undefined : status,
        kind: kind === "all" ? undefined : kind,
        tags,
        q: q || undefined,
        project_id: projectId ?? undefined,
        folder_id: folderId ?? undefined,
        job_type: "main",
      }),
    enabled: !!token && !contentMode,
    placeholderData: keepPreviousData,
    retry: 1,
    // Poll fast only while something on screen is still moving.
    refetchInterval: (query) =>
      query.state.data?.jobs.some((j) => j.status === "queued" || j.status === "processing") ? 3000 : 30000,
  });

  const contentSearch = useQuery({
    queryKey: ["search", q, token],
    queryFn: () => jobsApi.search({ query: q, limit: 100 }),
    enabled: !!token && contentMode && q.length > 0,
    retry: 1,
  });

  // Counts move as jobs arrive; refresh them at the slow list cadence.
  const projectsQuery = useProjects({ refetchInterval: 30_000 });
  const projects = projectsQuery.data?.projects ?? [];
  const title = filterTitle(projects, location);
  const currentProjectId = projectId ?? filterProject(projects, location)?.id ?? null;
  const selectLocation = (next: LocationFilter) =>
    setParams({ project_id: next.projectId, folder_id: next.folderId });
  // "New conversion" from inside a project starts there (an explicit choice, so allowed).
  const uploadHref = (() => {
    const params = new URLSearchParams();
    if (currentProjectId) params.set("project_id", currentProjectId);
    if (currentProjectId && folderId && folderId !== ROOT_FOLDER) params.set("folder_id", folderId);
    return `/convert${params.toString() ? `?${params}` : ""}`;
  })();

  const tagsQuery = useQuery({
    queryKey: ["tags", token],
    queryFn: () => tagsApi.list(),
    enabled: !!token,
    staleTime: 60_000,
  });

  const deleteMutation = useMutation({
    mutationFn: (jobId: string) => jobsApi.delete(jobId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.invalidateQueries({ queryKey: ["tags"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-jobs"] });
      toast({ title: "Job deleted", description: "The job and its files were removed." });
      setJobToDelete(null);
    },
    onError: (error) => {
      toast({ title: "Error deleting job", description: formatApiError(error), variant: "destructive" });
    },
  });

  const data = jobsQuery.data;
  const jobs = data?.jobs ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const toggleTag = (tag: string) =>
    setParams({ tag: tags.includes(tag) ? tags.filter((t) => t !== tag) : [...tags, tag] });
  const hasListFilters = status !== "all" || kind !== "all" || tags.length > 0 || q.length > 0;
  const resetFilters = () => {
    setSearchDraft("");
    setParams({ status: null, kind: null, tag: null, q: null });
  };
  // Deletion and filter changes can make a bookmarked page fall out of range.
  useEffect(() => {
    if (!contentMode && data && !jobsQuery.isPlaceholderData && !jobsQuery.isError && page >= totalPages) {
      setParams({ page: totalPages > 1 ? String(totalPages) : null }, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contentMode, data, jobsQuery.isPlaceholderData, jobsQuery.isError, page, totalPages]);
  if (!hasHydrated || !isAuthenticated) return <div className="flex min-h-screen items-center justify-center text-muted-foreground">Loading jobs…</div>;

  return (
    <div className="min-h-screen bg-background">
      <AppHeader />

      <main className="container mx-auto px-4 py-8">
        <div className="max-w-7xl mx-auto space-y-6">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div className="min-w-0">
              <Link href="/dashboard" className="mb-3 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"><ChevronLeft className="h-3 w-3" />Workspace</Link>
              <h1 className="text-3xl font-semibold tracking-tight">Jobs</h1>
              <p className="mt-2 text-sm text-muted-foreground">Track conversions. Organize results. Find the data you need.</p>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" aria-label="Refresh results" disabled={contentMode ? contentSearch.isFetching || !q : jobsQuery.isFetching} onClick={() => { if (contentMode) contentSearch.refetch(); else { jobsQuery.refetch(); projectsQuery.refetch(); } }}><RefreshCw className={cn("h-4 w-4", (contentMode ? contentSearch.isFetching : jobsQuery.isFetching) && "animate-spin")} /></Button>
              <Button asChild><Link href={contentMode ? "/convert" : uploadHref}><Plus className="mr-2 h-4 w-4" />New conversion</Link></Button>
            </div>
          </div>

          <div className={cn(!contentMode && "lg:grid lg:grid-cols-[13rem_minmax(0,1fr)] lg:gap-6")}>
            {/* Project navigation on desktop */}
            {!contentMode && <aside className="hidden lg:block">
              <div className="sticky top-20 max-h-[calc(100vh-6rem)] overflow-y-auto rounded-xl border bg-background p-2">
                <ProjectSidebar
                  projects={projects}
                  isLoading={projectsQuery.isLoading}
                  error={projectsQuery.isError ? formatApiError(projectsQuery.error) : null}
                  filter={location}
                  onSelect={selectLocation}
                />
              </div>
            </aside>}

            <div className="flex min-w-0 flex-col gap-5">
              {/* Compact project navigation on smaller screens */}
              {!contentMode && projects.length > 0 && (
                <div className="lg:hidden">
                  <ProjectSelects projects={projects} filter={location} onSelect={selectLocation} />
                </div>
              )}

              {!contentMode && (projectId || folderId) && <nav aria-label="Job location" className="flex min-w-0 flex-wrap items-center gap-2 text-sm">
                <button type="button" onClick={() => selectLocation({ projectId: null, folderId: null })} className="text-muted-foreground hover:underline">All jobs</button><ChevronRight className="h-3 w-3 text-muted-foreground" />
                <button type="button" onClick={() => selectLocation({ projectId: currentProjectId, folderId: null })} className="max-w-full truncate font-medium hover:underline">{title?.project ?? "Selected project"}</button>
                {folderId && <><ChevronRight className="h-3 w-3 text-muted-foreground" /><span className="max-w-full truncate">{title?.folder ?? "Selected folder"}</span></>}
              </nav>}
              <JobsFilters
                draft={searchDraft} onDraft={setSearchDraft} onSearch={() => setParams({ q: searchDraft.trim() || null })}
                contentMode={contentMode} onMode={value => setParams({ in: value ? "content" : null })}
                status={status} kind={kind} tags={tags} counts={data?.counts}
                knownTags={tagsQuery.data ?? []} tagsLoading={tagsQuery.isLoading} tagsError={tagsQuery.isError} retryTags={() => tagsQuery.refetch()}
                onStatus={value => setParams({ status: value === "all" ? null : value })}
                onKind={value => setParams({ kind: value === "all" ? null : value })}
                onTag={toggleTag} onClear={resetFilters} hasFilters={hasListFilters}
              />
              {!contentMode && <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground" aria-live="polite">
                <span>{jobsQuery.isLoading ? "Loading jobs…" : data ? `${total.toLocaleString()} job${total === 1 ? "" : "s"}${hasListFilters ? " matching filters" : ""}` : "Jobs unavailable"}</span>
                <span className="flex items-center gap-1.5">{jobsQuery.isFetching && <Loader2 className="h-3 w-3 animate-spin" />}{jobsQuery.isFetching ? "Updating…" : "Newest first · auto-refresh"}</span>
              </div>}

              {!contentMode && projectsQuery.isError && <div role="alert" className="flex flex-wrap items-center gap-2 text-xs text-destructive lg:hidden">Project navigation could not load. <button type="button" className="underline" onClick={() => projectsQuery.refetch()}>Retry projects</button></div>}
              {/* Results */}
              {contentMode ? (
                <ContentResults
                  q={q}
                  isLoading={contentSearch.isLoading}
                  error={contentSearch.error}
                  results={contentSearch.data?.results ?? []}
                  total={contentSearch.data?.total ?? 0}
                  onRetry={() => contentSearch.refetch()}
                />
              ) : jobsQuery.error ? (
                <div role="alert" className="rounded-xl border border-destructive/50 p-8 text-center text-destructive">
                  <p className="font-semibold">Could not load your jobs</p>
                  <p className="text-sm mt-1">{formatApiError(jobsQuery.error)}</p>
                  <Button variant="outline" className="mt-4" onClick={() => jobsQuery.refetch()}>Try again</Button>
                </div>
              ) : jobsQuery.isLoading ? (
                <div className="rounded-xl border bg-background divide-y">
                  {Array.from({ length: 6 }).map((_, i) => (
                    <div key={i} className="flex items-center gap-4 p-4">
                      <div className="h-10 w-10 rounded-lg bg-muted animate-pulse" />
                      <div className="flex-1 space-y-2">
                        <div className="h-4 w-1/3 rounded bg-muted animate-pulse" />
                        <div className="h-3 w-1/2 rounded bg-muted animate-pulse" />
                      </div>
                    </div>
                  ))}
                </div>
              ) : jobs.length === 0 ? (
                <div className="rounded-xl border bg-background py-16 px-6 text-center">
                  <FileText className="h-12 w-12 mx-auto mb-4 text-muted-foreground/50" />
                  {hasListFilters ? (
                    <>
                      <p className="font-medium">No jobs match these filters</p>
                      <Button variant="link" onClick={resetFilters}>
                        Reset filters
                      </Button>
                    </>
                  ) : (
                    <>
                      <p className="font-medium">{projectId || folderId ? "No jobs in this location yet" : "No jobs yet"}</p>
                      <p className="text-sm text-muted-foreground mt-1">Upload a document, audio or video to get started.</p>
                      <Button asChild className="mt-4">
                        <Link href={uploadHref}>
                          <Plus className="h-4 w-4 mr-2" />
                          New conversion
                        </Link>
                      </Button>
                    </>
                  )}
                </div>
              ) : (
                <>
                  <ul
                    aria-label="Jobs" aria-busy={jobsQuery.isFetching} inert={jobsQuery.isPlaceholderData}
                    className={cn(
                      "rounded-xl border bg-background divide-y overflow-hidden transition-opacity",
                      jobsQuery.isPlaceholderData && "opacity-60"
                    )}
                  >
                    {jobs.map((job) => (
                      <JobRow
                        key={job.job_id}
                        job={job}
                        activeTags={tags}
                        onTag={toggleTag}
                        onDelete={() => setJobToDelete(job)}
                        onEditTags={() => setJobToTag(job)}
                        showProject={!projectId && !folderId}
                        showFolder={!folderId}
                        onLocation={selectLocation}
                      />
                    ))}
                  </ul>

                  {/* Pagination */}
                  <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
                    <span className="text-muted-foreground">
                      {page * PAGE_SIZE + 1}–{page * PAGE_SIZE + jobs.length} of {total}
                    </span>
                    {totalPages > 1 && (
                      <div className="flex items-center gap-1">
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={page === 0}
                          onClick={() => setParams({ page: page > 1 ? String(page) : null })}
                        >
                          <ChevronLeft className="h-4 w-4" />
                          <span className="sr-only">Previous page</span>
                        </Button>
                        {pageNumbers(page, totalPages).map((n, i) =>
                          n === null ? (
                            <span key={`gap-${i}`} className="px-2 text-muted-foreground">
                              …
                            </span>
                          ) : (
                            <Button
                              key={n}
                              aria-label={`Page ${n + 1}`} aria-current={n === page ? "page" : undefined}
                              variant={n === page ? "secondary" : "ghost"}
                              size="sm"
                              className="min-w-9"
                              onClick={() => setParams({ page: n > 0 ? String(n + 1) : null })}
                            >
                              {n + 1}
                            </Button>
                          )
                        )}
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={page >= totalPages - 1}
                          onClick={() => setParams({ page: String(page + 2) })}
                        >
                          <ChevronRight className="h-4 w-4" />
                          <span className="sr-only">Next page</span>
                        </Button>
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      </main>

      {jobToTag && <JobTagEditor key={jobToTag.job_id} job={jobToTag} onClose={() => setJobToTag(null)} />}
      <AlertDialog open={jobToDelete !== null} onOpenChange={(open) => { if (!open && !deleteMutation.isPending) setJobToDelete(null); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete “{jobToDelete?.name || jobToDelete?.job_id}”?</AlertDialogTitle>
            <AlertDialogDescription>
              This permanently removes the job, its pages, its result and its stored files. It cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteMutation.isPending}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={(event) => { event.preventDefault(); if (jobToDelete) deleteMutation.mutate(jobToDelete.job_id); }}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Deleting...
                </>
              ) : (
                "Delete"
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

/** 0-based page indexes to show, with `null` for a gap: 1 … 4 5 6 … 12 */
function pageNumbers(current: number, total: number): (number | null)[] {
  const pages = new Set([0, total - 1, current - 1, current, current + 1]);
  const sorted = Array.from(pages).filter((p) => p >= 0 && p < total).sort((a, b) => a - b);
  const out: (number | null)[] = [];
  sorted.forEach((p, i) => {
    if (i > 0 && p - sorted[i - 1] > 1) out.push(null);
    out.push(p);
  });
  return out;
}

function ContentResults({
  q,
  isLoading,
  error,
  results,
  total,
  onRetry,
}: {
  q: string;
  isLoading: boolean;
  error: unknown;
  total: number;
  onRetry: () => void;
  results: { job_id: string; filename?: string | null; total_pages?: number | null; created_at?: string | null; preview: string }[];
}) {
  if (!q) {
    return (
      <div className="rounded-xl border bg-background py-16 text-center text-muted-foreground">
        <Search className="h-10 w-10 mx-auto mb-3 opacity-50" />
        Type to search inside the text of your finished conversions.
      </div>
    );
  }
  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }
  if (error) {
    return (
      <div className="rounded-xl border border-destructive/50 p-8 text-center text-destructive">
        <p className="font-semibold">Search failed</p>
        <p className="text-sm mt-1">{formatApiError(error)}</p>
        <Button variant="outline" className="mt-4" onClick={onRetry}>Try again</Button>
      </div>
    );
  }
  if (results.length === 0) {
    return (
      <div className="rounded-xl border bg-background py-16 text-center">
        <p className="font-medium">Nothing inside your documents matches “{q}”</p>
        <p className="text-sm text-muted-foreground mt-1">Only finished conversions are searchable.</p>
      </div>
    );
  }
  return (
    <div className="space-y-3"><p className="text-xs text-muted-foreground">Showing {results.length} of {total} content matches{total > results.length ? ". Refine your search to narrow the results." : ""}</p><ul aria-label="Content matches" className="rounded-xl border bg-background divide-y overflow-hidden">
      {results.map((hit) => {
        const created = relative(hit.created_at);
        return (
          <li key={hit.job_id}>
            <Link href={`/jobs/${hit.job_id}`} className="block p-4 hover:bg-muted/40 transition-colors">
              <p className="font-medium truncate">{hit.filename || hit.job_id}</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                {[created?.text, hit.total_pages ? `${hit.total_pages} pages` : null].filter(Boolean).join(" · ")}
              </p>
              <p className="text-sm text-muted-foreground mt-2 line-clamp-2">{hit.preview}</p>
            </Link>
          </li>
        );
      })}
    </ul></div>
  );
}
