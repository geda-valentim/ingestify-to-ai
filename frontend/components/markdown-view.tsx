"use client";

import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";

/**
 * Rendered Markdown (GFM: tables, task lists, strikethrough).
 *
 * The project has no @tailwindcss/typography, so each element is styled here.
 * Raw HTML in the source is not rendered: converted documents are untrusted.
 */
export function MarkdownView({ content, className, allowedImageUrls = [] }: {
  content: string; className?: string; allowedImageUrls?: string[];
}) {
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
      <ReactMarkdown remarkPlugins={[remarkGfm]} urlTransform={(value, key, node) => {
        if (key === "src" && node.tagName === "img" && (
          allowedImageUrls.includes(value) || /^data:image\/(?:png|jpeg|gif|webp);base64,[a-zA-Z0-9+/]+=*$/.test(value)
        )) return value;
        return defaultUrlTransform(value);
      }}>{content}</ReactMarkdown>
    </div>
  );
}
