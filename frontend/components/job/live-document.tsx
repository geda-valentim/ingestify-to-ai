"use client";

import {
  createContext,
  memo,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, CheckCircle2, CircleSlash, Clock, Columns2, Loader2, RotateCw, XCircle } from "lucide-react";
import { jobsApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  buildSlots,
  countStates,
  createLimiter,
  isFetchable,
  reuseSlots,
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
// LIFO: the page the reader just jumped to starts before those queued while scrolling past.
const MAX_PAGE_REQUESTS = 4;
const limitPageRequests = createLimiter(MAX_PAGE_REQUESTS, { lifo: true });
// Start loading a page a couple of screens before it is reached.
const NEAR_MARGIN = "1200px 0px";
const MAX_PAGE_RETRIES = 3;
const TRAIL_SEGMENT_PX = 4;
const GO_TO_PAGE_THRESHOLD = 40;

const STATE_LABEL: Record<LivePageState, string> = {
  done: "Converted",
  converting: "Converting",
  queued: "Queued",
  failed: "Failed",
  skipped: "Not converted",
};

const STATE_TRAIL_CLASS: Record<LivePageState, string> = {
  done: "bg-primary",
  converting: "bg-primary/40 motion-safe:animate-pulse",
  queued: "bg-muted-foreground/25",
  failed: "bg-destructive",
  skipped: "bg-muted-foreground/10",
};

const STATE_PILL_CLASS: Record<LivePageState, string> = {
  done: "bg-primary/10 text-primary",
  converting: "bg-muted text-foreground",
  queued: "text-muted-foreground ring-1 ring-inset ring-border",
  failed: "bg-destructive/10 text-destructive",
  skipped: "text-muted-foreground ring-1 ring-inset ring-border",
};

function StateIcon({ state, className }: { state: LivePageState; className?: string }) {
  const cls = cn("h-3.5 w-3.5 shrink-0", className);
  if (state === "done") return <CheckCircle2 aria-hidden="true" className={cls} />;
  if (state === "failed") return <XCircle aria-hidden="true" className={cls} />;
  if (state === "skipped") return <CircleSlash aria-hidden="true" className={cls} />;
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

/**
 * One IntersectionObserver for every page section, rooted at the element that
 * actually scrolls (the column from lg up, the window below it) so the margin
 * counts. Sections register before the root exists, hence the pending list.
 */
class ViewportWatcher {
  private callbacks = new Map<Element, (near: boolean) => void>();
  private observer: IntersectionObserver | null = null;

  attach(root: Element | null) {
    this.observer?.disconnect();
    if (typeof IntersectionObserver === "undefined") {
      this.callbacks.forEach((cb) => cb(true));
      return;
    }
    this.observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) this.callbacks.get(entry.target)?.(entry.isIntersecting);
      },
      { root, rootMargin: NEAR_MARGIN },
    );
    this.callbacks.forEach((_cb, el) => this.observer!.observe(el));
  }

  detach() {
    this.observer?.disconnect();
    this.observer = null;
  }

  observe(el: Element, cb: (near: boolean) => void) {
    this.callbacks.set(el, cb);
    if (typeof IntersectionObserver === "undefined" && !this.observer) cb(true);
    this.observer?.observe(el);
    return () => {
      this.callbacks.delete(el);
      this.observer?.unobserve(el);
    };
  }
}

const ViewportContext = createContext<ViewportWatcher | null>(null);

