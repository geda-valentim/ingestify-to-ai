"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download, Loader2, Search } from "lucide-react";
import { jobsApi } from "@/lib/api";
import { downloadText, formatDuration } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { MarkdownView } from "@/components/markdown-view";
import type { TranscriptFormat, TranscriptJson } from "@/types/api";
import { CopyButton, Panel, Spinner } from "./result-primitives";

type FileFormat = Exclude<TranscriptFormat, "markdown">;

const DOWNLOADS: { format: TranscriptFormat; label: string; mime: string }[] = [
  { format: "markdown", label: "Markdown", mime: "text/markdown" },
  { format: "vtt", label: "VTT", mime: "text/vtt" },
  { format: "srt", label: "SRT", mime: "application/x-subrip" },
  { format: "txt", label: "TXT", mime: "text/plain" },
  { format: "json", label: "JSON", mime: "application/json" },
];

const EXTENSIONS: Record<TranscriptFormat, string> = {
  markdown: "md",
  vtt: "vtt",
  srt: "srt",
  txt: "txt",
  json: "json",
};

/**
 * An audio/video transcription: timed segments, subtitles and Markdown, with
 * every format the API produced available for download.
 */
export function TranscriptView({
  jobId,
  markdown,
  fileName,
  token,
}: {
  jobId: string;
  markdown: string;
  fileName: string;
  token: string | null;
}) {
  const [query, setQuery] = useState("");
  const [subtitleFormat, setSubtitleFormat] = useState<"vtt" | "srt">("vtt");
  const [downloading, setDownloading] = useState<TranscriptFormat | null>(null);

  const transcript = useQuery({
    queryKey: ["transcript", jobId, "json", token],
    queryFn: async () =>
      JSON.parse(
        await jobsApi.getTranscriptFile(jobId, "json"),
      ) as TranscriptJson,
    enabled: !!token,
    staleTime: Infinity,
  });

  const subtitles = useQuery({
    queryKey: ["transcript", jobId, subtitleFormat, token],
    queryFn: () => jobsApi.getTranscriptFile(jobId, subtitleFormat),
    enabled: !!token,
    staleTime: Infinity,
  });

  const segments = transcript.data?.segments ?? [];
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q
      ? segments.filter((s) => s.text.toLowerCase().includes(q))
      : segments;
  }, [segments, query]);

  const download = async (format: TranscriptFormat, mime: string) => {
    setDownloading(format);
    try {
      const content =
        format === "markdown"
          ? markdown
          : await jobsApi.getTranscriptFile(jobId, format as FileFormat);
      downloadText(`${fileName}.${EXTENSIONS[format]}`, content, mime);
    } finally {
      setDownloading(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-muted-foreground mr-1">Download:</span>
        {DOWNLOADS.map(({ format, label, mime }) => (
          <Button
            key={format}
            variant="outline"
            size="sm"
            disabled={downloading !== null}
            onClick={() => download(format, mime)}
          >
            {downloading === format ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Download className="h-4 w-4 mr-2" />
            )}
            {label}
          </Button>
        ))}
      </div>

      <Tabs defaultValue="transcript">
        <TabsList className="w-fit">
          <TabsTrigger value="transcript">Transcript</TabsTrigger>
          <TabsTrigger value="subtitles">Subtitles</TabsTrigger>
          <TabsTrigger value="markdown">Markdown</TabsTrigger>
        </TabsList>

        <TabsContent value="transcript" className="mt-4">
          <Panel>
            {transcript.isLoading ? (
              <Spinner />
            ) : transcript.isError ? (
              <p className="py-12 text-center text-muted-foreground">
                Could not load the timed transcript.
              </p>
            ) : (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center gap-2">
                  <div className="relative flex-1 min-w-[12rem]">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      placeholder="Search the transcript"
                      className="pl-9"
                    />
                  </div>
                  <CopyButton
                    text={transcript.data?.text ?? ""}
                    label="Copy text"
                  />
                </div>
                {query && (
                  <p className="text-xs text-muted-foreground">
                    {filtered.length} of {segments.length} segments
                  </p>
                )}
                <ol className="space-y-1">
                  {filtered.map((segment) => (
                    <li
                      key={`${segment.start}-${segment.end}`}
                      className="flex gap-4 rounded-md px-2 py-2 hover:bg-background"
                    >
                      <span className="shrink-0 w-14 pt-0.5 font-mono text-xs text-muted-foreground tabular-nums">
                        {formatDuration(segment.start)}
                      </span>
                      <div className="min-w-0 flex-1 text-sm leading-relaxed">
                        <p>{segment.text}</p>
                        {!!segment.words?.length && (
                          <details className="mt-2">
                            <summary className="cursor-pointer text-xs text-muted-foreground">
                              Timestamps de palavras
                            </summary>
                            <div className="mt-2 flex flex-wrap gap-2">
                              {segment.words.map((word, index) => (
                                <span
                                  key={index}
                                  className="rounded border px-2 py-1 text-xs"
                                  title={
                                    word.probability == null
                                      ? undefined
                                      : `Probabilidade: ${(word.probability * 100).toFixed(1)}%`
                                  }
                                >
                                  <span className="font-mono text-muted-foreground">
                                    {word.start.toFixed(2)}–
                                    {word.end.toFixed(2)}s
                                  </span>{" "}
                                  {word.word}
                                </span>
                              ))}
                            </div>
                          </details>
                        )}
                      </div>
                    </li>
                  ))}
                </ol>
                {transcript.data?.operation === "inspect" && (
                  <pre className="overflow-auto whitespace-pre-wrap rounded border p-4 text-sm">
                    {JSON.stringify(transcript.data.media_info, null, 2)}
                  </pre>
                )}
                {transcript.data?.operation === "detect_language" && (
                  <div className="space-y-2 rounded border p-4">
                    <p>{transcript.data.text}</p>
                    {transcript.data.language_probability != null && (
                      <p className="text-sm text-muted-foreground">
                        Probabilidade:{" "}
                        {(transcript.data.language_probability * 100).toFixed(
                          1,
                        )}
                        %
                      </p>
                    )}
                  </div>
                )}
                {segments.length === 0 &&
                  !["inspect", "detect_language"].includes(
                    transcript.data?.operation ?? "",
                  ) && (
                    <p className="py-12 text-center text-muted-foreground">
                      No speech was detected.
                    </p>
                  )}
              </div>
            )}
          </Panel>
        </TabsContent>

        <TabsContent value="subtitles" className="mt-4 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            {(["vtt", "srt"] as const).map((f) => (
              <Button
                key={f}
                size="sm"
                variant={subtitleFormat === f ? "secondary" : "ghost"}
                aria-pressed={subtitleFormat === f}
                onClick={() => setSubtitleFormat(f)}
              >
                {f.toUpperCase()}
              </Button>
            ))}
            {subtitles.data !== undefined && (
              <CopyButton text={subtitles.data} />
            )}
          </div>
          <div>
            <Panel>
              {subtitles.isLoading ? (
                <Spinner />
              ) : subtitles.isError ? (
                <p className="py-12 text-center text-muted-foreground">
                  Could not load the subtitles.
                </p>
              ) : (
                <pre className="text-sm whitespace-pre-wrap font-mono">
                  {subtitles.data}
                </pre>
              )}
            </Panel>
          </div>
        </TabsContent>

        <TabsContent value="markdown" className="mt-4">
          <Panel>
            <MarkdownView content={markdown} className="max-w-4xl" />
          </Panel>
        </TabsContent>
      </Tabs>
    </div>
  );
}
