"use client";

import { Download } from "lucide-react";
import { downloadText } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { MarkdownView } from "@/components/markdown-view";
import { CopyButton, Panel } from "./result-primitives";

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
