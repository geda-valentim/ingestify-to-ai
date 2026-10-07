"use client";

import { useEffect, useState } from "react";
import { Download } from "lucide-react";
import { jobsApi } from "@/lib/api";
import { downloadText } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { MarkdownView } from "@/components/markdown-view";
import type { DocumentFormat } from "@/types/api";
import { CopyButton, Panel } from "./result-primitives";

/**
 * A converted document: rendered Markdown by default, source on demand.
 */
export function DocumentView({
  markdown,
  fileName,
  exports,
  defaultFormat = "markdown",
  assets = [],
}: {
  markdown: string;
  fileName: string;
  exports?: Partial<Record<DocumentFormat, string>>;
  defaultFormat?: string;
  assets?: { url: string; name: string }[];
}) {
  const [format, setFormat] = useState(defaultFormat);
  const [images, setImages] = useState<
    Record<string, { objectUrl: string; embeddedUrl: string }>
  >({});
  const [imageError, setImageError] = useState(false);
  const manifest = JSON.stringify(assets);
  useEffect(() => {
    setFormat(defaultFormat);
  }, [defaultFormat]);
  useEffect(() => {
    let cancelled = false;
    const urls: string[] = [];
    setImages({});
    setImageError(false);
    Promise.all(
      (JSON.parse(manifest) as { url: string }[]).map(async (asset) => {
        const blob = await jobsApi.getDocumentAsset(asset.url);
        // Sandboxed HTML has an opaque origin and cannot load our blob URLs.
        // Embed authenticated image bytes without granting scripts/origin access.
        const embeddedUrl = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(String(reader.result));
          reader.onerror = () => reject(reader.error);
          reader.readAsDataURL(blob);
        });
        if (cancelled) return null;
        const objectUrl = URL.createObjectURL(blob);
        urls.push(objectUrl);
        return [asset.url, { objectUrl, embeddedUrl }];
      }),
    )
      .then((entries) => {
        if (!cancelled)
          setImages(
            Object.fromEntries(entries.filter((item) => item !== null)),
          );
      })
      .catch(() => {
        if (!cancelled) setImageError(true);
      });
    return () => {
      cancelled = true;
      urls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [manifest]);
  const formats = exports ? Object.keys(exports) : ["markdown"];
  const selected = formats.includes(format) ? format : formats[0];
  const source = exports?.[selected as DocumentFormat] ?? markdown;
  const rendered = Object.entries(images).reduce(
    (text, [path, image]) =>
      text.replaceAll(
        path,
        selected === "html" ? image.embeddedUrl : image.objectUrl,
      ),
    source,
  );
  const mime =
    selected === "html"
      ? "text/html"
      : selected === "json"
        ? "application/json"
        : selected === "vtt"
          ? "text/vtt"
          : "text/plain";
  const extension = selected === "markdown" ? "md" : selected;
  return (
    <Tabs defaultValue="preview">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <TabsList>
          <TabsTrigger value="preview">Preview</TabsTrigger>
          <TabsTrigger value="source">
            {selected === "markdown" ? "Markdown source" : "Source"}
          </TabsTrigger>
        </TabsList>
        <div className="flex flex-wrap gap-2">
          {exports && (
            <select
              aria-label="Formato do documento"
              value={selected}
              onChange={(event) => setFormat(event.target.value)}
              className="h-9 rounded border bg-background px-3 text-sm"
            >
              {formats.map((item) => (
                <option key={item} value={item}>
                  {item.toUpperCase()}
                </option>
              ))}
            </select>
          )}
          <CopyButton text={source} />
          <Button
            size="sm"
            onClick={() =>
              downloadText(`${fileName}.${extension}`, source, mime)
            }
          >
            <Download className="h-4 w-4 mr-2" />
            Download .{extension}
          </Button>
        </div>
      </div>
      {imageError && (
        <p role="alert" className="mt-3 text-sm text-destructive">
          Não foi possível carregar uma imagem do documento.
        </p>
      )}
      <TabsContent value="preview" className="mt-4">
        <Panel>
          {selected === "html" ? (
            <iframe
              title="HTML do documento"
              sandbox=""
              srcDoc={rendered}
              className="min-h-[600px] w-full rounded border bg-white"
            />
          ) : selected === "markdown" ? (
            source.trim() ? (
              <MarkdownView
                content={rendered}
                allowedImageUrls={Object.values(images).map(
                  (image) => image.objectUrl,
                )}
                className="max-w-4xl"
              />
            ) : (
              <p className="py-12 text-center text-muted-foreground">
                The conversion produced no text.
              </p>
            )
          ) : (
            <pre className="whitespace-pre-wrap break-words font-mono text-sm">
              {source}
            </pre>
          )}
        </Panel>
      </TabsContent>
      <TabsContent value="source" className="mt-4">
        <Panel>
          <pre className="text-sm whitespace-pre-wrap font-mono">{source}</pre>
        </Panel>
      </TabsContent>
    </Tabs>
  );
}
