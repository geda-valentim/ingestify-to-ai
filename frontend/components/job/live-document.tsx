"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertCircle, CheckCircle2, Clock, Columns2, Loader2, RotateCw, XCircle } from "lucide-react";
import { jobsApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  buildSlots,
  countStates,
  createLimiter,
  isFetchable,
  trailSegments,
  type LivePageInput,
  type LivePageState,
  type LiveSlot,
} from "@/lib/live-document";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { MarkdownView } from "@/components/markdown-view";
import { engineKindLabel, queueReasonText } from "./job-progress";
import type { JobStatusResponse } from "@/types/api";

// Page Markdown is fetched on demand, a few requests at a time, however long the PDF.
const MAX_PAGE_REQUESTS = 4;
const limitPageRequests = createLimiter(MAX_PAGE_REQUESTS);
// Start loading a page a couple of screens before it is reached.
const NEAR_MARGIN = "1200px 0px";
const TRAIL_MAX_SEGMENTS = 120;
const MAX_PAGE_RETRIES = 3;

const STATE_LABEL: Record<LivePageState, string> = {
  done: "Converted",
  converting: "Converting",
  queued: "Queued",
  failed: "Failed",
};

const STATE_TRAIL_CLASS: Record<LivePageState, string> = {
  done: "bg-primary",
  converting: "bg-primary/40 motion-safe:animate-pulse",
  queued: "bg-muted-foreground/25",
  failed: "bg-destructive",
};

const STATE_PILL_CLASS: Record<LivePageState, string> = {
  done: "bg-primary/10 text-primary",
  converting: "bg-muted text-foreground",
  queued: "text-muted-foreground ring-1 ring-inset ring-border",
  failed: "bg-destructive/10 text-destructive",
};

function StateIcon({ state, className }: { state: LivePageState; className?: string }) {
  const cls = cn("h-3.5 w-3.5 shrink-0", className);
  if (state === "done") return <CheckCircle2 aria-hidden="true" className={cls} />;
  if (state === "failed") return <XCircle aria-hidden="true" className={cls} />;
  if (state === "converting") return <Loader2 aria-hidden="true" className={cn(cls, "motion-safe:animate-spin")} />;
  return <Clock aria-hidden="true" className={cls} />;
}

function StatePill({ state, children }: { state: LivePageState; children: ReactNode }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium tabular-nums",
        STATE_PILL_CLASS[state],
      )}
    >
      <StateIcon state={state} />
      {children}
    </span>
  );
}

/** True from the moment the element gets within NEAR_MARGIN of the viewport, and stays true. */
function useNearViewport<T extends Element>() {
  const ref = useRef<T | null>(null);
  const [near, setNear] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || near) return;
    if (typeof IntersectionObserver === "undefined") {
      setNear(true);
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setNear(true);
          observer.disconnect();
        }
      },
      { rootMargin: NEAR_MARGIN },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [near]);
  return { ref, near };
}

function scrollToPage(pageNumber: number) {
  const el = document.getElementById(`live-page-${pageNumber}`);
  if (!el) return;
  const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  el.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
}

