"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  Download,
  FileText,
  Trash2,
  RotateCw,
  AlertCircle,
  File,
  Calendar,
  Layers,
  AlertTriangle,
  Copy,
  Mic,
  Timer,
  Languages,
  Cpu,
  HardDrive,
  ArrowLeft,
  Folder as FolderIcon,
} from "lucide-react";
import { jobsApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store/auth";
import { loginUrl } from "@/lib/session";
import { formatApiError, formatBytes, formatDuration, parseApiDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { AppHeader } from "@/components/app-header";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { formatDistanceToNow } from "date-fns";
import { useToast } from "@/hooks/use-toast";
import dynamic from "next/dynamic";
import { DocumentView, TranscriptView } from "@/components/job/result-views";
import { JobTagsCard } from "@/components/job/job-tags-card";
import type { JobResultResponse, JobStatusResponse } from "@/types/api";

// Dynamically import PDF viewer to avoid canvas module issues
const PdfViewer = dynamic(
  () => import("@/components/PdfViewer").then((mod) => ({ default: mod.PdfViewer })),
  { ssr: false, loading: () => <div className="flex items-center justify-center p-8">Loading PDF viewer...</div> }
);

// A presigned PDF URL is only good for a few minutes. Stop trusting it slightly
// before the server's expiry so a load never starts against a dying URL.
const PDF_URL_EXPIRY_MARGIN_MS = 10_000;

interface PageProps {
  params: Promise<{ id: string }>;
}

interface PageInfo {
  page_number: number;
  // Null until the split task has created this page's job - see PageJobInfo.
  job_id: string | null;
  status: string;
  url: string;
  error_message?: string | null;
  retry_count: number;
}

/** "12:30 of 57:27 transcribed" while a transcription runs, else null. */
function transcriptionProgress(status?: JobStatusResponse | null): string | null {
  if (!status || status.status !== "processing" || !status.media_duration) return null;
  const done = Math.min(status.transcribed_seconds ?? 0, status.media_duration);
  return `${formatDuration(done)} of ${formatDuration(status.media_duration)} transcribed`;
}

export default function JobStatusPage({ params }: PageProps) {
  const resolvedParams = use(params);
  const router = useRouter();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const token = useAuthStore((state) => state.token);
  const isAuthenticated = useAuthStore((state) => state.token !== null && state.user !== null);
  const hasHydrated = useAuthStore((state) => state._hasHydrated);

  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [selectedPage, setSelectedPage] = useState<PageInfo | null>(null);

  const [activeTab, setActiveTab] = useState<"pdf" | "markdown">("pdf");
  const [numPdfPages, setNumPdfPages] = useState<number>(0);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [selectedPages, setSelectedPages] = useState<Set<number>>(new Set());

  useEffect(() => {
    if (hasHydrated && !isAuthenticated) {
      router.replace(loginUrl());
    }
  }, [isAuthenticated, hasHydrated, router]);

  // Poll for job status
  const { data: status, isLoading, isError: isStatusError } = useQuery({
    queryKey: ["job-status", resolvedParams.id, token],
    queryFn: () => jobsApi.getStatus(resolvedParams.id),
    enabled: !!token,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "completed" || status === "failed" ? false : 3000;
    },
  });

  // Fetch result when job is completed
  const { data: result } = useQuery({
    queryKey: ["job-result", resolvedParams.id, token],
    queryFn: () => jobsApi.getResult(resolvedParams.id),
    enabled: status?.status === "completed" && !!token,
  });

  // Fetch pages for PDF documents
  const { data: pagesData } = useQuery({
    queryKey: ["job-pages", resolvedParams.id, token],
    queryFn: () => jobsApi.getPages(resolvedParams.id),
    enabled: status?.type === "main" && (status?.total_pages ?? 0) > 0 && !!token,
    refetchInterval: (query) => {
      if (status?.status === "completed" || status?.status === "failed") {
        return false;
      }
      return 3000;
    },
  });

  const pages = pagesData?.pages || status?.pages || [];

  // Fetch specific page result
  const { data: pageResult, isLoading: isLoadingPage } = useQuery({
    queryKey: ["page-result", selectedPage?.job_id, token],
    queryFn: () => jobsApi.getResult(selectedPage!.job_id!),
    // A page with no job id has nothing to fetch (it is not "completed" either,
    // but the id is what the request needs, so gate on it explicitly).
    enabled:
      !!selectedPage &&
      !!selectedPage.job_id &&
      !!token &&
      selectedPage.status === "completed",
  });

  // Fetch the short-lived presigned URL for the selected page's PDF.
  // The endpoint is authenticated, so this can no longer be a URL built inline:
  // it is a request whose answer expires. gcTime is 0 so a URL is never served
  // from cache after the viewer stops using it - paging back to a page always
  // asks for a fresh one instead of handing the viewer a dead URL.
  const {
    data: pdfUrlData,
    isFetching: isFetchingPdfUrl,
    isError: isPdfUrlError,
    refetch: refetchPdfUrl,
  } = useQuery({
    queryKey: ["page-pdf-url", resolvedParams.id, selectedPage?.page_number, token],
    queryFn: () => jobsApi.getPagePdf(resolvedParams.id, selectedPage!.page_number),
    enabled: !!selectedPage && !!token && selectedPage.status === "completed",
    staleTime: 0,
    gcTime: 0,
    retry: 1,
    // A new URL means a new `file` prop, which makes the viewer re-download the
    // PDF. Refresh only when it is actually needed (page change, tab change,
    // load failure), never just because the window regained focus.
    refetchOnWindowFocus: false,
  });

  // Treat a URL that is about to expire as already gone: it would only fail
  // halfway through loading. Margin absorbs clock skew and slow requests.
  const pdfUrlExpiresAt = pdfUrlData ? Date.parse(pdfUrlData.expires_at) : 0;
  const isPdfUrlUsable = () => pdfUrlExpiresAt - Date.now() > PDF_URL_EXPIRY_MARGIN_MS;

  // Retry mutation with real API
  // Retry is addressed by page number on the main job, not by the failed page's
  // own job id: `POST /jobs/{pageJobId}/retry` is not a route and always 404'd.
  const retryPageMutation = useMutation({
    mutationFn: ({ pageNumber }: { pageNumber: number }) =>
      jobsApi.retryPage(resolvedParams.id, pageNumber),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["job-status", resolvedParams.id] });
      queryClient.invalidateQueries({ queryKey: ["job-pages", resolvedParams.id] });
      toast({
        title: "Page retry started",
        description: `Page queued for retry`,
      });
    },
    onError: (error: any) => {
      toast({
        title: "Retry failed",
        description: formatApiError(error),
        variant: "destructive",
      });
    },
  });

  // Bulk retry mutation
  const bulkRetryMutation = useMutation({
    mutationFn: async (pageNumbers: number[]) => {
      const results = await Promise.allSettled(
        pageNumbers.map(pageNumber =>
          jobsApi.retryPage(resolvedParams.id, pageNumber)
        )
      );
      return results;
    },
    onSuccess: (results) => {
      const succeeded = results.filter(r => r.status === 'fulfilled').length;
      const failed = results.filter(r => r.status === 'rejected').length;

      queryClient.invalidateQueries({ queryKey: ["job-status", resolvedParams.id] });
      queryClient.invalidateQueries({ queryKey: ["job-pages", resolvedParams.id] });

      setSelectedPages(new Set()); // Clear selection

      toast({
        title: "Bulk retry completed",
        description: `${succeeded} pages queued for retry${failed > 0 ? `, ${failed} failed` : ''}`,
      });
    },
    onError: (error: any) => {
      toast({
        title: "Bulk retry failed",
        description: formatApiError(error),
        variant: "destructive",
      });
    },
  });

  const deleteMutation = useMutation({
    // Same stub as the jobs list had: it resolved, toasted "deleted", and left
    // the job in place. `DELETE /jobs/{job_id}` is live and does the work.
    mutationFn: () => jobsApi.delete(resolvedParams.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      toast({
        title: "Job deleted",
        description: "The job has been successfully deleted.",
      });
      router.push("/jobs");
    },
    onError: (error: any) => {
      toast({
        title: "Error deleting job",
        description: formatApiError(error),
        variant: "destructive",
      });
    },
  });

  const getStatusIcon = (status?: string) => {
    switch (status) {
      case "completed":
        return <CheckCircle2 className="h-5 w-5 text-green-500" />;
      case "failed":
        return <XCircle className="h-5 w-5 text-red-500" />;
      case "processing":
        return <Loader2 className="h-5 w-5 text-blue-500 animate-spin" />;
      default:
        return <Clock className="h-5 w-5 text-yellow-500" />;
    }
  };

  const getStatusColor = (status?: string) => {
    switch (status) {
      case "completed":
        return "text-green-500";
      case "failed":
        return "text-red-500";
      case "processing":
        return "text-blue-500";
      default:
        return "text-yellow-500";
    }
  };

  const handleDeleteClick = () => {
    setDeleteDialogOpen(true);
  };

  const handleDeleteConfirm = () => {
    deleteMutation.mutate();
  };

  const handlePageClick = (page: PageInfo) => {
    if (page.status === "completed" || page.status === "failed") {
      setSelectedPage(page);
      setPdfError(null);
      // Set initial tab based on status
      setActiveTab(page.status === "completed" ? "pdf" : "markdown");
    }
  };

  const handleRetryPage = (page: PageInfo, e: React.MouseEvent) => {
    e.stopPropagation();
    retryPageMutation.mutate({
      pageNumber: page.page_number
    });
  };

  const togglePageSelection = (pageNumber: number) => {
    setSelectedPages(prev => {
      const newSet = new Set(prev);
      if (newSet.has(pageNumber)) {
        newSet.delete(pageNumber);
      } else {
        newSet.add(pageNumber);
      }
      return newSet;
    });
  };

  const selectAllFailedPages = () => {
    const failedPageNumbers = pages
      .filter((p: PageInfo) => p.status === "failed" && p.retry_count < 3)
      .map((p: PageInfo) => p.page_number);
    setSelectedPages(new Set(failedPageNumbers));
  };

  const deselectAll = () => {
    setSelectedPages(new Set());
  };

  const handleBulkRetry = () => {
    if (selectedPages.size === 0) return;
    const pageNumbers = pages
      .filter((p: PageInfo) => selectedPages.has(p.page_number))
      .map((p: PageInfo) => p.page_number);
    bulkRetryMutation.mutate(pageNumbers);
  };

  const onDocumentLoadSuccess = ({ numPages }: { numPages: number }) => {
    setNumPdfPages(numPages);
    setPdfError(null);
  };

  const onDocumentLoadError = (error: Error) => {
    console.error("PDF load error:", error);
    // A presigned URL that died while the viewer was open fails here (storage
    // answers 403, not 404). Get a fresh one instead of showing an error.
    if (pdfUrlData && !isPdfUrlUsable()) {
      refetchPdfUrl();
      return;
    }
    setPdfError("Failed to load PDF. The file may still be processing.");
  };

  const handleTabChange = (value: string) => {
    setActiveTab(value as "pdf" | "markdown");
    // Coming back to the PDF tab after sitting on Markdown past the TTL: the
    // cached URL is dead, so ask for another one before rendering the viewer.
    if (value === "pdf" && !isPdfUrlUsable() && !isFetchingPdfUrl) {
      setPdfError(null);
      refetchPdfUrl();
    }
  };

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (isStatusError || !status) {
    return (
      <div className="min-h-screen bg-background">
        <AppHeader />
        <div className="flex flex-col items-center justify-center p-12 text-center">
          <AlertCircle className="h-12 w-12 text-muted-foreground mb-4" />
          <h1 className="text-lg font-semibold">Job not found</h1>
          <p className="text-sm text-muted-foreground mt-1">It may have been deleted, or it belongs to another account.</p>
          <Button variant="outline" className="mt-6" onClick={() => router.push("/jobs")}>
            Back to My Jobs
          </Button>
        </div>
      </div>
    );
  }

  const metadata = result?.result.metadata;
  // Only /transcribe jobs produce subtitle formats.
  const isTranscript = !!metadata?.available_formats?.includes("vtt");
  const hasPages = pages.length > 0;
  const fileName = status.name || resolvedParams.id;

  // No cache-buster: the query string is part of the presigned signature, and
  // appending to it turns every request into a 403.
  const pdfUrl = selectedPage && pdfUrlData && isPdfUrlUsable() ? pdfUrlData.url : null;

  return (
    <TooltipProvider>
      <div className="min-h-screen lg:h-screen flex flex-col bg-background">
        {/* Header */}
        <AppHeader className="sticky top-0 z-10" />

        {/* Split layout: stacked on small screens, sidebar + content from lg up */}
        <div className="flex-1 min-h-0 flex flex-col lg:flex-row">
          {/* Sidebar */}
          <aside className="lg:w-[30%] lg:max-w-md border-b lg:border-b-0 lg:border-r lg:overflow-y-auto p-4 space-y-4">
            {/* Job Header */}
            <div>
              <div className="flex items-center gap-3 mb-2">
                {getStatusIcon(status?.status)}
                <div className="flex-1 min-w-0">
                  <h1 className="text-2xl font-bold truncate">
                    {status?.name || "Untitled Job"}
                  </h1>
                  <p className="text-sm text-muted-foreground truncate">
                    {resolvedParams.id}
                  </p>
                  {status.project && (
                    <nav
                      aria-label="Location"
                      className="mt-1 flex min-w-0 items-center gap-1 text-sm"
                    >
                      <FolderIcon className="h-3.5 w-3.5 shrink-0 text-primary" />
                      <Link
                        href={`/jobs?project_id=${encodeURIComponent(status.project.id)}`}
                        className="min-w-0 truncate hover:underline underline-offset-4"
                        title={`All jobs in ${status.project.name}`}
                      >
                        {status.project.name}
                      </Link>
                      {status.folder && (
                        <>
                          <span className="text-muted-foreground">›</span>
                          <Link
                            href={`/jobs?project_id=${encodeURIComponent(status.project.id)}&folder_id=${encodeURIComponent(status.folder.id)}`}
                            className="min-w-0 truncate hover:underline underline-offset-4"
                            title={`All jobs in ${status.project.name} › ${status.folder.name}`}
                          >
                            {status.folder.name}
                          </Link>
                        </>
                      )}
                    </nav>
                  )}
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge
                  variant="outline"
                  className={getStatusColor(status?.status)}
                >
                  {status?.status}
                </Badge>
                {metadata && (
                  <Badge variant="secondary">
                    {isTranscript ? "Transcription" : "Document"}
                  </Badge>
                )}
              </div>
            </div>

            {/* Progress Section: hidden once a job without pages is done */}
            {(status.status !== "completed" || hasPages) && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Progress</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <div className="flex justify-between text-sm mb-2">
                    <span className="text-muted-foreground">Overall</span>
                    <span className="font-medium">{status?.progress}%</span>
                  </div>
                  <div className="w-full bg-secondary rounded-full h-2">
                    <div
                      className="bg-primary h-2 rounded-full transition-all duration-300"
                      style={{ width: `${status?.progress || 0}%` }}
                    />
                  </div>
                  {transcriptionProgress(status) && (
                    <p className="text-xs text-muted-foreground mt-2">{transcriptionProgress(status)}</p>
                  )}
                </div>

                {status?.total_pages && status.total_pages > 0 && (
                  <div className="pt-3 border-t space-y-2">
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">Pages</span>
                      <span className="font-medium">{status.total_pages} total</span>
                    </div>
                    <div className="grid grid-cols-3 gap-2 text-xs">
                      <div className="text-center p-2 bg-green-500/10 rounded">
                        <div className="font-semibold text-green-600 dark:text-green-400">
                          {pages.filter((p: PageInfo) => p.status === "completed").length}
                        </div>
                        <div className="text-muted-foreground">Completed</div>
                      </div>
                      <div className="text-center p-2 bg-blue-500/10 rounded">
                        <div className="font-semibold text-blue-600 dark:text-blue-400">
                          {pages.filter((p: PageInfo) => p.status === "processing").length}
                        </div>
                        <div className="text-muted-foreground">Processing</div>
                      </div>
                      <div className="text-center p-2 bg-red-500/10 rounded">
                        <div className="font-semibold text-red-600 dark:text-red-400">
                          {pages.filter((p: PageInfo) => p.status === "failed").length}
                        </div>
                        <div className="text-muted-foreground">Failed</div>
                      </div>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
            )}

            {/* Job Details */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Details</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                {metadata && (
                  <div className="grid grid-cols-2 gap-3 pb-3 border-b">
                    <DetailItem icon={isTranscript ? Mic : File} label="Format" value={metadata.format.toUpperCase()} />
                    <DetailItem icon={HardDrive} label="Size" value={formatBytes(metadata.size_bytes)} />
                    {metadata.duration != null && (
                      <DetailItem icon={Timer} label="Duration" value={formatDuration(metadata.duration)} />
                    )}
                    {metadata.language && (
                      <DetailItem icon={Languages} label="Language" value={metadata.language.toUpperCase()} />
                    )}
                    {metadata.pages != null && (
                      <DetailItem icon={Layers} label="Pages" value={String(metadata.pages)} />
                    )}
                    {metadata.words != null && (
                      <DetailItem icon={FileText} label="Words" value={metadata.words.toLocaleString()} />
                    )}
                    {metadata.device && (
                      <DetailItem
                        icon={Cpu}
                        label="Ran on"
                        value={metadata.device === "cuda" ? "GPU" : metadata.device === "cpu" ? "CPU" : metadata.device}
                      />
                    )}
                  </div>
                )}

                <div className="flex items-start gap-2">
                  <Calendar className="h-4 w-4 text-muted-foreground mt-0.5" />
                  <div className="flex-1 min-w-0">
                    <p className="text-muted-foreground">Created</p>
                    <p className="font-medium">
                      {status?.created_at
                        ? formatDistanceToNow(parseApiDate(status.created_at), {
                            addSuffix: true,
                          })
                        : "-"}
                    </p>
                  </div>
                </div>

                {status?.started_at && (
                  <div className="flex items-start gap-2">
                    <Clock className="h-4 w-4 text-muted-foreground mt-0.5" />
                    <div className="flex-1 min-w-0">
                      <p className="text-muted-foreground">Started</p>
                      <p className="font-medium">
                        {formatDistanceToNow(parseApiDate(status.started_at), {
                          addSuffix: true,
                        })}
                      </p>
                    </div>
                  </div>
                )}

                {status?.completed_at && (
                  <div className="flex items-start gap-2">
                    <CheckCircle2 className="h-4 w-4 text-muted-foreground mt-0.5" />
                    <div className="flex-1 min-w-0">
                      <p className="text-muted-foreground">Completed</p>
                      <p className="font-medium">
                        {formatDistanceToNow(parseApiDate(status.completed_at), {
                          addSuffix: true,
                        })}
                      </p>
                    </div>
                  </div>
                )}

                {status?.child_jobs && (
                  <div className="flex items-start gap-2 pt-3 border-t">
                    <Layers className="h-4 w-4 text-muted-foreground mt-0.5" />
                    <div className="flex-1 min-w-0">
                      <p className="text-muted-foreground mb-1">Child Jobs</p>
                      <div className="space-y-1 text-xs">
                        {status.child_jobs.split_job_id && (
                          <p className="font-mono truncate">
                            Split: {status.child_jobs.split_job_id}
                          </p>
                        )}
                        {status.child_jobs.merge_job_id && (
                          <p className="font-mono truncate">
                            Merge: {status.child_jobs.merge_job_id}
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            <JobTagsCard jobId={resolvedParams.id} tags={status.tags ?? []} />

            {/* Error Section */}
            {status?.error && (
              <Card className="border-destructive/50">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2 text-destructive">
                    <AlertTriangle className="h-4 w-4" />
                    Error
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-destructive">{status.error}</p>
                </CardContent>
              </Card>
            )}

            {/* Actions */}
            <div className="space-y-2">
              <Button
                variant="destructive"
                className="w-full"
                onClick={handleDeleteClick}
                size="sm"
              >
                <Trash2 className="h-4 w-4 mr-2" />
                Delete Job
              </Button>
            </div>

            {/* Pages List in Sidebar */}
            {pages.length > 0 && (
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">Pages ({pages.length})</CardTitle>
                  <CardDescription className="text-xs">
                    {selectedPages.size > 0
                      ? `${selectedPages.size} page${selectedPages.size > 1 ? 's' : ''} selected`
                      : 'Click to view content'}
                  </CardDescription>
                </CardHeader>

                {/* Bulk Actions */}
                {pages.filter((p: PageInfo) => p.status === "failed").length > 0 && (
                  <CardContent className="pt-0 pb-3 space-y-2">
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={selectAllFailedPages}
                        className="flex-1 text-xs h-8"
                      >
                        Select All Failed
                      </Button>
                      {selectedPages.size > 0 && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={deselectAll}
                          className="flex-1 text-xs h-8"
                        >
                          Deselect All
                        </Button>
                      )}
                    </div>
                    {selectedPages.size > 0 && (
                      <Button
                        onClick={handleBulkRetry}
                        disabled={bulkRetryMutation.isPending}
                        size="sm"
                        className="w-full text-xs h-8"
                      >
                        <RotateCw className={`h-3 w-3 mr-2 ${bulkRetryMutation.isPending ? 'animate-spin' : ''}`} />
                        Retry {selectedPages.size} Selected Page{selectedPages.size > 1 ? 's' : ''}
                      </Button>
                    )}
                  </CardContent>
                )}

                <CardContent className="space-y-1 max-h-[400px] overflow-y-auto">
                  {pages.map((page: PageInfo) => {
                    const isRetryDisabled = page.retry_count >= 3;
                    const canRetry = page.status === "failed" && !isRetryDisabled;
                    const isSelected = selectedPage?.page_number === page.page_number;
                    const isChecked = selectedPages.has(page.page_number);

                    return (
                      <Tooltip key={page.page_number}>
                        <TooltipTrigger asChild>
                          <div
                            className={`
                              w-full flex items-center gap-2 p-2 rounded-lg border transition-all
                              ${isSelected ? "border-primary bg-primary/10" : "border-border"}
                              ${isChecked ? "bg-blue-500/10 border-blue-500/50" : ""}
                              ${
                                page.status === "completed"
                                  ? "hover:bg-green-500/10 hover:border-green-500/50"
                                  : page.status === "failed"
                                  ? "hover:bg-red-500/10 hover:border-red-500/50"
                                  : "opacity-60"
                              }
                            `}
                          >
                            {/* Checkbox for failed pages */}
                            {page.status === "failed" && !isRetryDisabled && (
                              <Checkbox
                                checked={isChecked}
                                onCheckedChange={() => togglePageSelection(page.page_number)}
                                onClick={(e) => e.stopPropagation()}
                                className="flex-shrink-0"
                              />
                            )}

                            {/* Page Button */}
                            <button
                              onClick={() => handlePageClick(page)}
                              disabled={
                                page.status !== "completed" && page.status !== "failed"
                              }
                              className="flex-1 flex items-center justify-between text-left min-w-0"
                            >
                              <div className="flex items-center gap-2 flex-1 min-w-0">
                                <div className="flex-shrink-0">
                                  {page.status === "completed" && (
                                    <CheckCircle2 className="h-4 w-4 text-green-600 dark:text-green-400" />
                                  )}
                                  {page.status === "failed" && (
                                    <XCircle className="h-4 w-4 text-red-600 dark:text-red-400" />
                                  )}
                                  {page.status === "processing" && (
                                    <Loader2 className="h-4 w-4 text-blue-600 dark:text-blue-400 animate-spin" />
                                  )}
                                  {page.status === "queued" && (
                                    <Clock className="h-4 w-4 text-yellow-600 dark:text-yellow-400" />
                                  )}
                                  {page.status === "pending" && (
                                    <Clock className="h-4 w-4 text-gray-600 dark:text-gray-400" />
                                  )}
                                </div>
                                <span className="text-sm font-medium truncate">
                                  Page {page.page_number}
                                </span>
                              </div>
                              <div className="flex items-center gap-2 flex-shrink-0">
                                {page.retry_count > 0 && (
                                  <Badge variant="secondary" className="h-5 px-1.5 text-[10px]">
                                    {page.retry_count}/3
                                  </Badge>
                                )}
                                {canRetry && (
                                  <button
                                    onClick={(e) => handleRetryPage(page, e)}
                                    disabled={retryPageMutation.isPending || isRetryDisabled}
                                    className="p-1 hover:bg-destructive/20 rounded transition-colors"
                                    title="Retry this page"
                                  >
                                    <RotateCw
                                      className={`h-3 w-3 text-destructive ${
                                        retryPageMutation.isPending ? "animate-spin" : ""
                                      }`}
                                    />
                                  </button>
                                )}
                              </div>
                            </button>
                          </div>
                        </TooltipTrigger>
                        <TooltipContent side="right" className="max-w-xs">
                          <div className="space-y-1">
                            <p className="font-semibold">Page {page.page_number}</p>
                            <p className="text-xs capitalize">Status: {page.status}</p>
                            {page.retry_count > 0 && (
                              <p className="text-xs">
                                Retry attempts: {page.retry_count}/3
                              </p>
                            )}
                            {page.error_message && (
                              <p className="text-xs text-destructive mt-2">
                                Error: {page.error_message}
                              </p>
                            )}
                          </div>
                        </TooltipContent>
                      </Tooltip>
                    );
                  })}
                </CardContent>
              </Card>
            )}
          </aside>

          {/* Content */}
          <main className="flex-1 min-w-0 min-h-[70vh] lg:min-h-0 overflow-hidden flex flex-col">
            {selectedPage ? (
              selectedPage.status === "failed" ? (
                // Failed page error display
                <div className="flex-1 flex flex-col items-center justify-center p-8 space-y-4">
                  <AlertCircle className="h-16 w-16 text-destructive" />
                  <div className="text-center space-y-4">
                    <div>
                      <h3 className="text-lg font-semibold mb-2">Page {selectedPage.page_number} Failed</h3>
                      <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 max-w-md mx-auto">
                        <p className="text-sm text-destructive break-words">
                          {selectedPage.error_message || "An unknown error occurred"}
                        </p>
                      </div>
                    </div>

                    <div className="flex gap-2 justify-center">
                      {selectedPage.retry_count < 3 && (
                        <Button
                          onClick={(e) => handleRetryPage(selectedPage, e)}
                          disabled={retryPageMutation.isPending}
                        >
                          <RotateCw
                            className={`h-4 w-4 mr-2 ${
                              retryPageMutation.isPending ? "animate-spin" : ""
                            }`}
                          />
                          Retry Page
                        </Button>
                      )}
                      {selectedPage.error_message && (
                        <Button
                          variant="outline"
                          onClick={() => {
                            navigator.clipboard.writeText(
                              `Page ${selectedPage.page_number} Error:\n${selectedPage.error_message}`
                            );
                            toast({
                              title: "Error copied",
                              description: "Error message copied to clipboard",
                            });
                          }}
                        >
                          <Copy className="h-4 w-4 mr-2" />
                          Copy Error
                        </Button>
                      )}
                    </div>

                    {selectedPage.retry_count >= 3 && (
                      <p className="text-xs text-destructive font-medium">
                        Maximum retry attempts reached (3/3)
                      </p>
                    )}

                    <p className="text-xs text-muted-foreground">
                      Retry attempt: {selectedPage.retry_count}/3
                    </p>
                  </div>
                </div>
              ) : (
                // Completed page content display
                <div className="flex-1 flex flex-col overflow-hidden p-6">
                  <div className="mb-4 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <Button variant="ghost" size="sm" onClick={() => setSelectedPage(null)}>
                        <ArrowLeft className="h-4 w-4 mr-2" />
                        Full document
                      </Button>
                      <div>
                        <h2 className="text-xl font-semibold">Page {selectedPage.page_number}</h2>
                        <p className="text-sm text-muted-foreground">
                          View content in PDF or Markdown format
                        </p>
                      </div>
                    </div>
                    {selectedPage.retry_count > 0 && (
                      <Badge variant="secondary">
                        Retry {selectedPage.retry_count}/3
                      </Badge>
                    )}
                  </div>

                  <Tabs value={activeTab} onValueChange={handleTabChange} className="flex-1 flex flex-col overflow-hidden">
                    <TabsList className="grid w-full max-w-md grid-cols-2">
                      <TabsTrigger value="pdf">PDF Preview</TabsTrigger>
                      <TabsTrigger value="markdown">Markdown</TabsTrigger>
                    </TabsList>

                    <TabsContent value="pdf" className="flex-1 overflow-hidden mt-4">
                      <div className="h-full overflow-y-auto border rounded-lg bg-muted/30 p-4">
                        {pdfError || isPdfUrlError ? (
                          <div className="text-center py-12">
                            <AlertCircle className="h-12 w-12 text-destructive mx-auto mb-4" />
                            <p className="text-sm text-muted-foreground">
                              {pdfError || "Failed to load PDF. Please try again."}
                            </p>
                          </div>
                        ) : !pdfUrl && (isFetchingPdfUrl || !pdfUrlData) ? (
                          <div className="py-12 flex items-center justify-center">
                            <Loader2 className="h-8 w-8 animate-spin text-primary" />
                          </div>
                        ) : pdfUrl ? (
                          <div className="flex flex-col items-center">
                            <PdfViewer
                              file={pdfUrl}
                              onLoadSuccess={onDocumentLoadSuccess}
                              onLoadError={onDocumentLoadError}
                              pageNumber={1}
                              renderTextLayer={true}
                              renderAnnotationLayer={true}
                              className="mx-auto"
                              width={typeof window !== 'undefined' ? Math.min(900, window.innerWidth * 0.6) : 900}
                            />
                          </div>
                        ) : (
                          <div className="text-center py-12">
                            <p className="text-sm text-muted-foreground">PDF not available</p>
                          </div>
                        )}
                      </div>
                    </TabsContent>

                    <TabsContent value="markdown" className="flex-1 overflow-hidden mt-4">
                      <div className="h-full overflow-y-auto border rounded-lg bg-muted/30 p-4">
                        {isLoadingPage ? (
                          <div className="py-12 flex items-center justify-center">
                            <Loader2 className="h-8 w-8 animate-spin text-primary" />
                          </div>
                        ) : pageResult ? (
                          <div className="space-y-4">
                            <pre className="text-sm whitespace-pre-wrap font-mono">
                              {pageResult.result.markdown}
                            </pre>
                            <Button
                              variant="outline"
                              onClick={() => {
                                const blob = new Blob([pageResult.result.markdown], {
                                  type: "text/markdown",
                                });
                                const url = URL.createObjectURL(blob);
                                const a = document.createElement("a");
                                a.href = url;
                                a.download = `page-${selectedPage?.page_number}.md`;
                                document.body.appendChild(a);
                                a.click();
                                document.body.removeChild(a);
                                URL.revokeObjectURL(url);
                              }}
                            >
                              <Download className="h-4 w-4 mr-2" />
                              Download Markdown
                            </Button>
                          </div>
                        ) : (
                          <div className="py-12 text-center text-muted-foreground">
                            Failed to load page content
                          </div>
                        )}
                      </div>
                    </TabsContent>
                  </Tabs>
                </div>
              )
            ) : (
              // No page selected: the job's own result
              <JobResultPanel
                status={status}
                result={result}
                isTranscript={isTranscript}
                hasPages={hasPages}
                fileName={fileName}
                token={token}
              />
            )}
          </main>
        </div>

        {/* Delete Confirmation Dialog */}
        <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Are you sure?</AlertDialogTitle>
              <AlertDialogDescription>
                This action cannot be undone. This will permanently delete the job and all its
                associated data including:
                <ul className="list-disc list-inside mt-2 space-y-1">
                  <li>Job metadata</li>
                  <li>All pages and content</li>
                  <li>Markdown content</li>
                  <li>Temporary processing data</li>
                </ul>
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction
                onClick={handleDeleteConfirm}
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
    </TooltipProvider>
  );
}

function DetailItem({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-start gap-2 min-w-0">
      <Icon className="h-4 w-4 text-muted-foreground mt-0.5 shrink-0" />
      <div className="min-w-0">
        <p className="text-muted-foreground text-xs">{label}</p>
        <p className="font-medium truncate">{value}</p>
      </div>
    </div>
  );
}

/**
 * What the main panel shows when no PDF page is selected: progress while the
 * job runs, the error if it failed, otherwise the result in the view that fits
 * it - a transcript for audio/video, rendered Markdown for documents.
 */
function JobResultPanel({
  status,
  result,
  isTranscript,
  hasPages,
  fileName,
  token,
}: {
  status: JobStatusResponse;
  result?: JobResultResponse;
  isTranscript: boolean;
  hasPages: boolean;
  fileName: string;
  token: string | null;
}) {
  if (status.status === "failed") {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
        <XCircle className="h-16 w-16 text-destructive mb-4" />
        <h3 className="text-lg font-semibold mb-2">Processing failed</h3>
        <p className="text-sm text-muted-foreground max-w-md break-words">
          {status.error || "An unknown error occurred"}
        </p>
      </div>
    );
  }

  if (status.status !== "completed") {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
        <Loader2 className="h-12 w-12 text-primary animate-spin mb-4" />
        <h3 className="text-lg font-semibold mb-1">
          {status.status === "processing" ? "Processing…" : "Waiting in the queue…"}
        </h3>
        <p className="text-sm text-muted-foreground">
          {status.progress}% — the result shows up here as soon as it is ready.
        </p>
        {transcriptionProgress(status) && (
          <p className="text-sm text-muted-foreground mt-1">{transcriptionProgress(status)}</p>
        )}
      </div>
    );
  }

  if (!result) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-4">
      <div>
        <h2 className="text-xl font-semibold">{isTranscript ? "Transcription" : "Converted document"}</h2>
        {hasPages && (
          <p className="text-sm text-muted-foreground">
            All pages merged. Select a page in the sidebar to see its PDF next to its text.
          </p>
        )}
      </div>
      {isTranscript ? (
        <TranscriptView
          jobId={status.job_id}
          markdown={result.result.markdown}
          fileName={fileName}
          token={token}
        />
      ) : (
        <DocumentView markdown={result.result.markdown} fileName={fileName} />
      )}
    </div>
  );
}