/** Whether the element is within NEAR_MARGIN of the viewport right now. */
function useNearViewport<T extends Element>() {
  const watcher = useContext(ViewportContext);
  const ref = useRef<T | null>(null);
  const [near, setNear] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || !watcher) {
      setNear(true);
      return;
    }
    return watcher.observe(el, setNear);
  }, [watcher]);
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
  const ref = useRef<HTMLDivElement | null>(null);
  const [max, setMax] = useState(60);
  // As many segments as fit: a few px each, whatever the column width
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([entry]) => {
      const width = entry.contentRect.width;
      if (width > 0) setMax(Math.max(10, Math.floor(width / TRAIL_SEGMENT_PX)));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const segments = useMemo(() => trailSegments(slots, max), [slots, max]);
  const focusable = segments.length <= GO_TO_PAGE_THRESHOLD;
  return (
    <div ref={ref} role="group" aria-label="Page map" className="flex h-3 items-stretch gap-px overflow-hidden">
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

/** Keyboard route to any page when the trail has too many segments to tab through. */
function GoToPage({ total }: { total: number }) {
  const [value, setValue] = useState("");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const n = Math.min(total, Math.max(1, parseInt(value, 10) || 0));
    if (n > 0) scrollToPage(n);
  };
  return (
    <form onSubmit={submit} className="flex items-center gap-1.5">
      <label htmlFor="live-go-to-page" className="text-xs text-muted-foreground">
        Go to page
      </label>
      <input
        id="live-go-to-page"
        type="number"
        inputMode="numeric"
        min={1}
        max={total}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        className="h-7 w-16 rounded-md border bg-background px-2 text-xs tabular-nums focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      />
      <Button type="submit" size="sm" variant="outline" className="h-7 px-2 text-xs">
        Go
      </Button>
    </form>
  );
}

function PageBody({
  jobId,
  slot,
  token,
  near,
  canRetry,
  retrying,
  onRetry,
}: {
  jobId: string;
  slot: LiveSlot;
  token: string | null;
  near: boolean;
  canRetry: boolean;
  retrying: boolean;
  onRetry: (pageNumber: number) => void;
}) {
  const queryClient = useQueryClient();
  const fetchable = isFetchable(slot);
  // By main job + page number: the stored page result outlives the Redis cache that
  // GET /jobs/{page_job_id}/result reads. A retried page has a new job id: the key
  // changes and the new text is fetched. Never refetched once cached.
  const queryKey = useMemo(
    () => ["live-page-result", jobId, slot.page_number, slot.job_id, token],
    [jobId, slot.page_number, slot.job_id, token],
  );
  const query = useQuery({
    queryKey,
    queryFn: ({ signal }) => limitPageRequests(() => jobsApi.getPageResult(jobId, slot.page_number, signal), signal),
    enabled: fetchable && near && !!token,
    staleTime: Infinity,
    retry: 1,
    refetchOnWindowFocus: false,
  });

  // Scrolled away while still waiting its turn: drop the request (the limiter
  // removes it from the queue when the signal aborts)
  useEffect(() => {
    if (!near && query.fetchStatus === "fetching") void queryClient.cancelQueries({ queryKey });
  }, [near, query.fetchStatus, queryClient, queryKey]);

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

  if (slot.state === "skipped") {
    return (
      <p className="flex items-center gap-2 rounded-md border border-dashed px-3 py-4 text-sm text-muted-foreground">
        <StateIcon state="skipped" />
        This page was not converted.
      </p>
    );
  }

  if (slot.state === "queued" || slot.state === "converting") {
    return (
      <div className="flex items-center gap-2 rounded-md bg-muted/50 px-3 py-4 text-sm text-muted-foreground motion-safe:animate-pulse">
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
  return <div aria-hidden="true" className="h-48 rounded-md bg-muted/50 motion-safe:animate-pulse" />;
}

interface LivePageProps {
  jobId: string;
  slot: LiveSlot;
  token: string | null;
  canRetry: boolean;
  retrying: boolean;
  onRetry: (pageNumber: number) => void;
  onOpenPage: (pageNumber: number) => void;
}

const LivePage = memo(function LivePage({ jobId, slot, token, canRetry, retrying, onRetry, onOpenPage }: LivePageProps) {
  const { ref, near } = useNearViewport<HTMLElement>();
  return (
    <section
      ref={ref}
      id={`live-page-${slot.page_number}`}
      aria-label={`Page ${slot.page_number}`}
      style={{ scrollMarginTop: "calc(var(--live-sticky-top, 0px) + var(--live-header-h, 8rem) + 1rem)" }}
    >
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
      <PageBody
        jobId={jobId}
        slot={slot}
        token={token}
        near={near}
        canRetry={canRetry}
        retrying={retrying}
        onRetry={onRetry}
      />
    </section>
  );
});

/**
 * The document as it is being converted: the Markdown of every finished page in
 * page order, a placeholder where a page is not ready, and a progress header that
 * stays on screen while the document scrolls. Page text is requested only while
 * a page is near the viewport, four requests at a time.
 *
 * `visible` is false while a single page or the merged result is shown instead:
 * the parent hides this with display:none, which resets scrollTop, so the position
 * is saved on scroll and restored when it is visible again.
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
  visible = true,
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
  visible?: boolean;
}) {
  const prevSlots = useRef<LiveSlot[]>([]);
  const slots = useMemo(() => {
    const next = reuseSlots(prevSlots.current, buildSlots(pages, status.total_pages ?? 0, status.status));
    prevSlots.current = next;
    return next;
  }, [pages, status.total_pages, status.status]);
  const counts = useMemo(() => countStates(slots), [slots]);
  const total = slots.length;
  const settled = ["completed", "partial", "failed", "cancelled"].includes(status.status);
  const percent = Math.max(0, Math.min(100, Math.round(status.progress ?? 0)));
  const queueText = queueReasonText(status);
  const where = engineKindLabel(status);

  // Stable callbacks: pages are memoised and must not re-render on every poll
  const onRetryRef = useRef(onRetry);
  const onOpenRef = useRef(onOpenPage);
  onRetryRef.current = onRetry;
  onOpenRef.current = onOpenPage;
  const handleRetry = useCallback((n: number) => onRetryRef.current(n), []);
  const handleOpen = useCallback((n: number) => onOpenRef.current(n), []);

  const rootRef = useRef<HTMLDivElement | null>(null);
  const headerRef = useRef<HTMLElement | null>(null);
  const [watcher] = useState(() => new ViewportWatcher());

  // The scroller is this column from lg up and the window below; follow the breakpoint
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1024px)");
    const attach = () => watcher.attach(mq.matches ? rootRef.current : null);
    attach();
    mq.addEventListener?.("change", attach);
    return () => {
      mq.removeEventListener?.("change", attach);
      watcher.detach();
    };
  }, [watcher]);

  // Real height of the sticky header, for scroll-margin of the page anchors
  useEffect(() => {
    const header = headerRef.current;
    const root = rootRef.current;
    if (!header || !root || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => {
      const h = header.offsetHeight;
      if (h > 0) root.style.setProperty("--live-header-h", `${h}px`);
    });
    ro.observe(header);
    return () => ro.disconnect();
  }, []);

  // Keep the scroll position across display:none
  const lastTop = useRef(0);
  const handleScroll = useCallback(() => {
    if (rootRef.current && rootRef.current.offsetParent !== null) lastTop.current = rootRef.current.scrollTop;
  }, []);
  useLayoutEffect(() => {
    if (visible && rootRef.current) rootRef.current.scrollTop = lastTop.current;
  }, [visible]);

  return (
    <ViewportContext.Provider value={watcher}>
      <div
        ref={rootRef}
        onScroll={handleScroll}
        className="flex-1 min-h-0 lg:overflow-y-auto [--live-sticky-top:4rem] lg:[--live-sticky-top:0px]"
      >
        {/* Progress header: sticks under the app header (below lg) or to the top of this column */}
        <header
          ref={headerRef}
          className="sticky top-[var(--live-sticky-top)] z-[5] border-b bg-background px-4 py-3 md:px-6"
        >
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
              <p className="shrink-0 text-3xl font-semibold leading-none tabular-nums">
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
              {counts.skipped > 0 && <StatePill state="skipped">{counts.skipped} not converted</StatePill>}
              {total > GO_TO_PAGE_THRESHOLD && <GoToPage total={total} />}
              {actions && <div className="ml-auto">{actions}</div>}
            </div>
            {queueText && <p className="text-xs text-muted-foreground">{queueText}</p>}
            {/* The one live region: a summary, not a announcement per page */}
            <p className="sr-only" role="status" aria-live="polite">
              {counts.done} of {total} pages converted, {percent} percent
            </p>
          </div>
        </header>

        <article className="mx-auto flex w-full max-w-[72ch] min-w-0 flex-col gap-10 px-4 py-6 md:px-6">
          {slots.map((slot) => (
            <LivePage
              key={slot.page_number}
              jobId={status.job_id}
              slot={slot}
              token={token}
              canRetry={canRetry}
              retrying={retrying && slot.state === "failed"}
              onRetry={handleRetry}
              onOpenPage={handleOpen}
            />
          ))}
        </article>
      </div>
    </ViewportContext.Provider>
  );
}
