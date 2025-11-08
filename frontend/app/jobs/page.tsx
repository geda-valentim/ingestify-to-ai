"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Search,
  FileText,
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  Trash2,
} from "lucide-react";
import { jobsApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store/auth";
import { formatApiError } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
import { formatDistanceToNow } from "date-fns";
import { useToast } from "@/hooks/use-toast";
import type { JobStatus } from "@/types/api";

export default function JobsListPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const token = useAuthStore((state) => state.token);
  const isAuthenticated = useAuthStore((state) => state.token !== null && state.user !== null);
  const hasHydrated = useAuthStore((state) => state._hasHydrated);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<JobStatus | "all">("all");
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [jobToDelete, setJobToDelete] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 20;

  useEffect(() => {
    if (hasHydrated && !isAuthenticated) {
      router.push("/login");
    }
  }, [isAuthenticated, hasHydrated, router]);

  // Reset page when filter changes
  useEffect(() => {
    setPage(0);
  }, [statusFilter]);

  const { data: jobsData, isLoading, error } = useQuery({
    queryKey: ["jobs", statusFilter, page, token],
    queryFn: () => jobsApi.list({
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE,
      status: statusFilter === "all" ? undefined : statusFilter,
      job_type: "main",
    }),
    refetchInterval: 10000, // Refresh every 10 seconds
    enabled: !!token,
  });

  const { data: searchData, isLoading: isSearching } = useQuery({
    queryKey: ["search", searchQuery, token],
    queryFn: () => jobsApi.search({
      query: searchQuery,
      limit: 100,
    }),
    enabled: searchQuery.length > 0 && !!token,
  });

  const deleteMutation = useMutation({
    mutationFn: (jobId: string) => Promise.resolve(), // Delete not implemented yet
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      toast({
        title: "Job deleted",
        description: "The job has been successfully deleted.",
      });
      setDeleteDialogOpen(false);
      setJobToDelete(null);
    },
    onError: (error: any) => {
      toast({
        title: "Error deleting job",
        description: formatApiError(error),
        variant: "destructive",
      });
    },
  });

  const handleDeleteClick = (jobId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setJobToDelete(jobId);
    setDeleteDialogOpen(true);
  };

  const handleDeleteConfirm = () => {
    if (jobToDelete) {
      deleteMutation.mutate(jobToDelete);
    }
  };

  const jobs = jobsData || [];
  const searchResults = searchData || [];
  const displayJobs = searchQuery ? searchResults : jobs;
  const totalPages = Math.ceil(jobs.length / PAGE_SIZE);
  const hasNextPage = page < totalPages - 1;
  const hasPrevPage = page > 0;

  const formatDate = (dateString: string | undefined) => {
    if (!dateString) return "Unknown";
    try {
      const date = new Date(dateString);
      if (isNaN(date.getTime())) return "Unknown";
      return formatDistanceToNow(date, { addSuffix: true });
    } catch {
      return "Unknown";
    }
  };

  const getStatusIcon = (status: JobStatus) => {
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

  const getStatusColor = (status: JobStatus) => {
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

  return (
    <div className="min-h-screen bg-gradient-to-br from-background via-background to-muted">
      {/* Header */}
      <header className="border-b bg-background/95 backdrop-blur">
        <div className="container mx-auto px-4 py-4">
          <Button variant="ghost" onClick={() => router.push("/dashboard")}>
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Dashboard
          </Button>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-4 py-12">
        <div className="max-w-5xl mx-auto space-y-6">
          <div>
            <h1 className="text-3xl font-bold">My Jobs</h1>
            <p className="text-muted-foreground mt-1">
              View and manage your document conversion jobs
            </p>
          </div>

          {/* Search and Filter */}
          <Card>
            <CardContent className="pt-6">
              <div className="flex flex-col md:flex-row gap-4">
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Search jobs by content..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-9"
                  />
                </div>
                <div className="flex gap-2">
                  {["all", "queued", "processing", "completed", "failed"].map((status) => (
                    <Button
                      key={status}
                      variant={statusFilter === status ? "default" : "outline"}
                      size="sm"
                      onClick={() => setStatusFilter(status as JobStatus | "all")}
                      className="capitalize"
                    >
                      {status}
                    </Button>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Jobs List */}
          {error && (
            <Card className="border-destructive">
              <CardContent className="py-6 text-center text-destructive">
                <XCircle className="h-12 w-12 mx-auto mb-4" />
                <p className="font-semibold">Error loading jobs</p>
                <p className="text-sm mt-2">{error instanceof Error ? error.message : "Unknown error"}</p>
              </CardContent>
            </Card>
          )}
          {isLoading || isSearching ? (
            <div className="flex justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
          ) : displayJobs && displayJobs.length > 0 ? (
            <div className="space-y-4">
              {displayJobs.map((job) => (
                <Card
                  key={job.job_id}
                  className="hover:shadow-md transition-shadow cursor-pointer"
                  onClick={() => router.push(`/jobs/${job.job_id}`)}
                >
                  <CardHeader>
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <CardTitle className="text-lg flex items-center gap-2">
                          <FileText className="h-5 w-5" />
                          {job.name || job.job_id}
                        </CardTitle>
                        <CardDescription className="mt-1">
                          Created {formatDate(job.created_at)}
                        </CardDescription>
                      </div>
                      <div className="flex items-center gap-3">
                        {getStatusIcon(job.status)}
                        <span className={`font-medium capitalize ${getStatusColor(job.status)}`}>
                          {job.status}
                        </span>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="text-destructive hover:text-destructive hover:bg-destructive/10"
                          onClick={(e) => handleDeleteClick(job.job_id, e)}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="flex items-center justify-between">
                      <div className="text-sm text-muted-foreground">
                        {job.total_pages && (
                          <span>
                            {job.pages_completed || 0} / {job.total_pages} pages completed
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-4 text-sm">
                        <span className="text-muted-foreground">
                          Progress: <span className="font-medium">{job.progress}%</span>
                        </span>
                        {job.completed_at && (
                          <span className="text-muted-foreground">
                            Completed {formatDate(job.completed_at)}
                          </span>
                        )}
                      </div>
                    </div>
                    {/* Progress Bar */}
                    <div className="w-full bg-secondary rounded-full h-1.5 mt-3">
                      <div
                        className="bg-primary h-1.5 rounded-full transition-all duration-300"
                        style={{ width: `${job.progress}%` }}
                      />
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : (
            <Card>
              <CardContent className="py-12 text-center text-muted-foreground">
                <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p>No jobs found</p>
                {searchQuery && <p className="text-sm mt-2">Try a different search query</p>}
              </CardContent>
            </Card>
          )}

          {/* Pagination Controls */}
          {!searchQuery && jobs.length > 0 && (
            <Card>
              <CardContent className="py-4">
                <div className="flex items-center justify-between">
                  <div className="text-sm text-muted-foreground">
                    Showing {page * PAGE_SIZE + 1} - {Math.min((page + 1) * PAGE_SIZE, jobs.length)} of {jobs.length} jobs
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setPage(p => Math.max(0, p - 1))}
                      disabled={!hasPrevPage || isLoading}
                    >
                      Previous
                    </Button>
                    <div className="text-sm text-muted-foreground px-2">
                      Page {page + 1} of {totalPages}
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setPage(p => p + 1)}
                      disabled={!hasNextPage || isLoading}
                    >
                      Next
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </main>

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
