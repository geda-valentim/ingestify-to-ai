import { formatDuration } from "@/lib/utils";
import type { JobStatusResponse } from "@/types/api";

/** "12:30 of 57:27 transcribed" while a transcription runs, else null. */
export function transcriptionProgress(status?: JobStatusResponse | null): string | null {
  if (!status || status.status !== "processing" || !status.media_duration) return null;
  const done = Math.min(status.transcribed_seconds ?? 0, status.media_duration);
  return `${formatDuration(done)} of ${formatDuration(status.media_duration)} transcribed`;
}

/** Where a routed job runs (spec 0003): the class only, never the engine's name or cost. */
export function engineKindLabel(status?: JobStatusResponse | null): string | null {
  if (!status?.engine) return null;
  return status.engine.kind === "cloud" ? "Cloud GPU" : "Local server";
}

/** Why a routed job still waits; null for jobs without routing. */
export function queueReasonText(status?: JobStatusResponse | null): string | null {
  if (!status?.queue_reason || status.status === "completed" || status.status === "failed" || status.status === "cancelled") {
    return null;
  }
  if (status.queue_reason === "in_queue") {
    return "Waiting for a free engine. It starts automatically as soon as one has room.";
  }
  const where = engineKindLabel(status);
  return where === "Cloud GPU"
    ? "Starting on a cloud GPU… this can take a little while the first time."
    : `Starting${where ? ` on the ${where.toLowerCase()}` : ""}…`;
}
