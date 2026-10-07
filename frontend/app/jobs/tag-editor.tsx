"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { tagsApi } from "@/lib/api";
import { formatApiError } from "@/lib/utils";
import { TagInput } from "@/components/tag-input";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useToast } from "@/hooks/use-toast";
import type { JobListItem } from "@/types/api";

// Mounted for one job so reopening always starts with the latest saved tags.
export function JobTagEditor({ job, onClose }: { job: JobListItem; onClose: () => void }) {
  const [tags, setTags] = useState(job.tags);
  const client = useQueryClient();
  const { toast } = useToast();
  const save = useMutation({
    mutationFn: () => tagsApi.setForJob(job.job_id, tags),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["jobs"] });
      client.invalidateQueries({ queryKey: ["tags"] });
      client.invalidateQueries({ queryKey: ["job-status", job.job_id] });
      toast({ title: "Tags updated" });
      onClose();
    },
  });
  return <Dialog open onOpenChange={open => { if (!open && !save.isPending) onClose(); }}>
    <DialogContent className="flex h-[28rem] max-h-[calc(100dvh_-_2rem)] w-[calc(100%_-_2rem)] flex-col rounded-xl">
      <DialogHeader><DialogTitle>Edit tags</DialogTitle><DialogDescription className="break-words">Organize {job.name || job.filename || "this job"} with searchable labels.</DialogDescription></DialogHeader>
      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-1"><label htmlFor="job-tags" className="text-sm font-medium">Tags</label><TagInput id="job-tags" value={tags} onChange={setTags} disabled={save.isPending} autoFocus /><p className="text-xs text-muted-foreground">Press Enter or comma to add a tag. Up to 20 tags per job.</p></div>
      {save.isError && <p role="alert" className="text-sm text-destructive">{formatApiError(save.error)}</p>}
      <div className="flex shrink-0 justify-end gap-2"><Button variant="outline" onClick={onClose} disabled={save.isPending}>Cancel</Button><Button onClick={() => save.mutate()} disabled={save.isPending}>{save.isPending ? "Saving…" : "Save tags"}</Button></div>
    </DialogContent>
  </Dialog>;
}
