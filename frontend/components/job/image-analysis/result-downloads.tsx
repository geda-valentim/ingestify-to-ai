"use client";

import { useState } from "react";
import { Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { jobsApi } from "@/lib/api";
import { downloadText, formatApiError } from "@/lib/utils";

const FORMATS = {
  markdown: { label: "Download as Markdown", extension: "md", type: "text/markdown" },
  json: { label: "Download JSON", extension: "json", type: "application/json" },
} as const;

/**
 * The image job's result exactly as the API serves it: GET /jobs/{id}/result
 * with ?format=markdown (rendered by the server) or ?format=json.
 */
export function ResultDownloads({ jobId, fileName }: { jobId: string; fileName: string }) {
  const [pending, setPending] = useState<keyof typeof FORMATS | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function download(format: keyof typeof FORMATS) {
    setPending(format);
    setError(null);
    try {
      const content = await jobsApi.getImageResultFile(jobId, format);
      const { extension, type } = FORMATS[format];
      downloadText(`${fileName}.${extension}`, content, type);
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-xs text-muted-foreground">API result</span>
      {(Object.keys(FORMATS) as (keyof typeof FORMATS)[]).map((format) => (
        <Button
          key={format}
          size="sm"
          variant="outline"
          disabled={pending !== null}
          onClick={() => download(format)}
        >
          <Download className="mr-1.5 h-3.5 w-3.5" />
          {FORMATS[format].label}
        </Button>
      ))}
      {error && (
        <p role="alert" className="w-full text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}
