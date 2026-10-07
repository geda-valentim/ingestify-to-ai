"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Archive, FolderOpen, Loader2, Pencil, Plus, Search, Trash2 } from "lucide-react";
import { projectsApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store/auth";
import { loginUrl } from "@/lib/session";
import { cn, formatApiError, formatBytes, parseApiDate } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";
import { AppHeader } from "@/components/app-header";
import { useProjects } from "@/components/projects/use-projects";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { AlertDialog, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import type { Project, Folder } from "@/types/api";

type Editor = { kind: "project-create" } | { kind: "project-edit"; project: Project }
  | { kind: "folder-create"; project: Project } | { kind: "folder-edit"; project: Project; folder: Folder };
type Removal = { kind: "project"; project: Project } | { kind: "folder"; project: Project; folder: Folder };

function Stat({ label, value }: { label: string; value: number | string }) {
  return <div className="rounded-lg border bg-background p-4"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p></div>;
}

export default function ProjectsPage() {
  return <Suspense fallback={<div className="flex min-h-screen items-center justify-center"><Loader2 className="h-8 w-8 animate-spin" /></div>}><ProjectManagement /></Suspense>;
}

function ProjectManagement() {
  const router = useRouter();
  const params = useSearchParams();
  const client = useQueryClient();
  const { toast } = useToast();
  const token = useAuthStore(s => s.token);
  const hasHydrated = useAuthStore(s => s._hasHydrated);
  const authenticated = useAuthStore(s => s.token !== null && s.user !== null);
  const query = useProjects({ refetchInterval: 30_000 });
  const projects = query.data?.projects ?? [];
  const [search, setSearch] = useState("");
  const [editor, setEditor] = useState<Editor | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [removal, setRemoval] = useState<Removal | null>(null);
  const selectedId = params.get("project_id");
  const selected = selectedId ? projects.find(p => p.id === selectedId) : projects[0];
  const visible = projects.filter(p => p.name.toLocaleLowerCase().includes(search.toLocaleLowerCase()));

  useEffect(() => { if (hasHydrated && !authenticated) router.replace(loginUrl()); }, [hasHydrated, authenticated, router]);

  const refresh = async () => {
    await Promise.all(["projects", "jobs", "job-status", "api-keys"].map(key => client.invalidateQueries({ queryKey: [key] })));
  };
  const save = useMutation({
    mutationFn: async () => {
      if (!editor) return;
      if (editor.kind === "project-create") {
        const created = await projectsApi.create(name);
        router.replace(`/projects?project_id=${encodeURIComponent(created.id)}`, { scroll: false });
      } else if (editor.kind === "project-edit") await projectsApi.update(editor.project.id, { name, description: description.trim() || null });
      else if (editor.kind === "folder-create") await projectsApi.createFolder(editor.project.id, name);
      else await projectsApi.renameFolder(editor.folder.id, name);
    },
    onSuccess: async () => { await refresh(); setEditor(null); toast({ title: "Saved" }); },
  });
  const remove = useMutation({
    mutationFn: async () => {
      if (!removal) return;
      if (removal.kind === "folder") await projectsApi.deleteFolder(removal.folder.id);
      else {
        await projectsApi.delete(removal.project.id);
        if (selected?.id === removal.project.id) router.replace("/projects", { scroll: false });
      }
    },
    onSuccess: async () => { await refresh(); setRemoval(null); toast({ title: "Deleted" }); },
  });
  const archive = useMutation({
    mutationFn: (p: Project) => projectsApi.update(p.id, { archived: !p.archived }),
    onSuccess: refresh,
    onError: error => toast({ title: "Could not update project", description: formatApiError(error), variant: "destructive" }),
  });
  const openEditor = (next: Editor) => {
    setName(next.kind === "project-edit" ? next.project.name : next.kind === "folder-edit" ? next.folder.name : "");
    setDescription(next.kind === "project-edit" ? next.project.description ?? "" : "");
    save.reset(); setEditor(next);
  };
  const openRemoval = (next: Removal) => { remove.reset(); setRemoval(next); };
  const totals = projects.reduce((t, p) => ({ jobs: t.jobs + p.job_count, completed: t.completed + p.completed_count, active: t.active + p.active_count, failed: t.failed + p.failed_count }), { jobs: 0, completed: 0, active: 0, failed: 0 });

  if (!hasHydrated || !authenticated) return <div className="flex min-h-screen items-center justify-center"><Loader2 className="h-8 w-8 animate-spin" /></div>;

  return <div className="min-h-screen bg-muted/20">
    <AppHeader />
    <main className="container mx-auto space-y-6 px-4 py-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div><h1 className="text-3xl font-bold">Projects</h1><p className="mt-1 text-sm text-muted-foreground">Manage your projects, folders and job destinations.</p></div>
        <Button onClick={() => openEditor({ kind: "project-create" })}><Plus className="mr-2 h-4 w-4" />New project</Button>
      </div>
      {query.isLoading ? <p className="flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin" />Loading projects…</p>
        : query.isError ? <div role="alert" className="rounded-lg border border-destructive p-4"><p>{formatApiError(query.error)}</p><Button variant="outline" className="mt-3" onClick={() => query.refetch()}>Retry</Button></div>
        : <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4"><Stat label="All jobs" value={totals.jobs} /><Stat label="Completed" value={totals.completed} /><Stat label="Queued / processing" value={totals.active} /><Stat label="Failed" value={totals.failed} /></div>
          {projects.length === 0 ? <div className="rounded-xl border bg-background p-10 text-center"><FolderOpen className="mx-auto mb-3 h-10 w-10 text-muted-foreground" /><h2 className="font-medium">No projects yet</h2><p className="mt-1 text-sm text-muted-foreground">Create a project and folders before your next upload.</p></div>
            : <div className="grid items-start gap-6 lg:grid-cols-[280px_1fr]">
              <aside className="space-y-3">
                <div className="relative"><Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" /><Input aria-label="Search projects" className="pl-9" placeholder="Search projects" value={search} onChange={e => setSearch(e.target.value)} /></div>
                <p className="text-xs text-muted-foreground">{projects.length} / {query.data?.limits.max_projects} projects</p>
                <nav aria-label="Project management" className="max-h-[65vh] space-y-1 overflow-y-auto rounded-lg border bg-background p-2">
                  {visible.length === 0 && <p className="p-3 text-sm text-muted-foreground">No matching projects</p>}
                  {visible.map(p => <Link key={p.id} href={`/projects?project_id=${encodeURIComponent(p.id)}`} aria-current={selected?.id === p.id ? "page" : undefined} className={cn("flex items-center justify-between gap-2 rounded-md px-3 py-2 text-sm hover:bg-muted", selected?.id === p.id && "bg-secondary font-medium")}>
                    <span className="min-w-0"><span className="block truncate">{p.name}</span>{p.archived && <span className="text-xs text-muted-foreground">Archived</span>}</span><span className="tabular-nums text-muted-foreground">{p.job_count}</span>
                  </Link>)}
                </nav>
              </aside>
              {selected ? <div className="space-y-5">
                <Card><CardHeader><div className="flex flex-wrap items-start justify-between gap-3">
                  <div><CardTitle className="break-words">{selected.name}</CardTitle>{selected.archived && <p className="mt-2 text-sm text-muted-foreground">Archived · existing results remain available</p>}</div>
                  <div className="flex flex-wrap gap-2">
                    <Button variant="outline" size="sm" onClick={() => openEditor({ kind: "project-edit", project: selected })}><Pencil className="mr-2 h-4 w-4" />Edit project</Button>
                    <Button variant="outline" size="sm" disabled={archive.isPending || (!selected.archived && selected.api_keys.length > 0)} onClick={() => archive.mutate(selected)}><Archive className="mr-2 h-4 w-4" />{selected.archived ? "Restore" : "Archive"}</Button>
                    <Button variant="ghost" size="sm" onClick={() => openRemoval({ kind: "project", project: selected })}><Trash2 className="mr-2 h-4 w-4" />Delete project</Button>
                  </div>
                </div></CardHeader><CardContent className="space-y-4">
                  {selected.description && <p className="whitespace-pre-wrap text-sm">{selected.description}</p>}
                  <div className="flex flex-wrap gap-2"><Button asChild size="sm"><Link href={`/jobs?project_id=${encodeURIComponent(selected.id)}`}>View jobs</Link></Button>{!selected.archived && <Button asChild variant="outline" size="sm"><Link href={`/convert?project_id=${encodeURIComponent(selected.id)}`}>Upload here</Link></Button>}</div>
                  {selected.api_keys.length > 0 && <p className="text-sm text-muted-foreground">Linked API keys: {selected.api_keys.map(k => k.name || k.id).join(", ")}. <Link href="/api-keys" className="underline">Change their project</Link> before archiving or deleting.</p>}
                  {selected.last_job_at && <p className="text-xs text-muted-foreground">Last job: {parseApiDate(selected.last_job_at).toLocaleString()}</p>}
                </CardContent></Card>
                <section aria-label="Project statistics" className="space-y-3">
                  <h2 className="text-lg font-semibold">Statistics</h2>
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-3"><Stat label="Total jobs" value={selected.job_count} /><Stat label="Completed" value={selected.completed_count} /><Stat label="Queued / processing" value={selected.active_count} /><Stat label="Failed" value={selected.failed_count} /><Stat label="Partial" value={selected.partial_count ?? 0} /><Stat label="Cancelled" value={selected.cancelled_count} /><Stat label="Source volume" value={formatBytes(selected.total_bytes)} /></div>
                  <p className="text-xs text-muted-foreground">Source volume sums original file sizes; it does not measure retained storage. Uploads and live sessions are counted once; document pages are not counted separately.</p>
                </section>
                <Card><CardHeader><div className="flex flex-wrap items-center justify-between gap-3"><CardTitle className="text-lg">Folders</CardTitle><Button size="sm" variant="outline" disabled={selected.archived} onClick={() => openEditor({ kind: "folder-create", project: selected })}><Plus className="mr-2 h-4 w-4" />New folder</Button></div></CardHeader>
                  <CardContent className="space-y-3">
                    <div className="flex items-center justify-between rounded-md bg-muted/40 px-3 py-2 text-sm"><Link className="hover:underline" href={`/jobs?project_id=${encodeURIComponent(selected.id)}&folder_id=root`}>No folder</Link><span>{selected.root_job_count} {selected.root_job_count === 1 ? "job" : "jobs"}</span></div>
                    {(selected.folders ?? []).map(f => <div key={f.id} className="flex flex-wrap items-center justify-between gap-2 border-b py-2 last:border-0">
                      <Link className="min-w-0 flex-1 truncate text-sm hover:underline" href={`/jobs?project_id=${encodeURIComponent(selected.id)}&folder_id=${encodeURIComponent(f.id)}`}>{f.name}</Link>
                      <span className="text-xs text-muted-foreground">{f.job_count} {f.job_count === 1 ? "job" : "jobs"}</span>
                      <Button size="icon" variant="ghost" aria-label={`Edit folder ${f.name}`} onClick={() => openEditor({ kind: "folder-edit", project: selected, folder: f })}><Pencil className="h-4 w-4" /></Button>
                      <Button size="icon" variant="ghost" aria-label={`Delete folder ${f.name}`} onClick={() => openRemoval({ kind: "folder", project: selected, folder: f })}><Trash2 className="h-4 w-4" /></Button>
                    </div>)}
                    {!selected.folders?.length && <p className="text-sm text-muted-foreground">No folders yet.</p>}
                    <p className="text-xs text-muted-foreground">{selected.folders?.length ?? 0} / {query.data?.limits.max_folders_per_project} folders</p>
                  </CardContent>
                </Card>
              </div> : <p role="alert">Project not found. Choose a project from the list.</p>}
            </div>}
        </>}
    </main>
    <Dialog open={editor !== null} onOpenChange={open => { if (!open && !save.isPending) setEditor(null); }}>
      <DialogContent><DialogHeader><DialogTitle>{editor?.kind === "project-create" ? "New project" : editor?.kind === "project-edit" ? "Edit project" : editor?.kind === "folder-create" ? "New folder" : "Edit folder"}</DialogTitle>
        <DialogDescription>{editor?.kind.endsWith("edit") ? "You can correct capitalization, accents and spacing in the name." : "Choose a name to organize your jobs."}</DialogDescription></DialogHeader>
        <form className="space-y-4" onSubmit={e => { e.preventDefault(); save.mutate(); }}>
          <div className="space-y-2"><Label htmlFor="project-editor-name">Name</Label><Input id="project-editor-name" value={name} onChange={e => setName(e.target.value)} maxLength={100} required autoFocus disabled={save.isPending} /></div>
          {editor?.kind === "project-edit" && <div className="space-y-2"><Label htmlFor="project-editor-description">Description</Label><textarea id="project-editor-description" className="min-h-24 w-full rounded-md border bg-background p-3 text-sm" value={description} onChange={e => setDescription(e.target.value)} maxLength={4000} disabled={save.isPending} /></div>}
          {save.isError && <p role="alert" className="text-sm text-destructive">{formatApiError(save.error)}</p>}
          <div className="flex justify-end gap-2"><Button type="button" variant="outline" disabled={save.isPending} onClick={() => setEditor(null)}>Cancel</Button><Button type="submit" disabled={save.isPending || !name.trim()}>{save.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Save</Button></div>
        </form>
      </DialogContent>
    </Dialog>
    <AlertDialog open={removal !== null} onOpenChange={open => { if (!open && !remove.isPending) setRemoval(null); }}>
      <AlertDialogContent><AlertDialogHeader><AlertDialogTitle>Delete {removal?.kind === "folder" ? `folder “${removal.folder.name}”` : `project “${removal?.project.name}”`}?</AlertDialogTitle><AlertDialogDescription>
        {removal?.kind === "folder" ? "Jobs in this folder will move to the project root. Their files, results and tags will be kept." : "Only empty projects without linked API keys can be deleted. Move their jobs and unlink their API keys first."}
      </AlertDialogDescription></AlertDialogHeader>
        {remove.isError && <p role="alert" className="text-sm text-destructive">{formatApiError(remove.error)}</p>}
        <AlertDialogFooter><AlertDialogCancel disabled={remove.isPending}>Cancel</AlertDialogCancel><Button variant="destructive" disabled={remove.isPending} onClick={() => remove.mutate()}>{remove.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Delete</Button></AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </div>;
}
