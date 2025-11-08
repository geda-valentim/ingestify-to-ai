"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
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
  Eye,
  Copy,
} from "lucide-react";
import { jobsApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store/auth";
import { formatApiError } from "@/lib/utils";
import { Button } from "@/components/ui/button";
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

// Dynamically import PDF viewer to avoid canvas module issues
const PdfViewer = dynamic(
  () => import("@/components/PdfViewer").then((mod) => ({ default: mod.PdfViewer })),
  { ssr: false, loading: () => <div className="flex items-center justify-center p-8">Loading PDF viewer...</div> }
);

interface PageProps {
  params: Promise<{ id: string }>;
}

interface PageInfo {
  page_number: number;
  job_id: string;
  status: string;
  url: string;
  error_message?: string | null;
  retry_count: number;
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
      router.push("/login");
    }
  }, [isAuthenticated, hasHydrated, router]);

  // Poll for job status
  const { data: status, isLoading } = useQuery({
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
    queryFn: () => jobsApi.getResult(selectedPage!.job_id),
    enabled: !!selectedPage && !!token && selectedPage.status === "completed",
  });

  // Retry mutation with real API
  const retryPageMutation = useMutation({
    mutationFn: ({ pageJobId }: { pageJobId: string }) =>
      jobsApi.retryPage(pageJobId),
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
    mutationFn: async (pageJobIds: string[]) => {
      const results = await Promise.allSettled(
        pageJobIds.map(pageJobId =>
          jobsApi.retryPage(pageJobId)
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
    mutationFn: () => Promise.resolve(),
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
      pageJobId: page.job_id
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
    const pageJobIds = pages
      .filter((p: PageInfo) => selectedPages.has(p.page_number))
      .map((p: PageInfo) => p.job_id);
    bulkRetryMutation.mutate(pageJobIds);
  };

  const downloadMarkdown = () => {
    if (!result) return;
    const blob = new Blob([result.result.markdown], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${status?.name || resolvedParams.id}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const onDocumentLoadSuccess = ({ numPages }: { numPages: number }) => {
    setNumPdfPages(numPages);
    setPdfError(null);
  };

  const onDocumentLoadError = (error: Error) => {
    console.error("PDF load error:", error);
    setPdfError("Failed to load PDF. The file may still be processing.");
  };

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  const pdfUrl = selectedPage
    ? `${jobsApi.getPagePdf(resolvedParams.id, selectedPage.page_number)}?t=${Date.now()}`
    : null;

  return (
    <TooltipProvider>
      <div className="min-h-screen bg-background">
        {/* Header */}
        <header className="border-b bg-background/95 backdrop-blur sticky top-0 z-10">
          <div className="container mx-auto px-4 py-3">
            <Button
              variant="ghost"
              onClick={() => router.push("/dashboard")}
              size="sm"
            >
              <ArrowLeft className="h-4 w-4 mr-2" />
              Back to Dashboard
            </Button>
          </div>
        </header>

        {/* Split Layout */}
        <div className="flex h-[calc(100vh-57px)]">
          {/* Left Sidebar - 30% */}
          <aside className="w-[30%] border-r overflow-y-auto p-4 space-y-4">
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
                </div>
              </div>
              <Badge
                variant="outline"
                className={getStatusColor(status?.status)}
              >
                {status?.status}
              </Badge>
            </div>

            {/* Progress Section */}
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

            {/* Job Details */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Details</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <div className="flex items-start gap-2">
                  <File className="h-4 w-4 text-muted-foreground mt-0.5" />
                  <div className="flex-1 min-w-0">
                    <p className="text-muted-foreground">Type</p>
                    <p className="font-medium capitalize">{status?.type || "Unknown"}</p>
                  </div>
                </div>

                <div className="flex items-start gap-2">
                  <Calendar className="h-4 w-4 text-muted-foreground mt-0.5" />
                  <div className="flex-1 min-w-0">
                    <p className="text-muted-foreground">Created</p>
                    <p className="font-medium">
                      {status?.created_at
                        ? formatDistanceToNow(new Date(status.created_at), {
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
                        {formatDistanceToNow(new Date(status.started_at), {
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
                        {formatDistanceToNow(new Date(status.completed_at), {
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
              {status?.status === "completed" && (
                <>
                  <Button onClick={downloadMarkdown} className="w-full" size="sm">
                    <Download className="h-4 w-4 mr-2" />
                    Download Markdown
                  </Button>
                </>
              )}
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

          {/* Right Panel - 70% - Content Display */}
          <main className="w-[70%] overflow-hidden flex flex-col">
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
                    <div>
                      <h2 className="text-xl font-semibold">Page {selectedPage.page_number}</h2>
                      <p className="text-sm text-muted-foreground">
                        View content in PDF or Markdown format
                      </p>
                    </div>
                    {selectedPage.retry_count > 0 && (
                      <Badge variant="secondary">
                        Retry {selectedPage.retry_count}/3
                      </Badge>
                    )}
                  </div>

                  <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as "pdf" | "markdown")} className="flex-1 flex flex-col overflow-hidden">
                    <TabsList className="grid w-full max-w-md grid-cols-2">
                      <TabsTrigger value="pdf">PDF Preview</TabsTrigger>
                      <TabsTrigger value="markdown">Markdown</TabsTrigger>
                    </TabsList>

                    <TabsContent value="pdf" className="flex-1 overflow-hidden mt-4">
                      <div className="h-full overflow-y-auto border rounded-lg bg-muted/30 p-4">
                        {pdfUrl ? (
                          <div className="flex flex-col items-center">
                            {pdfError ? (
                              <div className="text-center py-12">
                                <AlertCircle className="h-12 w-12 text-destructive mx-auto mb-4" />
                                <p className="text-sm text-muted-foreground">{pdfError}</p>
                              </div>
                            ) : (
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
                            )}
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
              // No page selected - show placeholder
              <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
                <FileText className="h-16 w-16 text-muted-foreground mb-4" />
                <h3 className="text-lg font-semibold mb-2">No Page Selected</h3>
                <p className="text-sm text-muted-foreground max-w-md">
                  {pages.length > 0
                    ? "Select a page from the sidebar to view its content"
                    : "No pages available for this job yet"}
                </p>
              </div>
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
