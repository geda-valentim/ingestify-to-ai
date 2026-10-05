"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronLeft,
  ChevronRight,
  FileText,
  Folder as FolderIcon,
  Image as ImageIcon,
  Loader2,
  Mic,
  Plus,
  Search,
  Trash2,
  X,
} from "lucide-react";
import { format, formatDistanceToNow } from "date-fns";
import { jobsApi, tagsApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store/auth";
import { loginUrl } from "@/lib/session";
import { cn, formatApiError, formatBytes, parseApiDate } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";
import { AppHeader } from "@/components/app-header";
import { TagChip } from "@/components/tag-input";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
import type { JobKind, JobListItem, JobStatus } from "@/types/api";

const PAGE_SIZE = 20;

const STATUS_TABS: { value: JobStatus | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "processing", label: "Processing" },
  { value: "queued", label: "Queued" },
  { value: "completed", label: "Completed" },
  { value: "failed", label: "Failed" },
];

const KINDS: { value: JobKind | "all"; label: string }[] = [
  { value: "all", label: "All types" },
  { value: "document", label: "Documents" },
  { value: "transcription", label: "Transcriptions" },
  { value: "image", label: "Images" },
];

const KIND_ICONS: Record<JobKind, React.ComponentType<{ className?: string }>> = {
  document: FileText,
  transcription: Mic,
  image: ImageIcon,
};

