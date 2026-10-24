// Pure helpers behind the job page's live document (components/job/live-document.tsx).
// No imports: tests/live-document.test.cjs loads this file on its own.

export type LivePageState = "done" | "converting" | "queued" | "failed";

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

export function pageState(status: string | undefined | null): LivePageState {
  if (status === "completed") return "done";
  if (status === "failed") return "failed";
  if (status === "processing") return "converting";
  return "queued";
}

/**
 * One slot per page 1..total in page order. Pages the API has not listed yet
 * (the split task is still creating jobs) are queued slots without a job id;
 * duplicates keep the last entry; entries beyond `total` are kept too.
 */
export function buildSlots(pages: LivePageInput[], total: number): LiveSlot[] {
  const byNumber = new Map<number, LivePageInput>();
  for (const page of pages) byNumber.set(page.page_number, page);
  const count = Math.max(total, ...Array.from(byNumber.keys()), 0);
  const slots: LiveSlot[] = [];
  for (let n = 1; n <= count; n++) {
    const page = byNumber.get(n);
    slots.push({
      page_number: n,
      job_id: page?.job_id ?? null,
      state: pageState(page?.status),
      error_message: page?.error_message ?? null,
      retry_count: page?.retry_count ?? 0,
    });
  }
  return slots;
}

export function countStates(slots: LiveSlot[]): Record<LivePageState, number> {
  const counts: Record<LivePageState, number> = { done: 0, converting: 0, queued: 0, failed: 0 };
  for (const slot of slots) counts[slot.state] += 1;
  return counts;
}

/** A slot whose Markdown can be requested: converted and with a job to ask. */
export function isFetchable(slot: LiveSlot): boolean {
  return slot.state === "done" && !!slot.job_id;
}

/** Runs async tasks with at most `limit` in flight, in the order queued. */
export function createLimiter(limit: number) {
  let active = 0;
  const waiting: Array<() => void> = [];
  const next = () => {
    if (active >= limit) return;
    const start = waiting.shift();
    if (start) start();
  };
  return function run<T>(task: () => Promise<T>): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      waiting.push(() => {
        active += 1;
        task()
          .then(resolve, reject)
          .finally(() => {
            active -= 1;
            next();
          });
      });
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
 * else converting if any page converts or some are done, else queued.
 */
export function trailSegments(slots: LiveSlot[], max: number): TrailSegment[] {
  const size = Math.max(1, Math.ceil(slots.length / Math.max(1, max)));
  const out: TrailSegment[] = [];
  for (let i = 0; i < slots.length; i += size) {
    const chunk = slots.slice(i, i + size);
    const c = countStates(chunk);
    let state: LivePageState = "queued";
    if (c.failed > 0) state = "failed";
    else if (c.done === chunk.length) state = "done";
    else if (c.converting > 0 || c.done > 0) state = "converting";
    out.push({ from: chunk[0].page_number, to: chunk[chunk.length - 1].page_number, state });
  }
  return out;
}
