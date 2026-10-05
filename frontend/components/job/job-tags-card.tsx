"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Pencil } from "lucide-react";
import { tagsApi } from "@/lib/api";
import { formatApiError } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TagChip, TagInput } from "@/components/tag-input";

/** The job's tags: each links to the job list filtered by it, and can be edited in place. */
export function JobTagsCard({ jobId, tags }: { jobId: string; tags: string[] }) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<string[]>(tags);

  const save = useMutation({
    mutationFn: (next: string[]) => tagsApi.setForJob(jobId, next),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["job-status", jobId] });
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.invalidateQueries({ queryKey: ["tags"] });
      setEditing(false);
    },
    onError: (error) => {
      toast({ title: "Could not save tags", description: formatApiError(error), variant: "destructive" });
    },
  });

  return (
    <Card>
      <CardHeader className="pb-3 flex-row items-center justify-between space-y-0">
        <CardTitle className="text-base">Tags</CardTitle>
        {!editing && (
          <Button
            variant="ghost"
            size="sm"
            className="h-8"
            onClick={() => {
              setDraft(tags);
              setEditing(true);
            }}
          >
            <Pencil className="h-3.5 w-3.5 mr-1.5" />
            Edit
          </Button>
        )}
      </CardHeader>
      <CardContent>
        {editing ? (
          <div className="space-y-3">
            <TagInput value={draft} onChange={setDraft} autoFocus />
            <div className="flex gap-2">
              <Button size="sm" onClick={() => save.mutate(draft)} disabled={save.isPending}>
                {save.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                Save
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setEditing(false)} disabled={save.isPending}>
                Cancel
              </Button>
            </div>
          </div>
        ) : tags.length ? (
          <div className="flex flex-wrap gap-1.5">
            {tags.map((tag) => (
              <Link key={tag} href={`/jobs?tag=${encodeURIComponent(tag)}`} title={`All jobs tagged “${tag}”`}>
                <TagChip tag={tag} className="hover:border-primary/60 hover:bg-primary/10" />
              </Link>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">No tags yet.</p>
        )}
      </CardContent>
    </Card>
  );
}
