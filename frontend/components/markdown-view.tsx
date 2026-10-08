"use client";

import type { ImgHTMLAttributes } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { parseAssetPath, useAssetUrl } from "@/hooks/use-asset-url";
import { cn } from "@/lib/utils";

/**
 * An image of the converted document. Asset paths (`/jobs/{job_id}/assets/{name}`)
 * are API routes that need the user's credentials, so they are fetched with them
 * and shown from a blob URL (useAssetUrl); a missing or deleted asset shows a
 * placeholder. Any other src is left to the browser as before.
 */
function MarkdownImage({ src, alt, ...rest }: ImgHTMLAttributes<HTMLImageElement>) {
  const asset = parseAssetPath(src);
  const loaded = useAssetUrl(asset?.jobId ?? null, asset?.name ?? null, !!asset);

  if (!asset) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={src} alt={alt ?? ""} {...rest} />;
  }
  if (loaded.state === "unavailable" || loaded.state === "error") {
    return (
      <span className="inline-block rounded border border-dashed px-3 py-2 text-xs text-muted-foreground">
        Image unavailable{alt ? `: ${alt}` : ""}
      </span>
    );
  }
  if (loaded.state === "loading") {
    return <span className="inline-block h-24 w-32 animate-pulse rounded bg-muted" aria-label={alt ?? "image"} />;
  }
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={loaded.url} alt={alt ?? ""} {...rest} />;
}

/**
 * Rendered Markdown (GFM: tables, task lists, strikethrough).
 *
 * The project has no @tailwindcss/typography, so each element is styled here.
 * Raw HTML in the source is not rendered: converted documents are untrusted.
 */
export function MarkdownView({ content, className }: { content: string; className?: string }) {
  return (
    <div
      className={cn(
        "text-sm leading-relaxed break-words",
        "[&_h1]:text-2xl [&_h1]:font-bold [&_h1]:mt-6 [&_h1]:mb-3",
        "[&_h2]:text-xl [&_h2]:font-semibold [&_h2]:mt-6 [&_h2]:mb-3",
        "[&_h3]:text-lg [&_h3]:font-semibold [&_h3]:mt-5 [&_h3]:mb-2",
        "[&_h4]:font-semibold [&_h4]:mt-4 [&_h4]:mb-2",
        "[&>*:first-child]:mt-0",
        "[&_p]:my-3",
        "[&_ul]:my-3 [&_ul]:list-disc [&_ul]:pl-6 [&_ol]:my-3 [&_ol]:list-decimal [&_ol]:pl-6 [&_li]:my-1",
        "[&_a]:text-primary [&_a]:underline [&_a]:underline-offset-4",
        "[&_blockquote]:border-l-4 [&_blockquote]:pl-4 [&_blockquote]:text-muted-foreground [&_blockquote]:my-3",
        "[&_hr]:my-6 [&_hr]:border-border",
        "[&_code]:bg-muted [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:rounded [&_code]:text-[0.85em]",
        "[&_pre]:bg-muted [&_pre]:p-4 [&_pre]:rounded-lg [&_pre]:overflow-x-auto [&_pre]:my-3 [&_pre_code]:p-0 [&_pre_code]:bg-transparent",
        "[&_table]:block [&_table]:max-w-full [&_table]:overflow-x-auto [&_table]:my-4 [&_table]:border-collapse [&_table]:text-sm",
        "[&_th]:border [&_th]:px-3 [&_th]:py-2 [&_th]:bg-muted/50 [&_th]:text-left [&_th]:font-medium",
        "[&_td]:border [&_td]:px-3 [&_td]:py-2 [&_td]:align-top",
        "[&_img]:max-w-full [&_img]:rounded",
        className
      )}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ img: ({ node: _node, ...props }) => <MarkdownImage {...props} /> }}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
