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
import { formatDistanceToNow } from "date-fns";
import { useToast } from "@/hooks/use-toast";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function JobStatusPage({ params }: PageProps) {
  const resolvedParams = use(params);
  const router = useRouter();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const token = useAuthStore((state) => state.token);
  const isAuthenticated = useAuthStore((state) => state.token !== null && state.user !== null);
  const hasHydrated = useAuthStore((state) => state._hasHydrated);
  const [showResult, setShowResult] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [selectedPage, setSelectedPage] = useState<number | null>(null);
  const [pageDialogOpen, setPageDialogOpen] = useState(false);

  useEffect(() => {
    if (hasHydrated && !isAuthenticated) {
      router.push("/login");
    }
  }, [isAuthenticated, hasHydrated, router]);

  // Poll for job status
  const { data: status, isLoading } = useQuery({
    queryKey: ["job-status", resolvedParams.id, token],
    queryFn: () => jobsApi.get(resolvedParams.id, token!),
    enabled: !!token,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      // Stop polling if job is completed or failed
      return status === "completed" || status === "failed" ? false : 3000;
    },
  });

  // Fetch result when job is completed
  const { data: result } = useQuery({
    queryKey: ["job-result", resolvedParams.id, token],
    queryFn: () => jobsApi.getResult(resolvedParams.id, token!),
    enabled: status?.status === "completed" && showResult && !!token,
  });

  // Fetch pages for PDF documents
  const { data: pagesData } = useQuery({
    queryKey: ["job-pages", resolvedParams.id, token],
    queryFn: () => jobsApi.getPages(resolvedParams.id, token!),
    enabled: status?.type === "main" && (status?.total_pages ?? 0) > 0 && !!token,
    refetchInterval: (query) => {
      // Keep polling if we have pages that aren't completed yet
      if (status?.status === "completed" || status?.status === "failed") {
        return false;
      }
      return 3000;
    },
  });

  const pages = pagesData?.pages;

  // Fetch specific page result - not yet implemented, will show placeholder
  const { data: pageResult, isLoading: isLoadingPage } = useQuery({
    queryKey: ["page-result", resolvedParams.id, selectedPage, token],
    queryFn: () => Promise.resolve(null),  // Not yet implemented in API
    enabled: false,  // Disabled until API supports it
  });

  const getStatusIcon = () => {
    switch (status?.status) {
      case "completed":
        return <CheckCircle2 className="h-12 w-12 text-green-500" />;
      case "failed":
        return <XCircle className="h-12 w-12 text-red-500" />;
      case "processing":
        return <Loader2 className="h-12 w-12 text-blue-500 animate-spin" />;
      default:
        return <Clock className="h-12 w-12 text-yellow-500" />;
    }
  };

  const getStatusColor = () => {
    switch (status?.status) {
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

  const deleteMutation = useMutation({
    mutationFn: () => Promise.resolve(),  // Delete not yet implemented in API
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

  const retryPageMutation = useMutation({
    mutationFn: ({ pageJobId }: { pageJobId: string }) =>
      Promise.resolve(),  // Retry not yet implemented in API
    onSuccess: (newJobId, variables) => {
      queryClient.invalidateQueries({ queryKey: ["job-status", resolvedParams.id] });
      toast({
        title: "Page retry started",
        description: `Page retry coming soon!`,
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

  const handleDeleteClick = () => {
    setDeleteDialogOpen(true);
  };

  const handleDeleteConfirm = () => {
    deleteMutation.mutate();
  };

  const handlePageClick = (pageNumber: number, pageStatus: string, e: React.MouseEvent) => {
    // Prevent click if clicking on retry button
    if ((e.target as HTMLElement).closest('button[data-retry]')) {
      return;
    }

    if (pageStatus === "completed") {
      setSelectedPage(pageNumber);
      setPageDialogOpen(true);
    }
  };

  const handleRetryPage = (pageJobId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    retryPageMutation.mutate({ pageJobId });
  };

  const downloadPageMarkdown = () => {
    alert("Page download coming soon!");
  };

  const downloadMarkdown = () => {
    if (!result) return;
    const blob = new Blob([result.markdown], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${status?.name || resolvedParams.id}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-background via-background to-muted">
      {/* Header */}
      <header className="border-b bg-background/95 backdrop-blur">
        <div className="container mx-auto px-4 py-4">
          <Button
            variant="ghost"
            onClick={() => router.push("/dashboard")}
            className="mb-2"
          >
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Dashboard
          </Button>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-4 py-12">
        <div className="max-w-4xl mx-auto space-y-6">
          {/* Status Card */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div className="flex-1">
                  <CardTitle>Job Status</CardTitle>
                  <CardDescription className="mt-1">
                    {status?.name || `Job ID: ${resolvedParams.id}`}
                  </CardDescription>
                </div>
                <div className="flex items-center gap-3">
                  {getStatusIcon()}
                  <Button
                    variant="ghost"
                    size="icon"
                    className="text-destructive hover:text-destructive hover:bg-destructive/10"
                    onClick={handleDeleteClick}
                  >
                    <Trash2 className="h-5 w-5" />
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Status Info */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                  <p className="text-sm text-muted-foreground">Status</p>
                  <p className={`font-medium capitalize ${getStatusColor()}`}>
                    {status?.status}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Progress</p>
                  <p className="font-medium">{status?.progress}%</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Created</p>
                  <p className="font-medium text-sm">
                    {status?.created_at
                      ? formatDistanceToNow(new Date(status.created_at), {
                          addSuffix: true,
                        })
                      : "-"}
                  </p>
                </div>
                {status?.completed_at && (
                  <div>
                    <p className="text-sm text-muted-foreground">Completed</p>
                    <p className="font-medium text-sm">
                      {formatDistanceToNow(new Date(status.completed_at), {
                        addSuffix: true,
                      })}
                    </p>
                  </div>
                )}
              </div>

              {/* Progress Bar */}
              <div className="space-y-2">
                <div className="w-full bg-secondary rounded-full h-2">
                  <div
                    className="bg-primary h-2 rounded-full transition-all duration-300"
                    style={{ width: `${status?.progress || 0}%` }}
                  />
                </div>
              </div>

              {/* Error Message */}
              {status?.error && (
                <div className="rounded-md bg-destructive/10 border border-destructive/20 p-4 text-sm text-destructive">
                  <p className="font-medium">Error:</p>
                  <p className="mt-1">{status.error}</p>
                </div>
              )}

              {/* Pages Progress */}
              {status?.pages && status.pages.length > 0 && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium">
                      Pages Progress
                    </p>
                    <p className="text-sm text-muted-foreground">
                      {status.pages.filter((p: any) => p.status === "completed").length} /{" "}
                      {status.total_pages} completed
                      {status.pages.filter((p: any) => p.status === "failed").length > 0 && (
                        <span className="text-destructive ml-2">
                          ({status.pages.filter((p: any) => p.status === "failed").length} failed)
                        </span>
                      )}
                    </p>
                  </div>

                  {/* Pages Grid */}
                  <div className="grid grid-cols-5 sm:grid-cols-8 md:grid-cols-10 lg:grid-cols-12 gap-2">
                    {status.pages.map((page: any) => (
                      <div
                        key={page.page_number}
                        className="relative"
                      >
                        <button
                          onClick={(e) => handlePageClick(page.page_number, page.status, e)}
                          disabled={page.status !== "completed" && page.status !== "failed"}
                          className={`
                            relative w-full h-10 sm:h-9 md:h-8 rounded border-2 flex items-center justify-center text-xs font-medium transition-all cursor-pointer hover:scale-105 active:scale-95 disabled:cursor-not-allowed disabled:hover:scale-100
                            ${
                              page.status === "completed"
                                ? "bg-green-500/10 border-green-500/50 text-green-700 dark:text-green-400 hover:bg-green-500/20"
                                : page.status === "failed"
                                ? "bg-red-500/10 border-red-500/50 text-red-700 dark:text-red-400 hover:bg-red-500/20"
                                : page.status === "processing"
                                ? "bg-blue-500/10 border-blue-500/50 text-blue-700 dark:text-blue-400 animate-pulse"
                                : "bg-yellow-500/10 border-yellow-500/50 text-yellow-700 dark:text-yellow-400 hover:bg-yellow-500/20"
                            }
                          `}
                          title={`Page ${page.page_number}: ${page.status}${page.status === "completed" ? " - Click to view" : page.status === "failed" ? " - Click to retry" : ""}`}
                        >
                          {page.page_number}

                          {/* Status indicator */}
                          <div className="absolute -top-1 -right-1">
                            {page.status === "completed" && (
                              <CheckCircle2 className="h-3 w-3 text-green-600 dark:text-green-400" />
                            )}
                            {page.status === "failed" && (
                              <XCircle className="h-3 w-3 text-red-600 dark:text-red-400" />
                            )}
                            {page.status === "processing" && (
                              <Loader2 className="h-3 w-3 text-blue-600 dark:text-blue-400 animate-spin" />
                            )}
                            {page.status === "queued" && (
                              <Clock className="h-3 w-3 text-yellow-600 dark:text-yellow-400" />
                            )}
                          </div>
                        </button>

                        {/* Retry button for failed pages */}
                        {page.status === "failed" && (
                          <button
                            data-retry
                            onClick={(e) => handleRetryPage(page.job_id, e)}
                            disabled={retryPageMutation.isPending}
                            className="absolute -bottom-1 left-1/2 -translate-x-1/2 bg-destructive hover:bg-destructive/90 text-destructive-foreground rounded-full p-0.5 shadow-sm hover:shadow-md transition-all disabled:opacity-50"
                            title="Retry this page"
                          >
                            <RotateCw className={`h-2.5 w-2.5 ${retryPageMutation.isPending ? 'animate-spin' : ''}`} />
                          </button>
                        )}
                      </div>
                    ))}
                  </div>

                  {/* Legend */}
                  <div className="flex flex-wrap gap-4 text-xs text-muted-foreground pt-2 border-t">
                    <div className="flex items-center gap-1">
                      <CheckCircle2 className="h-3 w-3 text-green-600 dark:text-green-400" />
                      <span>Completed</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <Loader2 className="h-3 w-3 text-blue-600 dark:text-blue-400" />
                      <span>Processing</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <Clock className="h-3 w-3 text-yellow-600 dark:text-yellow-400" />
                      <span>Queued</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <XCircle className="h-3 w-3 text-red-600 dark:text-red-400" />
                      <span>Failed</span>
                    </div>
                  </div>
                </div>
              )}

              {/* Actions */}
              {status?.status === "completed" && (
                <div className="flex gap-4">
                  <Button onClick={() => setShowResult(!showResult)} className="flex-1">
                    <FileText className="h-4 w-4 mr-2" />
                    {showResult ? "Hide" : "View"} Result
                  </Button>
                  <Button onClick={downloadMarkdown} variant="outline">
                    <Download className="h-4 w-4 mr-2" />
                    Download
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Result Card */}
          {showResult && result && (
            <Card>
              <CardHeader>
                <CardTitle>Markdown Output</CardTitle>
                <CardDescription>
                  Job result
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="bg-muted rounded-lg p-4 max-h-[600px] overflow-y-auto">
                  <pre className="text-sm whitespace-pre-wrap font-mono">
                    {result.markdown}
                  </pre>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </main>

      {/* Page Result Dialog */}
      <Dialog open={pageDialogOpen} onOpenChange={setPageDialogOpen}>
        <DialogContent className="max-w-4xl max-h-[80vh] overflow-hidden flex flex-col">
          <DialogHeader>
            <DialogTitle>Page {selectedPage} - Markdown Result</DialogTitle>
            <DialogDescription>
              Page result coming soon!
            </DialogDescription>
          </DialogHeader>

          <div className="py-12 text-center text-muted-foreground">
            Individual page results coming soon!
          </div>
        </DialogContent>
      </Dialog>

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
  );
}
