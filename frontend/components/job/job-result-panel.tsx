"use client";

import { Loader2, XCircle } from "lucide-react";
import { DocumentView, TranscriptView } from "./result-views";
import { LiveTranscriptView, useLiveTranscript } from "./live-transcript";
import { queueReasonText, transcriptionProgress } from "./job-progress";
import type { JobResultResponse, JobStatusResponse } from "@/types/api";

/**
 * What the main panel shows when no PDF page is selected: progress while the
 * job runs, the error if it failed, otherwise the result in the view that fits
 * it - a transcript for audio/video, rendered Markdown for documents.
 */
export function JobResultPanel({
  status,
  result,
  isTranscript,
  hasPages,
  fileName,
  token,
}: {
  status: JobStatusResponse;
  result?: JobResultResponse;
  isTranscript: boolean;
  hasPages: boolean;
  fileName: string;
  token: string | null;
}) {
  const { segments: liveSegments, preloaded: livePreloaded } = useLiveTranscript(
    status.job_id,
    status.status === "processing"
  );
  if (status.status === "failed") {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
        <XCircle className="h-16 w-16 text-destructive mb-4" />
        <h3 className="text-lg font-semibold mb-2">Processing failed</h3>
        <p className="text-sm text-muted-foreground max-w-md break-words">
          {status.error || "An unknown error occurred"}
        </p>
      </div>
    );
  }

  // faster-whisper reports media time and streams its text: show the captions as they come
  if (status.status === "processing" && (status.media_duration || liveSegments.length > 0)) {
    return <LiveTranscriptView status={status} segments={liveSegments} preloaded={livePreloaded} />;
  }

  // A split PDF whose pages did not all convert: there is no merged Markdown (nor
  // image list) until a page retry completes it, but each converted page has its own
  if (status.status === "partial") {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
        <XCircle className="h-12 w-12 text-destructive mb-4" />
        <h3 className="text-lg font-semibold mb-1">Some pages could not be converted</h3>
        <p className="text-sm text-muted-foreground max-w-md">
          The merged document is created once every page converts. Open a page in the sidebar to read it, or
          retry the failed ones.
        </p>
      </div>
    );
  }

  if (status.status !== "completed") {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
        <Loader2 className="h-12 w-12 text-primary animate-spin mb-4" />
        <h3 className="text-lg font-semibold mb-1">
          {status.status === "processing" ? "Processing…" : "Waiting in the queue…"}
        </h3>
        <p className="text-sm text-muted-foreground">
          {status.progress}% — the result shows up here as soon as it is ready.
        </p>
        {transcriptionProgress(status) && (
          <p className="text-sm text-muted-foreground mt-1">{transcriptionProgress(status)}</p>
        )}
        {queueReasonText(status) && (
          <p className="text-sm text-muted-foreground mt-1">{queueReasonText(status)}</p>
        )}
      </div>
    );
  }

  if (!result) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-4">
      <div>
        <h2 className="text-xl font-semibold">{isTranscript ? "Transcription" : "Converted document"}</h2>
        {hasPages && (
          <p className="text-sm text-muted-foreground">
            All pages merged. Select a page in the sidebar to see its PDF next to its text.
          </p>
        )}
      </div>
      {isTranscript ? (
        <TranscriptView
          jobId={status.job_id}
          markdown={result.result.markdown}
          fileName={fileName}
          token={token}
        />
      ) : (
        <DocumentView
          markdown={result.result.markdown}
          fileName={fileName}
          status={status}
          assets={result.result.assets}
          assetsSkipped={result.result.assets_skipped}
        />
      )}
    </div>
  );
}
