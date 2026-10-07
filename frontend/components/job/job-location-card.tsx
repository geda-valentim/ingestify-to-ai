"use client";
import { useState } from "react";
import Link from "next/link";
import { FolderInput } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { MoveJobsDialog } from "@/components/projects/move-jobs-dialog";
import type { ProjectRef } from "@/types/api";

export function JobLocationCard({ jobId, project, folder }: { jobId: string; project?: ProjectRef | null; folder?: ProjectRef | null }) {
  const [open, setOpen] = useState(false);
  return <Card>
    <CardHeader className="flex-row items-center justify-between space-y-0 pb-3">
      <CardTitle className="text-base">Location</CardTitle>
      <Button variant="ghost" size="sm" onClick={() => setOpen(true)}><FolderInput className="mr-1.5 h-4 w-4" />Move</Button>
    </CardHeader>
    <CardContent>
      {project ? <div className="flex flex-wrap items-center gap-2 text-sm">
        <Link className="hover:underline" href={`/projects?project_id=${encodeURIComponent(project.id)}`}>{project.name}</Link>
        <span className="text-muted-foreground">›</span>
        {folder ? <Link className="hover:underline" href={`/jobs?project_id=${encodeURIComponent(project.id)}&folder_id=${encodeURIComponent(folder.id)}`}>{folder.name}</Link> : <span className="text-muted-foreground">No folder</span>}
      </div> : <p className="text-sm text-muted-foreground">No project assigned</p>}
      <MoveJobsDialog jobIds={[jobId]} open={open} onOpenChange={setOpen} single />
    </CardContent>
  </Card>;
}
