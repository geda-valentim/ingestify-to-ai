"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, AudioLines, Braces, FileInput, KeyRound, Search, Workflow } from "lucide-react";
import { AppHeader } from "@/components/app-header";
import { Button } from "@/components/ui/button";
import { API_URL, jobsApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store/auth";
import { loginUrl } from "@/lib/session";

const capabilities = [
  { title: "Convert files", description: "Turn documents, images and recordings into usable text.", href: "/convert", icon: FileInput },
  { title: "Live transcription", description: "Capture speech and follow your transcript as it arrives.", href: "/live", icon: AudioLines },
  { title: "Jobs & search", description: "Track processing and find content you have already ingested.", href: "/jobs", icon: Search },
  { title: "Build with agents", description: "Connect ingestion, progress, reading and search as tools.", href: "/agents", icon: Workflow },
];

const statusStyle: Record<string, string> = {
  completed: "bg-emerald-50 text-emerald-800",
  failed: "bg-red-50 text-red-800",
  processing: "bg-blue-50 text-blue-800",
  queued: "bg-amber-50 text-amber-800",
  cancelled: "bg-secondary text-muted-foreground",
};

export function DashboardOverview() {
  const router = useRouter();
  const token = useAuthStore(state => state.token);
  const user = useAuthStore(state => state.user);
  const hydrated = useAuthStore(state => state._hasHydrated);
  const authenticated = !!token && !!user;
  useEffect(() => {
    if (hydrated && !authenticated) router.replace(loginUrl());
  }, [hydrated, authenticated, router]);
  const jobs = useQuery({
    queryKey: ["dashboard-jobs", token],
    queryFn: () => jobsApi.list({ limit: 5, job_type: "main" }),
    enabled: hydrated && authenticated,
    refetchInterval: 30_000,
    retry: 1,
  });
  if (!hydrated || !authenticated) {
    return <div className="flex min-h-screen items-center justify-center text-muted-foreground">Loading workspace…</div>;
  }
  const counts = jobs.data?.counts;
  const stats = [
    { label: "Total jobs", value: counts?.all, href: "/jobs" },
    { label: "In progress", value: counts ? counts.queued + counts.processing : undefined, href: "/jobs" },
    { label: "Completed", value: counts?.completed, href: "/jobs?status=completed" },
    { label: "Failed", value: counts?.failed, href: "/jobs?status=failed" },
  ];
  return (
    <div className="min-h-screen bg-background">
      <AppHeader />
      <main className="mx-auto max-w-6xl space-y-8 px-4 py-8 sm:px-6 sm:py-12">
        <div className="flex flex-wrap items-end justify-between gap-5">
          <div>
            <p className="mb-2 text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">Dashboard</p>
            <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Your data workspace.</h1>
            <p className="mt-3 max-w-xl text-sm leading-relaxed text-muted-foreground">Convert for AI. Connect your data. Keep your operations in view.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button asChild variant="outline"><Link href="/api-keys"><KeyRound className="mr-2 h-4 w-4" aria-hidden="true" />API keys</Link></Button>
            <Button asChild><Link href="/convert">Convert a file<ArrowUpRight className="ml-2 h-4 w-4" aria-hidden="true" /></Link></Button>
          </div>
        </div>

        <section aria-label="Job overview" className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {stats.map(stat => <Link key={stat.label} href={stat.href} className="rounded-xl border p-5 transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            <p className="text-xs text-muted-foreground">{stat.label}</p>
            <p className="mt-2 text-3xl font-semibold tabular-nums" aria-label={stat.value === undefined ? `${stat.label}: unavailable` : undefined}>{stat.value?.toLocaleString() ?? "—"}</p>
          </Link>)}
        </section>

        <section aria-labelledby="api-heading" className="relative overflow-hidden rounded-2xl border bg-zinc-950 text-white">
          <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-pink-400 via-amber-300 to-blue-400" />
          <div className="grid gap-8 p-6 sm:p-8 lg:grid-cols-[1.1fr_1fr]">
            <div>
              <p className="mb-4 flex items-center gap-2 text-xs font-medium uppercase tracking-[0.16em] text-zinc-400"><Braces className="h-4 w-4" aria-hidden="true" />Build with the API</p>
              <h2 id="api-heading" className="text-2xl font-medium tracking-tight">The same operations.<br />Inside your own workflow.</h2>
              <p className="mt-3 max-w-md text-sm leading-relaxed text-zinc-400">Submit a file, track its job and retrieve the result. Connect Ingestify to your applications, data pipelines and agents.</p>
              <div className="mt-6 flex flex-wrap gap-3 text-sm">
                <Link href="/api-keys" className="rounded-md bg-white px-4 py-2 font-medium text-black hover:bg-zinc-200">Manage API keys</Link>
                <Link href="/docs/documents" className="rounded-md border border-zinc-700 px-4 py-2 hover:bg-zinc-800">Read API docs ↗</Link>
              </div>
            </div>
            <div className="min-w-0 self-center rounded-xl border border-zinc-800 bg-black/30 p-5">
              <p className="mb-4 text-xs text-zinc-400">YOUR FIRST REQUEST</p>
              <pre className="overflow-x-auto pb-3 text-xs leading-7 text-zinc-200" tabIndex={0} aria-label="Example upload request"><code>{`curl -X POST "${API_URL}/upload" \\\n  -H "X-API-Key: YOUR_API_KEY" \\\n  -F "file=@report.pdf"`}</code></pre>
              <p className="mt-3 border-t border-zinc-800 pt-3 text-xs leading-relaxed text-zinc-400">Use an API key from your account. This example is not executed.</p>
            </div>
          </div>
        </section>

        <section aria-labelledby="recent-heading" className="overflow-hidden rounded-xl border">
          <div className="flex items-center justify-between gap-3 border-b px-5 py-4">
            <div><h2 id="recent-heading" className="font-semibold">Recent jobs</h2><p className="mt-1 text-xs text-muted-foreground">Your latest conversions · refreshes every 30 seconds</p></div>
            <Link href="/jobs" className="shrink-0 text-sm underline underline-offset-4">View all jobs</Link>
          </div>
          {jobs.isError && <div role="alert" className="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-4 text-sm"><span>Could not refresh jobs. {jobs.data ? "Showing the last available data." : "Try again to load your activity."}</span><Button variant="outline" size="sm" onClick={() => jobs.refetch()} disabled={jobs.isFetching}>Retry</Button></div>}
          {jobs.isPending ? <p role="status" className="p-8 text-center text-sm text-muted-foreground">Loading your activity…</p> : jobs.data?.jobs.length ? (
            <ul className="divide-y">{jobs.data.jobs.map(job => <li key={job.job_id}>
              <Link href={`/jobs/${encodeURIComponent(job.job_id)}`} className="flex items-center gap-3 px-5 py-4 transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring">
                <div className="min-w-0 flex-1"><p className="truncate text-sm font-medium">{job.name || job.filename || job.job_id}</p><p className="mt-1 truncate text-xs text-muted-foreground">{job.project?.name || "No project"} · {job.kind || "Conversion"}</p></div>
                <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs capitalize ${statusStyle[job.status] || "bg-secondary"}`}>{job.status}</span>
                <ArrowUpRight className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
              </Link>
            </li>)}</ul>
          ) : jobs.data && <div className="px-5 py-10 text-center"><p className="font-medium">Your first job starts here.</p><p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">Convert a file in the workspace or submit it through the API. Follow its progress here.</p><Link href="/convert" className="mt-4 inline-block text-sm underline underline-offset-4">Start a conversion</Link></div>}
        </section>

        <section aria-labelledby="tools-heading">
          <h2 id="tools-heading" className="mb-4 font-semibold">Explore your workspace</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{capabilities.map(({ title, description, href, icon: Icon }) => (
            <Link key={href} href={href} className="group rounded-xl border p-5 transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
              <div className="mb-5 flex items-center justify-between"><Icon className="h-5 w-5" aria-hidden="true" /><ArrowUpRight className="h-4 w-4 text-muted-foreground" aria-hidden="true" /></div>
              <h3 className="text-sm font-medium">{title}</h3><p className="mt-2 text-xs leading-relaxed text-muted-foreground">{description}</p>
            </Link>
          ))}</div>
        </section>
      </main>
    </div>
  );
}
