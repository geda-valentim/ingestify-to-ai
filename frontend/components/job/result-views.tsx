"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Check, Copy, Download, Loader2, Search } from "lucide-react";
import { jobsApi } from "@/lib/api";
import { downloadText, formatDuration } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { MarkdownView } from "@/components/markdown-view";
import type { TranscriptFormat, TranscriptJson } from "@/types/api";

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

function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <Button
      variant="outline"
      size="sm"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
        } catch {
          // Clipboard needs a secure origin (https or localhost); over plain
          // http on the LAN it is unavailable and the text stays selectable.
        }
      }}
    >
      {copied ? <Check className="h-4 w-4 mr-2" /> : <Copy className="h-4 w-4 mr-2" />}
      {copied ? "Copied" : label}
    </Button>
  );
}

function Panel({ children }: { children: React.ReactNode }) {
  return <div className="border rounded-lg bg-muted/30 p-4 md:p-6">{children}</div>;
}

function Spinner() {
  return (
    <div className="py-12 flex items-center justify-center">
      <Loader2 className="h-8 w-8 animate-spin text-primary" />
    </div>
  );
}

/**
 * A converted document: rendered Markdown by default, source on demand.
 */
export function DocumentView({ markdown, fileName }: { markdown: string; fileName: string }) {
  return (
    <Tabs defaultValue="preview">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <TabsList>
          <TabsTrigger value="preview">Preview</TabsTrigger>
          <TabsTrigger value="source">Markdown source</TabsTrigger>
        </TabsList>
        <div className="flex gap-2">
          <CopyButton text={markdown} />
          <Button size="sm" onClick={() => downloadText(`${fileName}.md`, markdown, "text/markdown")}>
            <Download className="h-4 w-4 mr-2" />
            Download .md
          </Button>
        </div>
      </div>
      <TabsContent value="preview" className="mt-4">
        <Panel>
          {markdown.trim() ? (
            <MarkdownView content={markdown} className="max-w-4xl" />
          ) : (
            <p className="py-12 text-center text-muted-foreground">The conversion produced no text.</p>
          )}
        </Panel>
      </TabsContent>
      <TabsContent value="source" className="mt-4">
        <Panel>
          <pre className="text-sm whitespace-pre-wrap font-mono">{markdown}</pre>
        </Panel>
      </TabsContent>
    </Tabs>
  );
}

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
    queryFn: async () => JSON.parse(await jobsApi.getTranscriptFile(jobId, "json")) as TranscriptJson,
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
    return q ? segments.filter((s) => s.text.toLowerCase().includes(q)) : segments;
  }, [segments, query]);

  const download = async (format: TranscriptFormat, mime: string) => {
    setDownloading(format);
    try {
      const content = format === "markdown" ? markdown : await jobsApi.getTranscriptFile(jobId, format as FileFormat);
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

      {transcript.data?.diarization?.status === "completed" && (
        <p className="text-sm text-muted-foreground">{transcript.data.diarization.speaker_count} falantes identificados nesta gravação</p>
      )}
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
              <p className="py-12 text-center text-muted-foreground">Could not load the timed transcript.</p>
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
                  <CopyButton text={transcript.data?.text ?? ""} label="Copy text" />
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
                      <span className="text-sm leading-relaxed">
                        {transcript.data?.schema_version === 2 && transcript.data.diarization?.status === "completed" && (
                          <span className={`mr-2 inline-flex rounded px-2 py-0.5 text-xs font-medium ${segment.speaker_id && Number(segment.speaker_id.slice(-2)) % 2 ? "bg-violet-100 text-violet-900" : "bg-blue-100 text-blue-900"}`}>
                            {transcript.data.speakers?.find(s => s.id === segment.speaker_id)?.label ?? "Falante não identificado"}
                          </span>
                        )}
                        {segment.text}
                      </span>
                    </li>
                  ))}
                </ol>
                {segments.length === 0 && (
                  <p className="py-12 text-center text-muted-foreground">No speech was detected.</p>
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
            {subtitles.data !== undefined && <CopyButton text={subtitles.data} />}
          </div>
          <div>
            <Panel>
              {subtitles.isLoading ? (
                <Spinner />
              ) : subtitles.isError ? (
                <p className="py-12 text-center text-muted-foreground">Could not load the subtitles.</p>
              ) : (
                <pre className="text-sm whitespace-pre-wrap font-mono">{subtitles.data}</pre>
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
