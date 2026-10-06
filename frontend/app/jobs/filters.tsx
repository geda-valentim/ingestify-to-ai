"use client";

import { useId, useState } from "react";
import { Check, ChevronDown, Loader2, Search, SlidersHorizontal, Tag, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { JobKind, JobStatus } from "@/types/api";

export const STATUS_TABS: { value: JobStatus | "all"; label: string }[] = [
  { value: "all", label: "All jobs" },
  { value: "processing", label: "Processing" },
  { value: "queued", label: "Queued" },
  { value: "completed", label: "Completed" },
  { value: "failed", label: "Failed" },
  { value: "cancelled", label: "Cancelled" },
];
export const KINDS: { value: JobKind | "all"; label: string }[] = [
  { value: "all", label: "All types" },
  { value: "document", label: "Documents" },
  { value: "transcription", label: "Transcriptions" },
  { value: "image", label: "Images" },
];

export function JobsFilters({ draft, onDraft, onSearch, contentMode, onMode, status, kind, tags, counts,
  knownTags, tagsLoading, tagsError, retryTags, onStatus, onKind, onTag, onClear, hasFilters,
}: {
  draft: string; onDraft: (value: string) => void; onSearch: () => void;
  contentMode: boolean; onMode: (content: boolean) => void;
  status: JobStatus | "all"; kind: JobKind | "all"; tags: string[];
  counts?: Record<JobStatus | "all", number>;
  knownTags: { tag: string; count: number }[]; tagsLoading: boolean; tagsError: boolean; retryTags: () => void;
  onStatus: (value: JobStatus | "all") => void; onKind: (value: JobKind | "all") => void;
  onTag: (tag: string) => void; onClear: () => void; hasFilters: boolean;
}) {
  const [tagsOpen, setTagsOpen] = useState(false);
  const [tagSearch, setTagSearch] = useState("");
  const id = useId();
  // Keep selected tags visible even if their counts have changed or loading failed.
  const choices = [...new Set([...tags, ...knownTags.map(item => item.tag)])]
    .filter(tag => tag.toLocaleLowerCase().includes(tagSearch.trim().toLocaleLowerCase()));
  const knownCounts = new Map(knownTags.map(item => [item.tag, item.count]));
  return <section aria-label="Job filters" className="rounded-xl border bg-background">
    <div className="space-y-4 p-4 sm:p-5">
      <div className="flex flex-col gap-3 xl:flex-row">
        <form role="search" className="relative min-w-0 flex-1" onSubmit={e => { e.preventDefault(); onSearch(); }}>
          <Search aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input aria-label={contentMode ? "Search converted content" : "Search jobs by name"} value={draft} onChange={e => onDraft(e.target.value)} placeholder={contentMode ? "Search converted content…" : "Search jobs by name or filename…"} className="h-11 pl-9 pr-11" />
          {draft && <button type="button" aria-label="Clear search" onClick={() => onDraft("")} className="absolute inset-y-0 right-0 grid w-11 place-items-center rounded-md text-muted-foreground hover:text-foreground"><X className="h-4 w-4" /></button>}
        </form>
        <div role="group" aria-label="Search in" className="flex w-fit shrink-0 rounded-lg bg-muted p-1">
          {[{ content: false, label: "Jobs" }, { content: true, label: "Content" }].map(item => <button key={item.label} type="button" aria-pressed={contentMode === item.content} onClick={() => onMode(item.content)} className={cn("min-h-9 rounded-md px-4 text-sm transition-colors", contentMode === item.content ? "bg-background font-medium shadow-sm" : "text-muted-foreground hover:text-foreground")}>{item.label}</button>)}
        </div>
      </div>
      {contentMode ? <p className="text-xs leading-relaxed text-muted-foreground">Search indexed content across all your projects. Job status, file type and tag filters apply only in Jobs view.</p> : <>
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex min-h-10 items-center gap-2 rounded-md border px-3 text-sm">
            <SlidersHorizontal aria-hidden="true" className="h-4 w-4 shrink-0 text-muted-foreground" />
            <span className="sr-only">File type</span>
            <select aria-label="File type" value={kind} onChange={e => onKind(e.target.value as JobKind | "all")} className="min-w-0 bg-transparent py-2 pr-1 outline-offset-2">{KINDS.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}</select>
          </label>
          <Button type="button" variant="outline" aria-expanded={tagsOpen} aria-controls={`${id}-tags`} onClick={() => setTagsOpen(!tagsOpen)} className="gap-2"><Tag className="h-4 w-4" aria-hidden="true" />Tags{tags.length > 0 && <span className="rounded bg-secondary px-1.5 text-xs">{tags.length}</span>}<ChevronDown className={cn("h-3.5 w-3.5 transition-transform", tagsOpen && "rotate-180")} aria-hidden="true" /></Button>
          {hasFilters && <button type="button" onClick={onClear} className="ml-auto min-h-10 px-2 text-xs text-muted-foreground underline underline-offset-4 hover:text-foreground">Reset filters</button>}
        </div>
        {tagsOpen && <div id={`${id}-tags`} className="rounded-lg border bg-muted/20 p-3">
          <div className="mb-3 flex items-center justify-between gap-3"><div><h2 className="text-sm font-medium">Filter by tags</h2><p className="mt-1 text-xs text-muted-foreground">Match every selected tag. Counts cover all your jobs.</p></div><button type="button" onClick={() => setTagsOpen(false)} aria-label="Close tag filters" className="grid h-10 w-10 shrink-0 place-items-center rounded-md hover:bg-muted"><X className="h-4 w-4" /></button></div>
          <Input aria-label="Find a tag" placeholder="Find a tag…" value={tagSearch} onChange={e => setTagSearch(e.target.value)} className="mb-3 bg-background" />
          {tagsLoading && <p role="status" className="p-2 text-xs text-muted-foreground"><Loader2 className="mr-2 inline h-3 w-3 animate-spin" />Loading tags…</p>}
          {tagsError && <p role="alert" className="p-2 text-xs text-destructive">Could not load tags. <button type="button" onClick={retryTags} className="underline">Retry tags</button></p>}
          <div role="group" aria-label="Available tags" className="grid max-h-56 gap-1 overflow-y-auto sm:grid-cols-2 xl:grid-cols-3">
            {choices.map(tag => <button type="button" key={tag} aria-pressed={tags.includes(tag)} onClick={() => onTag(tag)} className={cn("flex min-h-10 min-w-0 items-center gap-2 rounded-md px-2 text-left text-xs hover:bg-muted", tags.includes(tag) && "bg-secondary font-medium")}>
              <span className={cn("grid h-4 w-4 shrink-0 place-items-center rounded border", tags.includes(tag) && "border-primary bg-primary text-primary-foreground")}>{tags.includes(tag) && <Check className="h-3 w-3" />}</span><span className="min-w-0 flex-1 truncate" title={tag}>{tag}</span><span className="shrink-0 tabular-nums text-muted-foreground">{knownCounts.get(tag) ?? "—"}</span>
            </button>)}
          </div>
          {!tagsLoading && !tagsError && choices.length === 0 && <p className="p-2 text-xs text-muted-foreground">{tagSearch ? "No tags match your search." : "No tags yet. Add them from a job’s actions menu."}</p>}
        </div>}
        {(tags.length > 0 || kind !== "all") && <div role="group" aria-label="Applied filters" className="flex flex-wrap items-center gap-2 border-t pt-3">
          <span className="text-xs text-muted-foreground">Filtered by</span>
          {kind !== "all" && <button type="button" onClick={() => onKind("all")} aria-label="Remove file type filter" className="inline-flex min-h-8 items-center gap-2 rounded-md border px-2 text-xs">{KINDS.find(item => item.value === kind)?.label}<X className="h-3 w-3" /></button>}
          {tags.map(tag => <button key={tag} type="button" aria-label={`Remove tag filter ${tag}`} title={tag} onClick={() => onTag(tag)} className="inline-flex min-h-8 max-w-full items-center gap-2 rounded-md border bg-muted/40 px-2 text-xs"><Tag className="h-3 w-3 shrink-0 text-muted-foreground" /><span className="max-w-52 truncate">{tag}</span><X className="h-3 w-3 shrink-0" /></button>)}
        </div>}
      </>}
    </div>
    {!contentMode && <div role="group" aria-label="Job status" className="flex gap-1 overflow-x-auto border-t px-3 pt-1">
      {STATUS_TABS.map(item => <button key={item.value} type="button" aria-pressed={status === item.value} onClick={() => onStatus(item.value)} className={cn("flex min-h-12 shrink-0 items-center gap-2 whitespace-nowrap border-b-2 px-3 text-xs transition-colors", status === item.value ? "border-foreground font-semibold" : "border-transparent text-muted-foreground hover:text-foreground")}>
        {item.label}{counts?.[item.value] !== undefined && <span className={cn("rounded px-1.5 py-0.5 text-[11px] tabular-nums", status === item.value ? "bg-secondary text-foreground" : "bg-muted/50")}>{counts[item.value]}</span>}
      </button>)}
    </div>}
  </section>;
}
