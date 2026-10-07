"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { projectsApi } from "@/lib/api";
import { formatApiError } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useProjects } from "./use-projects";

/** Picking a new project resets the folder: folders never cross projects. */
export function MoveJobsDialog({ jobIds, open, onOpenChange, onMoved, single = false }: {
  jobIds: string[]; open: boolean; onOpenChange: (open: boolean) => void; onMoved?: () => void; single?: boolean;
}) {
  const query = useProjects();
  const client = useQueryClient();
  const { toast } = useToast();
  const [projectId, setProjectId] = useState("");
  const [folderId, setFolderId] = useState("");
  const projects = (query.data?.projects ?? []).filter(p => !p.archived);
  const destination = projects.find(p => p.id === projectId);
  const move = useMutation({
    mutationFn: () => single ? projectsApi.moveJob(jobIds[0], projectId, folderId || null) : projectsApi.move(jobIds, projectId, folderId || null),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["projects"] }),
        client.invalidateQueries({ queryKey: ["jobs"] }),
        client.invalidateQueries({ queryKey: ["job-status"] }),
      ]);
      toast({ title: jobIds.length === 1 ? "Job moved" : `${jobIds.length} jobs moved` });
      onMoved?.();
      onOpenChange(false);
    },
  });
  useEffect(() => {
    if (!open) { setProjectId(""); setFolderId(""); move.reset(); }
    // Clear drafts when any close path (Cancel, Escape or success) is used.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);
  return <Dialog open={open} onOpenChange={next => { if (!move.isPending) { onOpenChange(next); if (!next) { setProjectId(""); setFolderId(""); move.reset(); } } }}>
    <DialogContent>
      <DialogHeader><DialogTitle>Move {jobIds.length === 1 ? "job" : `${jobIds.length} jobs`}</DialogTitle>
        <DialogDescription>Choose a destination. Results and tags stay with the jobs.</DialogDescription></DialogHeader>
      <form className="space-y-4" onSubmit={e => { e.preventDefault(); move.mutate(); }}>
        <div className="space-y-2"><Label htmlFor="move-project">Destination project</Label>
          <select id="move-project" className="flex h-10 w-full rounded-md border bg-background px-3 text-sm" value={projectId} disabled={move.isPending || query.isLoading} required
            onChange={e => { setProjectId(e.target.value); setFolderId(""); move.reset(); }}>
            <option value="">Choose a project</option>{projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
        <div className="space-y-2"><Label htmlFor="move-folder">Destination folder</Label>
          <select id="move-folder" className="flex h-10 w-full rounded-md border bg-background px-3 text-sm" value={folderId} disabled={!destination || move.isPending} onChange={e => setFolderId(e.target.value)}>
            <option value="">No folder</option>{destination?.folders?.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
        </div>
        {query.isError && <p role="alert" className="text-sm text-destructive">{formatApiError(query.error)}</p>}
        {!query.isLoading && !query.isError && projects.length === 0 && <p className="text-sm">Create an active project in <Link className="underline" href="/projects">Projects</Link> first.</p>}
        {move.isError && <p role="alert" className="text-sm text-destructive">{formatApiError(move.error)}</p>}
        <div className="flex justify-end gap-2"><Button type="button" variant="outline" disabled={move.isPending} onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button type="submit" disabled={!destination || move.isPending || jobIds.length === 0 || jobIds.length > 100}>{move.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Move</Button></div>
      </form>
    </DialogContent>
  </Dialog>;
}
