// Pure helpers behind the job page's live document (components/job/live-document.tsx).
// No imports: tests/live-document.test.cjs loads this file on its own.

/** "skipped": the job settled without converting this page (no work is going on for it). */
export type LivePageState = "done" | "converting" | "queued" | "failed" | "skipped";

const SETTLED = ["completed", "partial", "failed", "cancelled"];

export interface LivePageInput {
  page_number: number;
  job_id: string | null;
  status: string;
  error_message?: string | null;
  retry_count?: number;
}

export interface LiveSlot {
  page_number: number;
  job_id: string | null;
  state: LivePageState;
  error_message: string | null;
  retry_count: number;
}

export function pageState(status: string | undefined | null, jobStatus?: string | null): LivePageState {
  const settled = !!jobStatus && SETTLED.includes(jobStatus);
  if (status === "failed") return "failed";
  // The pages poll stops when the job settles, so its last answer can be one beat
  // behind: a completed job has converted every page that did not fail.
  if (status === "completed" || jobStatus === "completed") return "done";
  if (settled) return "skipped";
  if (status === "processing") return "converting";
  return "queued";
}

/**
 * One slot per page 1..total in page order. Pages the API has not listed yet
 * (the split task is still creating jobs) are queued slots without a job id;
 * duplicates keep the last entry; entries beyond `total` are kept too.
 * `jobStatus` is the main job's status: it settles pages the poll left behind.
 */
export function buildSlots(pages: LivePageInput[], total: number, jobStatus?: string | null): LiveSlot[] {
  const byNumber = new Map<number, LivePageInput>();
  for (const page of pages) byNumber.set(page.page_number, page);
  const count = Math.max(total, ...Array.from(byNumber.keys()), 0);
  const slots: LiveSlot[] = [];
  for (let n = 1; n <= count; n++) {
    const page = byNumber.get(n);
    slots.push({
      page_number: n,
      job_id: page?.job_id ?? null,
      state: pageState(page?.status, jobStatus),
      error_message: page?.error_message ?? null,
      retry_count: page?.retry_count ?? 0,
    });
  }
  return slots;
}

export function countStates(slots: LiveSlot[]): Record<LivePageState, number> {
  const counts: Record<LivePageState, number> = { done: 0, converting: 0, queued: 0, failed: 0, skipped: 0 };
  for (const slot of slots) counts[slot.state] += 1;
  return counts;
}

/** A slot whose Markdown can be requested (by main job + page number, so no job id is needed). */
export function isFetchable(slot: LiveSlot): boolean {
  return slot.state === "done";
}

/** Reuse the previous slot objects whose content did not change, so memoised pages skip re-rendering. */
export function reuseSlots(prev: LiveSlot[], next: LiveSlot[]): LiveSlot[] {
  const old = new Map<number, LiveSlot>();
  for (const slot of prev) old.set(slot.page_number, slot);
  let same = prev.length === next.length;
  const out = next.map((slot, i) => {
    const o = old.get(slot.page_number);
    const equal =
      !!o &&
      o.job_id === slot.job_id &&
      o.state === slot.state &&
      o.error_message === slot.error_message &&
      o.retry_count === slot.retry_count;
    if (!equal || prev[i] !== o) same = false;
    return equal ? o! : slot;
  });
  return same ? prev : out;
}

/**
 * Runs async tasks with at most `limit` in flight. A task still waiting when its
 * `signal` aborts leaves the queue and rejects with an AbortError. `lifo` starts
 * the most recently queued task first: the page the reader just jumped to goes
 * before the ones queued while scrolling past.
 */
export function createLimiter(limit: number, options: { lifo?: boolean } = {}) {
  let active = 0;
  const waiting: Array<{ start: () => void }> = [];
  const next = () => {
    if (active >= limit) return;
    const entry = options.lifo ? waiting.pop() : waiting.shift();
    if (entry) entry.start();
  };
  return function run<T>(task: () => Promise<T>, signal?: AbortSignal): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      const abortError = () => {
        const e = new Error("Aborted");
        e.name = "AbortError";
        return e;
      };
      if (signal?.aborted) return reject(abortError());
      const entry = {
        start: () => {
          signal?.removeEventListener("abort", onAbort);
          active += 1;
          task()
            .then(resolve, reject)
            .finally(() => {
              active -= 1;
              next();
            });
        },
      };
      function onAbort() {
        const i = waiting.indexOf(entry);
        if (i >= 0) {
          waiting.splice(i, 1);
          reject(abortError());
        }
      }
      signal?.addEventListener("abort", onAbort);
      waiting.push(entry);
      next();
    });
  };
}

export interface TrailSegment {
  from: number;
  to: number;
  state: LivePageState;
}

/**
 * The trail (one segment per page, or per bucket of pages beyond `max`).
 * A bucket shows its most urgent state: failed, else done only if all are,
 * else converting if any page converts or some are done and others wait, else queued;
 * a bucket only of converted and unconverted-but-settled pages reads as skipped.
 */
export function trailSegments(slots: LiveSlot[], max: number): TrailSegment[] {
  const size = Math.max(1, Math.ceil(slots.length / Math.max(1, max)));
  const out: TrailSegment[] = [];
  for (let i = 0; i < slots.length; i += size) {
    const chunk = slots.slice(i, i + size);
    const c = countStates(chunk);
    let state: LivePageState;
    if (c.failed > 0) state = "failed";
    else if (c.done === chunk.length) state = "done";
    else if (c.converting > 0) state = "converting";
    else if (c.queued > 0) state = c.done > 0 ? "converting" : "queued";
    else state = "skipped";
    out.push({ from: chunk[0].page_number, to: chunk[chunk.length - 1].page_number, state });
  }
  return out;
}
