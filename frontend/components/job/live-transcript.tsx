"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowDown } from "lucide-react";
import { jobsApi } from "@/lib/api";
import { cn, formatDuration } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import type { JobStatusResponse, TranscriptSegment } from "@/types/api";

const POLL_MS = 3000;

/**
 * The text of a running transcription, polled every 3s and accumulated: each
 * request asks only for the segments after the ones already received. Empty for
 * providers that return the whole file at once (only faster-whisper streams).
 */
export function useLiveTranscript(jobId: string, active: boolean): TranscriptSegment[] {
  const [segments, setSegments] = useState<TranscriptSegment[]>([]);

  useEffect(() => {
    if (!active) return;
    let since = 0;
    let cancelled = false;

    const poll = async () => {
      try {
        const data = await jobsApi.getPartialTranscript(jobId, since);
        if (cancelled) return;
        if (data.next < since) {
          // The transcription restarted (e.g. GPU failed, retrying on CPU): start over
          since = 0;
          setSegments([]);
          return;
        }
        since = data.next;
        if (data.segments.length > 0) {
          setSegments((prev) => [...prev, ...data.segments]);
        }
      } catch {
        // Live text is a nicety: keep polling, the final result still arrives
      }
    };

    setSegments([]);
    poll();
    const timer = setInterval(poll, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [jobId, active]);

  return segments;
}

/**
 * How many of the received segments to show. Segments arrive in batches every
 * few seconds; revealing them one at a time across the poll interval makes the
 * text flow in like captions instead of jumping a block at a time.
 */
function useReveal(total: number): number {
  const [shown, setShown] = useState(0);

  useEffect(() => {
    if (total < shown) {
      setShown(total); // the list was reset
      return;
    }
    if (shown === total) return;
    const pending = total - shown;
    const delay = Math.max(80, Math.min(700, (POLL_MS * 0.9) / pending));
    const timer = setTimeout(() => setShown((n) => n + 1), delay);
    return () => clearTimeout(timer);
  }, [total, shown]);

  return shown;
}

/**
 * The job page while a transcription runs: a live badge, how far into the media
 * it is, and the captions so far, the newest highlighted and a typing indicator
 * at the end. Follows the newest line like a terminal unless the reader scrolled
 * up, in which case a button offers to jump back.
 */
export function LiveTranscriptView({
  status,
  segments,
}: {
  status: JobStatusResponse;
  segments: TranscriptSegment[];
}) {
  const shown = useReveal(segments.length);
  const visible = segments.slice(0, shown);
  const containerRef = useRef<HTMLDivElement>(null);
  const [following, setFollowing] = useState(true);
  const [seenWhileAway, setSeenWhileAway] = useState(0);
  const lastScrollTop = useRef(0);

  useEffect(() => {
    const el = containerRef.current;
    if (el && following) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [shown, following]);

  const onScroll = () => {
    const el = containerRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    // Only the reader scrolls up; following the text (even smoothly) only scrolls down
    const scrolledUp = el.scrollTop < lastScrollTop.current - 2;
    lastScrollTop.current = el.scrollTop;
    if (following && scrolledUp && !atBottom) {
      setFollowing(false);
      setSeenWhileAway(shown);
    } else if (!following && atBottom) {
      setFollowing(true);
    }
  };

  const duration = status.media_duration ?? 0;
  const done = Math.min(status.transcribed_seconds ?? 0, duration);
  const share = duration > 0 ? (done / duration) * 100 : 0;
  const words = visible.reduce((n, s) => n + s.text.split(/\s+/).filter(Boolean).length, 0);
  const newLines = following ? 0 : shown - seenWhileAway;
  const last = visible[visible.length - 1];

  return (
    <div className="relative flex-1 min-h-0 flex flex-col">
      <div ref={containerRef} onScroll={onScroll} className="flex-1 overflow-y-auto p-4 md:p-6 space-y-4">
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-red-500/10 px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide text-red-600 dark:text-red-400">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-500 opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-red-500" />
              </span>
              Live
            </span>
            <h2 className="text-xl font-semibold">Transcribing…</h2>
          </div>

          {duration > 0 && (
            <div className="space-y-1.5">
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-primary transition-[width] duration-1000 ease-out"
                  style={{ width: `${share}%` }}
                />
              </div>
              <div className="flex flex-wrap justify-between gap-2 text-xs text-muted-foreground tabular-nums">
                <span>
                  {formatDuration(done)} of {formatDuration(duration)} transcribed · {Math.floor(share)}%
                </span>
                {visible.length > 0 && (
                  <span>
                    {visible.length} lines · {words} words
                  </span>
                )}
              </div>
            </div>
          )}
        </div>

        <div className="border rounded-lg bg-muted/30 p-4 md:p-6">
          <ol className="space-y-1">
            {visible.map((segment, i) => {
              const newest = i === visible.length - 1;
              return (
                <li
                  key={`${segment.start}-${segment.end}`}
                  className={cn(
                    "flex gap-4 rounded-md px-2 py-2 border-l-2 transition-colors duration-1000",
                    "animate-in fade-in slide-in-from-bottom-2 duration-500",
                    newest ? "border-primary bg-primary/5" : "border-transparent"
                  )}
                >
                  <span className="shrink-0 w-14 pt-0.5 font-mono text-xs text-muted-foreground tabular-nums">
                    {formatDuration(segment.start)}
                  </span>
                  <span className={cn("text-sm leading-relaxed", !newest && "text-foreground/85")}>
                    {segment.text}
                  </span>
                </li>
              );
            })}
            <li className="flex gap-4 px-2 py-2" aria-live="polite">
              <span className="shrink-0 w-14 pt-0.5 font-mono text-xs text-muted-foreground/60 tabular-nums">
                {last ? formatDuration(last.end) : formatDuration(0)}
              </span>
              <span className="flex items-center gap-1 text-sm text-muted-foreground">
                {!last && <span className="mr-2">Listening — the first lines show up in a few seconds</span>}
                {[0, 150, 300].map((delay) => (
                  <span
                    key={delay}
                    className="h-1.5 w-1.5 rounded-full bg-muted-foreground/60 animate-bounce"
                    style={{ animationDelay: `${delay}ms` }}
                  />
                ))}
              </span>
            </li>
          </ol>
        </div>
      </div>

      {!following && (
        <Button
          size="sm"
          className="absolute bottom-4 left-1/2 -translate-x-1/2 shadow-lg animate-in fade-in slide-in-from-bottom-2"
          onClick={() => {
            setFollowing(true);
            containerRef.current?.scrollTo({ top: containerRef.current.scrollHeight, behavior: "smooth" });
          }}
        >
          <ArrowDown className="h-4 w-4 mr-1.5" />
          {newLines > 0 ? `${newLines} new ${newLines === 1 ? "line" : "lines"}` : "Back to live"}
        </Button>
      )}
    </div>
  );
}
