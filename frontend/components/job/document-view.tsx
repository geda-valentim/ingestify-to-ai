"use client";

import { Download } from "lucide-react";
import { downloadText } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { MarkdownView } from "@/components/markdown-view";
import { CopyButton, Panel } from "./result-primitives";
import { FigureSummary, JobImages, hasFigureCounts, type FigureCounts } from "./job-images";
import type { ConversionAsset, ConversionAssetsSkipped, JobStatusResponse } from "@/types/api";

/**
 * A converted document: rendered Markdown by default, source on demand, and the
 * extracted images / page renders when the job asked for them (image_mode,
 * page_images).
 */
export function DocumentView({
  markdown,
  fileName,
  status,
  assets,
  assetsSkipped,
  figures,
}: {
  markdown: string;
  fileName: string;
  status?: JobStatusResponse;
  assets?: ConversionAsset[] | null;
  assetsSkipped?: ConversionAssetsSkipped | null;
  /** describe_images / ocr_images counts (null when the job asked for neither) */
  figures?: FigureCounts | null;
}) {
  const images = status && assets && assets.length > 0 ? assets : null;
  return (
    <Tabs defaultValue="preview">
      {/* Without extracted images there is no Images tab: show the counts here */}
      {!images && hasFigureCounts(figures) && (
        <div className="mb-2">
          <FigureSummary counts={figures} />
        </div>
      )}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <TabsList>
          <TabsTrigger value="preview">Preview</TabsTrigger>
          <TabsTrigger value="source">Markdown source</TabsTrigger>
          {images && <TabsTrigger value="images">Images ({images.length})</TabsTrigger>}
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
      {images && status && (
        <TabsContent value="images" className="mt-4">
          <Panel>
            <JobImages status={status} assets={images} skipped={assetsSkipped} figures={figures} fileName={fileName} />
          </Panel>
        </TabsContent>
      )}
    </Tabs>
  );
}