/** Segmented switch between the page-by-page document and the merged result. */
export function LiveViewToggle({
  value,
  onChange,
}: {
  value: "pages" | "merged";
  onChange: (value: "pages" | "merged") => void;
}) {
  const options: Array<["pages" | "merged", string]> = [
    ["pages", "Pages"],
    ["merged", "Merged document"],
  ];
  return (
    <div role="group" aria-label="Document view" className="inline-flex rounded-md border p-0.5 text-xs">
      {options.map(([key, label]) => (
        <button
          key={key}
          type="button"
          aria-pressed={value === key}
          onClick={() => onChange(key)}
          className={cn(
            "rounded px-2.5 py-1 font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            value === key ? "bg-secondary text-secondary-foreground" : "text-muted-foreground hover:text-foreground",
          )}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function PageTrail({ slots }: { slots: LiveSlot[] }) {
  const segments = useMemo(() => trailSegments(slots, TRAIL_MAX_SEGMENTS), [slots]);
  const focusable = segments.length <= 40;
  return (
    <div role="group" aria-label="Page map" className="flex h-3 items-stretch gap-px">
      {segments.map((seg) => {
        const label =
          seg.from === seg.to
            ? `Page ${seg.from} · ${STATE_LABEL[seg.state].toLowerCase()}`
            : `Pages ${seg.from}-${seg.to} · ${STATE_LABEL[seg.state].toLowerCase()}`;
        return (
          <button
            key={seg.from}
            type="button"
            title={label}
            aria-label={label}
            tabIndex={focusable ? 0 : -1}
            onClick={() => scrollToPage(seg.from)}
            className="group/seg min-w-[2px] flex-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <span className={cn("block h-full w-full rounded-[1px] group-hover/seg:opacity-70", STATE_TRAIL_CLASS[seg.state])} />
          </button>
        );
      })}
    </div>
  );
}

function PageBody({
  slot,
  token,
  near,
  canRetry,
  retrying,
  onRetry,
}: {
  slot: LiveSlot;
  token: string | null;
  near: boolean;
  canRetry: boolean;
  retrying: boolean;
  onRetry: (pageNumber: number) => void;
}) {
  const fetchable = isFetchable(slot);
  // Same key as the single-page viewer, so a page read there is already cached here.
  // A retried page has a new job id: the key changes and the new text is fetched.
  const query = useQuery({
    queryKey: ["page-result", slot.job_id, token],
    queryFn: () => limitPageRequests(() => jobsApi.getResult(slot.job_id!)),
    enabled: fetchable && near && !!token,
    staleTime: Infinity,
    retry: 1,
    refetchOnWindowFocus: false,
  });

  if (slot.state === "failed") {
    const exhausted = slot.retry_count >= MAX_PAGE_RETRIES;
    return (
      <div className="flex items-start gap-3 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm">
        <AlertCircle aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
        <div className="min-w-0 flex-1 space-y-2">
          <p className="font-medium">This page could not be converted.</p>
          {slot.error_message && (
            <p className="break-words text-xs text-muted-foreground">{slot.error_message}</p>
          )}
          {canRetry && !exhausted ? (
            <Button size="sm" variant="outline" disabled={retrying} onClick={() => onRetry(slot.page_number)}>
              <RotateCw className={cn("mr-2 h-3.5 w-3.5", retrying && "motion-safe:animate-spin")} />
              Try again
            </Button>
          ) : (
            <p className="text-xs text-muted-foreground">
              {exhausted ? "Maximum retry attempts reached." : "It can no longer be retried: the original file was deleted."}
            </p>
          )}
        </div>
      </div>
    );
  }

  if (slot.state === "queued" || slot.state === "converting") {
    return (
      <div
        className="flex items-center gap-2 rounded-md bg-muted/50 px-3 py-4 text-sm text-muted-foreground motion-safe:animate-pulse"
        role="status"
      >
        <StateIcon state={slot.state} />
        {slot.state === "converting" ? "Converting this page…" : "Waiting in the queue"}
      </div>
    );
  }

  // Converted
  if (query.data) {
    const markdown = query.data.result.markdown;
    return markdown.trim() ? (
      <MarkdownView content={markdown} className="text-[0.9375rem] leading-7" />
    ) : (
      <p className="text-sm italic text-muted-foreground">No text on this page.</p>
    );
  }
  if (query.isError) {
    return (
      <div className="flex flex-wrap items-center gap-3 rounded-md border border-dashed p-3 text-sm text-muted-foreground">
        <span>Could not load this page.</span>
        <Button size="sm" variant="outline" onClick={() => void query.refetch()}>
          Reload
        </Button>
      </div>
    );
  }
  return <div className="h-48 rounded-md bg-muted/50 motion-safe:animate-pulse" aria-label="Loading page" role="status" />;
}

function LivePage({
  slot,
  token,
  canRetry,
  retrying,
  onRetry,
  onOpenPage,
}: {
  slot: LiveSlot;
  token: string | null;
  canRetry: boolean;
  retrying: boolean;
  onRetry: (pageNumber: number) => void;
  onOpenPage: (pageNumber: number) => void;
}) {
  const { ref, near } = useNearViewport<HTMLElement>();
  return (
    <section ref={ref} id={`live-page-${slot.page_number}`} aria-label={`Page ${slot.page_number}`} className="scroll-mt-40 lg:scroll-mt-32">
      <div className="mb-3 flex items-center gap-3">
        <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground tabular-nums">
          Page {slot.page_number}
        </span>
        <span aria-hidden="true" className="h-px flex-1 bg-border" />
        {slot.state !== "done" && <StatePill state={slot.state}>{STATE_LABEL[slot.state]}</StatePill>}
        {slot.state === "done" && (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs text-muted-foreground"
            onClick={() => onOpenPage(slot.page_number)}
            title="Open this page next to its PDF"
          >
            <Columns2 aria-hidden="true" className="mr-1.5 h-3.5 w-3.5" />
            Open
          </Button>
        )}
      </div>
      <PageBody slot={slot} token={token} near={near} canRetry={canRetry} retrying={retrying} onRetry={onRetry} />
    </section>
  );
}

/**
 * The document as it is being converted: the Markdown of every finished page in
 * page order, a placeholder where a page is not ready, and a progress header that
 * stays on screen while the document scrolls. Page text is requested only when
 * a page nears the viewport, four requests at a time.
 */
export function LiveDocument({
  status,
  pages,
  fileName,
  token,
  canRetry,
  retrying,
  onRetry,
  onOpenPage,
  actions,
}: {
  status: JobStatusResponse;
  pages: LivePageInput[];
  fileName: string;
  token: string | null;
  canRetry: boolean;
  retrying: boolean;
  onRetry: (pageNumber: number) => void;
  onOpenPage: (pageNumber: number) => void;
  actions?: ReactNode;
}) {
  const slots = useMemo(() => buildSlots(pages, status.total_pages ?? 0), [pages, status.total_pages]);
  const counts = useMemo(() => countStates(slots), [slots]);
  const total = slots.length;
  const settled = ["completed", "partial", "failed", "cancelled"].includes(status.status);
  const percent = Math.max(0, Math.min(100, Math.round(status.progress ?? 0)));
  const queueText = queueReasonText(status);
  const where = engineKindLabel(status);

  const handleRetry = useCallback((n: number) => onRetry(n), [onRetry]);

  return (
    <div className="flex-1 min-h-0 lg:overflow-y-auto">
      {/* Progress header: sticks under the app header (mobile) or to the top of this column (lg) */}
      <header className="sticky top-16 lg:top-0 z-[5] border-b bg-background px-4 py-3 md:px-6">
        <div className="mx-auto flex w-full max-w-[72ch] flex-col gap-2.5">
          <div className="flex items-start gap-3">
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium" title={fileName}>
                {fileName}
              </p>
              <p className="text-xs text-muted-foreground tabular-nums">
                {counts.done} of {total} pages converted
                {where && !settled ? ` · ${where}` : ""}
              </p>
            </div>
            <Badge variant="outline" className="shrink-0 capitalize">
              {status.status}
            </Badge>
            <p className="shrink-0 text-3xl font-semibold leading-none tabular-nums" aria-label={`${percent} percent`}>
              {percent}
              <span className="text-base font-normal text-muted-foreground">%</span>
            </p>
          </div>

          <div
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={percent}
            aria-label="Overall progress"
            className="h-1.5 w-full overflow-hidden rounded-full bg-secondary"
          >
            <div className="h-full rounded-full bg-primary transition-[width] duration-300" style={{ width: `${percent}%` }} />
          </div>

          <PageTrail slots={slots} />

          <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
            <StatePill state="done">{counts.done} converted</StatePill>
            {counts.converting > 0 && <StatePill state="converting">{counts.converting} converting</StatePill>}
            {counts.queued > 0 && <StatePill state="queued">{counts.queued} queued</StatePill>}
            {counts.failed > 0 && <StatePill state="failed">{counts.failed} failed</StatePill>}
            {actions && <div className="ml-auto">{actions}</div>}
          </div>
          {queueText && (
            <p className="text-xs text-muted-foreground" role="status">
              {queueText}
            </p>
          )}
        </div>
      </header>

      <article className="mx-auto flex w-full max-w-[72ch] min-w-0 flex-col gap-10 px-4 py-6 md:px-6">
        {slots.map((slot) => (
          <LivePage
            key={slot.page_number}
            slot={slot}
            token={token}
            canRetry={canRetry}
            retrying={retrying}
            onRetry={handleRetry}
            onOpenPage={onOpenPage}
          />
        ))}
      </article>
    </div>
  );
}