const STATUS_STYLES: Record<string, string> = {
  completed: "bg-green-500/10 text-green-700 dark:text-green-400 border-green-500/20",
  failed: "bg-red-500/10 text-red-700 dark:text-red-400 border-red-500/20",
  processing: "bg-blue-500/10 text-blue-700 dark:text-blue-400 border-blue-500/20",
  queued: "bg-yellow-500/10 text-yellow-700 dark:text-yellow-400 border-yellow-500/20",
  cancelled: "bg-muted text-muted-foreground",
};

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
  const status = (searchParams.get("status") as JobStatus | null) ?? "all";
  const kind = (searchParams.get("kind") as JobKind | null) ?? "all";
  const tags = searchParams.getAll("tag");
  const q = searchParams.get("q") ?? "";
  const contentMode = searchParams.get("in") === "content";
  const page = Math.max(0, Number(searchParams.get("page") ?? 1) - 1);
  const projectId = searchParams.get("project_id");
  const folderId = searchParams.get("folder_id");
  const location: LocationFilter = { projectId, folderId };

  const [searchDraft, setSearchDraft] = useState(q);
  const [jobToDelete, setJobToDelete] = useState<JobListItem | null>(null);

  useEffect(() => {
    if (hasHydrated && !isAuthenticated) router.replace(loginUrl());
  }, [isAuthenticated, hasHydrated, router]);

  const setParams = (updates: Record<string, string | string[] | null>, { replace = false } = {}) => {
    const next = new URLSearchParams(searchParams.toString());
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
    if (searchDraft === q) return;
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
    // Poll fast only while something on screen is still moving.
    refetchInterval: (query) =>
      query.state.data?.jobs.some((j) => j.status === "queued" || j.status === "processing") ? 3000 : 30000,
  });

  const contentSearch = useQuery({
    queryKey: ["search", q, token],
    queryFn: () => jobsApi.search({ query: q, limit: 100 }),
    enabled: !!token && contentMode && q.length > 0,
  });

  // Counts move as jobs arrive; refresh them at the slow list cadence.
  const projectsQuery = useProjects({ refetchInterval: 30_000 });
  const projects = projectsQuery.data?.projects ?? [];
  const title = filterTitle(projects, location);
  const currentProjectId = projectId ?? filterProject(projects, location)?.id ?? null;
  const selectLocation = (next: LocationFilter) =>
    setParams({ project_id: next.projectId, folder_id: next.folderId });
  // "New upload" from inside a project starts there (an explicit choice, so allowed).
  const uploadHref = (() => {
    const params = new URLSearchParams();
    if (currentProjectId) params.set("project_id", currentProjectId);
    if (currentProjectId && folderId && folderId !== ROOT_FOLDER) params.set("folder_id", folderId);
    return `/dashboard${params.toString() ? `?${params}` : ""}`;
  })();

  const { data: knownTags = [] } = useQuery({
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
  const hasFilters =
    status !== "all" || kind !== "all" || tags.length > 0 || q.length > 0 || !!projectId || !!folderId;
  const toggleTag = (tag: string) =>
    setParams({ tag: tags.includes(tag) ? tags.filter((t) => t !== tag) : [...tags, tag] });
  const suggestedTags = knownTags.filter((t) => !tags.includes(t.tag)).slice(0, 12);

  return (
    <div className="min-h-screen bg-gradient-to-br from-background via-background to-muted">
      <AppHeader />

      <main className="container mx-auto px-4 py-8">
        <div className="max-w-6xl mx-auto space-y-6">
          {/* Title */}
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div className="min-w-0">
              {projectId || folderId ? (
                <h1 className="flex flex-wrap items-center gap-x-2 text-3xl font-bold">
                  <button
                    type="button"
                    onClick={() => selectLocation({ projectId: null, folderId: null })}
                    className="text-muted-foreground hover:text-foreground"
                  >
                    My Jobs
                  </button>
                  <ChevronRight className="h-6 w-6 shrink-0 text-muted-foreground" aria-hidden />
                  {title?.folder ? (
                    <>
                      <button
                        type="button"
                        onClick={() => selectLocation({ projectId: currentProjectId, folderId: null })}
                        className="min-w-0 truncate text-muted-foreground hover:text-foreground"
                      >
                        {title.project}
                      </button>
                      <ChevronRight className="h-6 w-6 shrink-0 text-muted-foreground" aria-hidden />
                      <span className={cn("min-w-0 truncate", folderId === ROOT_FOLDER && "italic")}>{title.folder}</span>
                    </>
                  ) : (
                    <span className="min-w-0 truncate">{title?.project ?? "…"}</span>
                  )}
                </h1>
              ) : (
                <h1 className="text-3xl font-bold">My Jobs</h1>
              )}
              <p className="text-muted-foreground mt-1">
                {data ? `${data.counts.all} job${data.counts.all === 1 ? "" : "s"}` : "Your conversions and transcriptions"}
              </p>
            </div>
            <Button asChild>
              <Link href={uploadHref}>
                <Plus className="h-4 w-4 mr-2" />
                New upload
              </Link>
            </Button>
          </div>

          <div className="md:grid md:grid-cols-[13rem_minmax(0,1fr)] md:gap-6 lg:grid-cols-[15rem_minmax(0,1fr)]">
            {/* Projects: a column from md up */}
            <aside className="hidden md:block">
              <div className="sticky top-20 max-h-[calc(100vh-6rem)] overflow-y-auto rounded-xl border bg-background p-2">
                <ProjectSidebar
                  projects={projects}
                  isLoading={projectsQuery.isLoading}
                  error={projectsQuery.isError ? formatApiError(projectsQuery.error) : null}
                  filter={location}
                  onSelect={selectLocation}
                />
              </div>
            </aside>

            <div className="min-w-0 space-y-6">
              {/* Projects: two selects below md */}
              {projects.length > 0 && (
                <div className="md:hidden">
                  <ProjectSelects projects={projects} filter={location} onSelect={selectLocation} />
                </div>
              )}

              {/* Filters */}
              <div className="rounded-xl border bg-background p-4 space-y-4">
                <div className="flex flex-col md:flex-row gap-3">
                  <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      value={searchDraft}
                      onChange={(e) => setSearchDraft(e.target.value)}
                      placeholder={contentMode ? "Search inside converted content…" : "Search by name…"}
                      className="pl-9 pr-9"
                    />
                    {searchDraft && (
                      <button
                        type="button"
                        onClick={() => setSearchDraft("")}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                        aria-label="Clear search"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                  <div className="flex rounded-md border p-0.5 w-fit" role="group" aria-label="Search in">
                    {[
                      { value: false, label: "Names" },
                      { value: true, label: "Content" },
                    ].map((opt) => (
                      <button
                        key={opt.label}
                        type="button"
                        onClick={() => setParams({ in: opt.value ? "content" : null })}
                        aria-pressed={contentMode === opt.value}
                        className={cn(
                          "px-3 py-1.5 text-sm rounded-sm transition-colors",
                          contentMode === opt.value ? "bg-secondary font-medium" : "text-muted-foreground hover:text-foreground"
                        )}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>

                {!contentMode && (
                  <>
                    {/* Status tabs */}
                    <div className="flex items-center gap-x-1 overflow-x-auto whitespace-nowrap border-b -mx-4 px-4">
                      {STATUS_TABS.map((tab) => {
                        const active = status === tab.value;
                        const count = data?.counts?.[tab.value];
                        return (
                          <button
                            key={tab.value}
                            type="button"
                            onClick={() => setParams({ status: tab.value === "all" ? null : tab.value })}
                            className={cn(
                              "-mb-px border-b-2 px-3 pb-2 text-sm transition-colors",
                              active
                                ? "border-primary font-medium text-foreground"
                                : "border-transparent text-muted-foreground hover:text-foreground"
                            )}
                          >
                            {tab.label}
                            {count !== undefined && (
                              <span
                                className={cn(
                                  "ml-1.5 rounded-full px-1.5 py-0.5 text-xs tabular-nums",
                                  active ? "bg-primary text-primary-foreground" : "bg-muted"
                                )}
                              >
                                {count}
                              </span>
                            )}
                          </button>
                        );
                      })}
                    </div>

                    {/* Kind + tags */}
                    <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                      <div className="flex flex-wrap gap-1.5">
                        {KINDS.map((k) => (
                          <Button
                            key={k.value}
                            size="sm"
                            variant={kind === k.value ? "secondary" : "ghost"}
                            className="h-8"
                            onClick={() => setParams({ kind: k.value === "all" ? null : k.value })}
                          >
                            {k.label}
                          </Button>
                        ))}
                      </div>

                      {(tags.length > 0 || suggestedTags.length > 0) && (
                        <div className="flex flex-wrap items-center gap-1.5 lg:justify-end lg:max-w-[60%]">
                          <span className="text-xs text-muted-foreground mr-1">Tags:</span>
                          {tags.map((tag) => (
                            <TagChip key={tag} tag={tag} active onRemove={() => toggleTag(tag)} />
                          ))}
                          {suggestedTags.map((t) => (
                            <TagChip
                              key={t.tag}
                              tag={`${t.tag} · ${t.count}`}
                              onClick={() => toggleTag(t.tag)}
                              className="cursor-pointer"
                            />
                          ))}
                        </div>
                      )}
                    </div>

                    {hasFilters && (
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-muted-foreground">
                          {total} matching job{total === 1 ? "" : "s"}
                        </span>
                        <button
                          type="button"
                          onClick={() => {
                            setSearchDraft("");
                            router.push("/jobs");
                          }}
                          className="text-primary hover:underline underline-offset-4"
                        >
                          Clear all filters
                        </button>
                      </div>
                    )}
                  </>
                )}
              </div>

              {contentMode && (projectId || folderId) && (
                <p className="text-xs text-muted-foreground">Content search covers all your projects.</p>
              )}

              {/* Results */}
              {contentMode ? (
                <ContentResults
                  q={q}
                  isLoading={contentSearch.isLoading}
                  error={contentSearch.error}
                  results={contentSearch.data?.results ?? []}
                />
              ) : jobsQuery.error ? (
                <div className="rounded-xl border border-destructive/50 p-8 text-center text-destructive">
                  <p className="font-semibold">Could not load your jobs</p>
                  <p className="text-sm mt-1">{formatApiError(jobsQuery.error)}</p>
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
                  {hasFilters ? (
                    <>
                      <p className="font-medium">No jobs match these filters</p>
                      <Button variant="link" onClick={() => router.push("/jobs")}>
                        Clear all filters
                      </Button>
                    </>
                  ) : (
                    <>
                      <p className="font-medium">No jobs yet</p>
                      <p className="text-sm text-muted-foreground mt-1">Upload a document, audio or video to get started.</p>
                      <Button asChild className="mt-4">
                        <Link href="/dashboard">
                          <Plus className="h-4 w-4 mr-2" />
                          New upload
                        </Link>
                      </Button>
                    </>
                  )}
                </div>
              ) : (
                <>
                  <ul
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

      <AlertDialog open={jobToDelete !== null} onOpenChange={(open) => !open && setJobToDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete “{jobToDelete?.name || jobToDelete?.job_id}”?</AlertDialogTitle>
            <AlertDialogDescription>
              This permanently removes the job, its pages, its result and its stored files. It cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => jobToDelete && deleteMutation.mutate(jobToDelete.job_id)}
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

function JobRow({
  job,
  activeTags,
  onTag,
  onDelete,
  showProject,
  showFolder,
  onLocation,
}: {
  job: JobListItem;
  activeTags: string[];
  onTag: (tag: string) => void;
  onDelete: () => void;
  /** Off once the list is filtered to one project (every row would say the same). */
  showProject: boolean;
  showFolder: boolean;
  onLocation: (filter: LocationFilter) => void;
}) {
  const router = useRouter();
  const Icon = KIND_ICONS[job.kind] ?? FileText;
  const created = relative(job.created_at);
  const href = `/jobs/${job.job_id}`;
  const running = job.status === "processing" || job.status === "queued";
  const title = job.name || job.filename || job.job_id;

  const meta = [
    job.filename && job.filename !== title ? job.filename : null,
    job.file_size_bytes ? formatBytes(job.file_size_bytes) : null,
    job.total_pages ? `${job.pages_completed ?? 0}/${job.total_pages} pages` : null,
  ].filter(Boolean);

  return (
    <li
      className="group relative flex flex-col gap-3 p-4 hover:bg-muted/40 transition-colors cursor-pointer sm:flex-row sm:items-center"
      onClick={(e) => {
        // Chips and buttons handle their own clicks; anything else opens the job.
        if ((e.target as HTMLElement).closest("a,button")) return;
        router.push(href);
      }}
    >
      <div className="flex min-w-0 flex-1 items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Icon className="h-5 w-5" />
        </div>
        <div className="min-w-0 flex-1 space-y-1">
          <Link href={href} className="block truncate font-medium hover:underline underline-offset-4" title={title}>
            {title}
          </Link>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
            <span className="capitalize">{job.kind}</span>
            {meta.map((m) => (
              <span key={m as string} className="before:content-['·'] before:mr-2 truncate max-w-[18rem]">
                {m}
              </span>
            ))}
            {created && (
              <span className="before:content-['·'] before:mr-2" title={created.full}>
                {created.text}
              </span>
            )}
          </div>
          {(job.tags.length > 0 || (job.project && (showProject || (showFolder && job.folder)))) && (
            <div className="flex flex-wrap gap-1 pt-1">
              {job.project && (showProject || (showFolder && job.folder)) && (
                <LocationChip job={job} showProject={showProject} showFolder={showFolder} onLocation={onLocation} />
              )}
              {job.tags.map((tag) => (
                <TagChip
                  key={tag}
                  tag={tag}
                  active={activeTags.includes(tag)}
                  onClick={() => onTag(tag)}
                  className="cursor-pointer"
                />
              ))}
            </div>
          )}
          {job.status === "failed" && job.error && (
            <p className="text-xs text-destructive line-clamp-1" title={job.error}>
              {job.error}
            </p>
          )}
        </div>
      </div>

      <div className="flex items-center justify-between gap-3 pl-[3.25rem] sm:pl-0 sm:justify-end">
        <div className="flex flex-col items-start gap-1.5 sm:items-end sm:w-36">
          <span
            className={cn(
              "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize",
              STATUS_STYLES[job.status] ?? STATUS_STYLES.cancelled
            )}
          >
            {running && <Loader2 className="h-3 w-3 animate-spin" />}
            {job.status}
            {job.status === "processing" && ` · ${job.progress}%`}
          </span>
          {running && (
            <div className="h-1 w-28 rounded-full bg-secondary">
              <div className="h-1 rounded-full bg-primary transition-all" style={{ width: `${job.progress}%` }} />
            </div>
          )}
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="text-muted-foreground hover:text-destructive hover:bg-destructive/10 sm:opacity-0 sm:group-hover:opacity-100 focus-visible:opacity-100"
          onClick={onDelete}
          aria-label={`Delete ${title}`}
        >
          <Trash2 className="h-4 w-4" />
        </Button>
      </div>
    </li>
  );
}

/** "Project › Folder" on a row; each part filters the list to it. */
function LocationChip({
  job,
  showProject,
  showFolder,
  onLocation,
}: {
  job: JobListItem;
  showProject: boolean;
  showFolder: boolean;
  onLocation: (filter: LocationFilter) => void;
}) {
  const project = job.project!;
  const folder = showFolder ? job.folder : null;
  return (
    <span className="inline-flex max-w-[20rem] items-center gap-1 rounded-md border border-primary/20 bg-primary/5 px-2 py-0.5 text-xs font-medium text-foreground">
      <FolderIcon className="h-3 w-3 shrink-0 text-primary opacity-80" />
      {showProject && (
        <button
          type="button"
          onClick={() => onLocation({ projectId: project.id, folderId: null })}
          className="min-w-0 truncate hover:underline underline-offset-2"
          title={`All jobs in ${project.name}`}
        >
          {project.name}
        </button>
      )}
      {showProject && folder && <span className="text-muted-foreground">›</span>}
      {folder && (
        <button
          type="button"
          onClick={() => onLocation({ projectId: project.id, folderId: folder.id })}
          className="min-w-0 truncate hover:underline underline-offset-2"
          title={`All jobs in ${project.name} › ${folder.name}`}
        >
          {folder.name}
        </button>
      )}
    </span>
  );
}

function ContentResults({
  q,
  isLoading,
  error,
  results,
}: {
  q: string;
  isLoading: boolean;
  error: unknown;
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
    <ul className="rounded-xl border bg-background divide-y overflow-hidden">
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
    </ul>
  );
}
