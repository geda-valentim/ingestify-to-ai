"use client";

import Link from "next/link";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { ArrowUpRight, FileText, FolderInput, Folder, Image, Loader2, Mic, MoreHorizontal, Tag, Trash2 } from "lucide-react";
import { format, formatDistanceToNow } from "date-fns";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { cn, formatBytes, parseApiDate } from "@/lib/utils";
import type { LocationFilter } from "@/components/projects/project-sidebar";
import type { JobListItem } from "@/types/api";

const icons = { document: FileText, transcription: Mic, image: Image };
const statusStyle: Record<string, string> = {
  completed: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
  partial: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
  cancelled: "bg-muted text-muted-foreground",
  failed: "bg-red-500/10 text-red-700 dark:text-red-400",
  processing: "bg-blue-500/10 text-blue-700 dark:text-blue-400",
  queued: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
};
const menuItem = "flex min-h-10 cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm outline-none data-[highlighted]:bg-accent";
const menuPanel = "z-50 min-w-48 max-w-[calc(100vw-2rem)] rounded-xl border bg-popover p-1 text-popover-foreground shadow-lg";

export function JobRow({ job, activeTags, onTag, onEditTags, onDelete, onMove, selected, onSelect, showProject, showFolder, onLocation }: {
  job: JobListItem; activeTags: string[]; onTag: (tag: string) => void;
  onEditTags: () => void; onDelete: () => void; onMove?: () => void;
  selected?: boolean; onSelect?: (checked: boolean) => void;
  showProject: boolean; showFolder: boolean; onLocation: (filter: LocationFilter) => void;
}) {
  const Icon = icons[job.kind] ?? FileText;
  const title = job.name || job.filename || job.job_id;
  const href = `/jobs/${encodeURIComponent(job.job_id)}`;
  const running = job.status === "processing";
  const progress = Math.max(0, Math.min(100, job.progress || 0));
  const created = job.created_at ? parseApiDate(job.created_at) : null;
  const validDate = created && !isNaN(created.getTime());
  // Selected labels stay visible even when a job has many tags.
  const orderedTags = [...job.tags].sort((a, b) => Number(activeTags.includes(b)) - Number(activeTags.includes(a)));
  return <li className={cn("group px-3 py-4 transition-colors sm:px-5", selected ? "bg-secondary/70" : "hover:bg-muted/30")}>
    <div className="grid grid-cols-[1rem_minmax(0,1fr)_2.5rem] items-start gap-x-3 gap-y-3 xl:grid-cols-[1rem_minmax(0,1fr)_11rem_8rem_2.5rem] xl:items-center">
      <div className="pt-2 xl:pt-0">{onSelect && <Checkbox aria-label={`Select ${title}`} checked={selected} onCheckedChange={checked => onSelect(checked === true)} />}</div>
      <div className="flex min-w-0 items-start gap-3">
        <div className="hidden h-9 w-9 shrink-0 items-center justify-center rounded-lg border bg-background text-muted-foreground sm:flex"><Icon className="h-4 w-4" aria-hidden="true" /></div>
        <div className="min-w-0 flex-1">
          <Link href={href} className="block truncate py-0.5 text-sm font-semibold underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" title={title}>{title}</Link>
          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted-foreground">
            <span className="capitalize">{job.kind}</span>
            {job.filename && job.filename !== title && <span className="max-w-40 truncate" title={job.filename}>· {job.filename}</span>}
            {!!job.file_size_bytes && <span>· {formatBytes(job.file_size_bytes)}</span>}
            {!!job.total_pages && <span>· {job.pages_completed ?? 0}/{job.total_pages} pages</span>}
            {validDate && <time dateTime={created.toISOString()} title={format(created, "PPpp")}>· {formatDistanceToNow(created, { addSuffix: true })}</time>}
          </div>
          {job.project && (showProject || (showFolder && job.folder)) && <div className="mt-1 flex min-w-0 items-center gap-1 text-[11px] text-muted-foreground">
            <Folder className="mr-1 h-3 w-3 shrink-0" aria-hidden="true" />
            {showProject && <button type="button" onClick={() => onLocation({ projectId: job.project!.id, folderId: null })} className="max-w-[45%] truncate py-1 hover:text-foreground hover:underline" title={`Open project ${job.project.name}`}>{job.project.name}</button>}
            {showProject && showFolder && job.folder && <span aria-hidden="true">/</span>}
            {showFolder && job.folder && <button type="button" onClick={() => onLocation({ projectId: job.project!.id, folderId: job.folder!.id })} className="max-w-[45%] truncate py-1 hover:text-foreground hover:underline" title={`Open folder ${job.folder.name}`}>{job.folder.name}</button>}
          </div>}
          {job.status === "failed" && job.error && <p className="mt-1 line-clamp-1 text-xs text-destructive" title={job.error}>{job.error}</p>}
        </div>
      </div>
      <div role="group" aria-label={`Tags for ${title}`} className="col-start-2 row-start-2 flex min-w-0 items-center gap-1.5 xl:col-start-3 xl:row-start-1">
        {orderedTags.slice(0, 1).map(tag => <button key={tag} type="button" aria-pressed={activeTags.includes(tag)} aria-label={`Filter by tag ${tag}`} title={tag} onClick={() => onTag(tag)} className={cn("inline-flex min-h-8 min-w-0 max-w-[10rem] items-center gap-1.5 rounded-md border px-2 text-[11px] transition-colors", activeTags.includes(tag) ? "border-foreground bg-primary text-primary-foreground" : "border-border/70 text-muted-foreground hover:bg-secondary hover:text-foreground")}><Tag className="h-3 w-3 shrink-0" /><span className="truncate">{tag}</span></button>)}
        {job.tags.length > 1 && <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild><button type="button" aria-label={`Show all ${job.tags.length} tags for ${title}`} className="min-h-8 shrink-0 rounded-md px-2 text-[11px] font-medium text-muted-foreground hover:bg-muted">+{job.tags.length - 1}</button></DropdownMenu.Trigger>
          <DropdownMenu.Portal><DropdownMenu.Content align="start" sideOffset={6} className={cn(menuPanel, "w-64")}>
            <DropdownMenu.Label className="px-3 py-2 text-xs text-muted-foreground">Filter by a tag</DropdownMenu.Label>
            <div className="max-h-60 overflow-y-auto">{job.tags.map(tag => <DropdownMenu.CheckboxItem key={tag} checked={activeTags.includes(tag)} onCheckedChange={() => onTag(tag)} className={cn(menuItem, activeTags.includes(tag) && "bg-secondary")}><Tag className="h-3.5 w-3.5 shrink-0" /><span className="min-w-0 break-words">{tag}</span></DropdownMenu.CheckboxItem>)}</div>
            <DropdownMenu.Separator className="my-1 h-px bg-border" />
            <DropdownMenu.Item className={menuItem} onSelect={onEditTags}>Edit tags</DropdownMenu.Item>
          </DropdownMenu.Content></DropdownMenu.Portal>
        </DropdownMenu.Root>}
        {job.tags.length === 0 && <button type="button" onClick={onEditTags} aria-label={`Add tags to ${title}`} className="inline-flex min-h-8 items-center gap-1.5 rounded-md px-2 text-xs text-muted-foreground hover:bg-muted"><Tag className="h-3 w-3" />Add tags</button>}
      </div>
      <div className="col-start-2 row-start-3 xl:col-start-4 xl:row-start-1"><JobStatus status={job.status} progress={progress} running={running} /></div>
      <div className="col-start-3 row-start-1 xl:col-start-5"><DropdownMenu.Root>
        <DropdownMenu.Trigger asChild><Button variant="ghost" size="icon" className="h-10 w-10 text-muted-foreground" aria-label={`Actions for ${title}`}><MoreHorizontal className="h-5 w-5" /></Button></DropdownMenu.Trigger>
        <DropdownMenu.Portal><DropdownMenu.Content align="end" sideOffset={6} className={menuPanel}>
          <DropdownMenu.Item asChild className={menuItem}><Link href={href}><ArrowUpRight className="h-4 w-4" />Open job</Link></DropdownMenu.Item>
          <DropdownMenu.Item className={menuItem} onSelect={onEditTags}><Tag className="h-4 w-4" />Edit tags</DropdownMenu.Item>
          {onMove && <DropdownMenu.Item className={menuItem} onSelect={onMove}><FolderInput className="h-4 w-4" />Move job</DropdownMenu.Item>}
          <DropdownMenu.Separator className="my-1 h-px bg-border" />
          <DropdownMenu.Item className={cn(menuItem, "text-destructive")} onSelect={onDelete}><Trash2 className="h-4 w-4" />Delete job</DropdownMenu.Item>
        </DropdownMenu.Content></DropdownMenu.Portal>
      </DropdownMenu.Root></div>
    </div>
  </li>;
}

function JobStatus({ status, progress, running }: { status: string; progress: number; running: boolean }) {
  return <div className="space-y-2">
    <span className={cn("inline-flex items-center gap-1.5 whitespace-nowrap rounded-md px-2 py-1 text-[11px] font-medium capitalize", statusStyle[status] || "bg-muted text-muted-foreground")}>
      {running ? <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" /> : <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />}{status}{running && ` · ${progress}%`}
    </span>
    {running && <div role="progressbar" aria-label="Job progress" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100} className="h-1 w-24 overflow-hidden rounded-full bg-secondary"><div className="h-full rounded-full bg-foreground transition-all" style={{ width: `${progress}%` }} /></div>}
  </div>;
}
