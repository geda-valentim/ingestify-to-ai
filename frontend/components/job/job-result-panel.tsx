"use client";

import { AlertCircle, Loader2, RotateCw, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DocumentView, ImageView, TranscriptView } from "./result-views";
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
  isResultError,
  isFetchingResult,
  retryResult,
  isTranscript,
  hasPages,
  fileName,
  token,
}: {
  status: JobStatusResponse;
  result?: JobResultResponse;
  isResultError: boolean;
  isFetchingResult: boolean;
  retryResult: () => void;
  isTranscript: boolean;
  hasPages: boolean;
  fileName: string;
  token: string | null;
}) {
  const { segments: liveSegments, preloaded: livePreloaded } =
    useLiveTranscript(status.job_id, status.status === "processing");
  if (status.status === "failed" && !status.image_analysis) {
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
  if (
    status.status === "processing" &&
    (status.media_duration || liveSegments.length > 0)
  ) {
    return (
      <LiveTranscriptView
        status={status}
        segments={liveSegments}
        preloaded={livePreloaded}
      />
    );
  }

  if (
    status.status !== "completed" &&
    status.status !== "partial" &&
    !(status.image_analysis && ["failed", "cancelled"].includes(status.status))
  ) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
        <Loader2 className="h-12 w-12 text-primary animate-spin mb-4" />
        <h3 className="text-lg font-semibold mb-1">
          {status.status === "processing"
            ? "Processing…"
            : "Waiting in the queue…"}
        </h3>
        <p className="text-sm text-muted-foreground">
          {status.progress}% — the result shows up here as soon as it is ready.
        </p>
        {transcriptionProgress(status) && (
          <p className="text-sm text-muted-foreground mt-1">
            {transcriptionProgress(status)}
          </p>
        )}
        {queueReasonText(status) && (
          <p className="text-sm text-muted-foreground mt-1">
            {queueReasonText(status)}
          </p>
        )}
      </div>
    );
  }

  if (!result) {
    if (isResultError) {
      return (
        <div
          className="flex-1 flex flex-col items-center justify-center gap-3 p-8 text-center"
          role="alert"
        >
          <AlertCircle className="h-12 w-12 text-destructive" />
          <h3 className="text-lg font-semibold">Could not load the result</h3>
          <p className="text-sm text-muted-foreground">
            Try again to retrieve the completed job&apos;s result.
          </p>
          <Button
            variant="outline"
            onClick={retryResult}
            disabled={isFetchingResult}
          >
            {isFetchingResult ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <RotateCw className="h-4 w-4 mr-2" />
            )}
            Try again
          </Button>
        </div>
      );
    }
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-4">
      {result.result.image?.operation !== "full_analysis" && (
        <div>
          <h2 className="text-xl font-semibold">
            {result.result.image
              ? result.result.image.operation === "face_analysis"
                ? "Rostos e expressões"
                : result.result.image.operation === "analyze"
                ? "Análise da imagem"
                : result.result.image.operation === "ocr"
                  ? "Texto da imagem (OCR)"
                  : "Descrição da imagem"
              : isTranscript
                ? "Transcription"
                : "Converted document"}
          </h2>
          {hasPages && (
            <p className="text-sm text-muted-foreground">
              All pages merged. Select a page in the sidebar to see its PDF next
              to its text.
            </p>
          )}
        </div>
      )}
      {result.result.image ? (
        <ImageView image={result.result.image} fileName={fileName} />
      ) : isTranscript ? (
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
          exports={result.result.exports}
          defaultFormat={
            (result.result.metadata as { output_format?: string }).output_format
          }
          assets={result.result.assets}
        />
      )}
    </div>
  );
}
