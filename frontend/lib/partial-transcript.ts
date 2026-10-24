import type { PartialTranscriptResponse, TranscriptSegment } from "@/types/api";

export interface PartialState {
  segments: TranscriptSegment[];
  /** The `since` for the next request: how many segments were received so far */
  cursor: number;
}

export const EMPTY_PARTIAL: PartialState = { segments: [], cursor: 0 };

/**
 * Applies one response of GET /jobs/{id}/transcript/partial to what was already
 * received. The endpoint returns the segments in [`since`, `next`), so a response
 * is only applied when it was requested at the current cursor (`requestedSince`)
 * and carries exactly `next - since` segments. Anything else (a stale or
 * out-of-order response, a truncated one) returns `current` untouched, so no
 * segment is appended twice or out of place. `next` below the cursor means the
 * transcription restarted (e.g. GPU failed, retrying on CPU): start over.
 */
export function mergePartial(
  current: PartialState,
  requestedSince: number,
  response: Pick<PartialTranscriptResponse, "segments" | "next">
): { state: PartialState; reset: boolean } {
  if (requestedSince !== current.cursor) return { state: current, reset: false };
  if (response.next < current.cursor) return { state: EMPTY_PARTIAL, reset: true };
  if (response.segments.length !== response.next - current.cursor) return { state: current, reset: false };
  if (response.segments.length === 0) return { state: current, reset: false };
  return {
    state: { segments: [...current.segments, ...response.segments], cursor: response.next },
    reset: false,
  };
}
