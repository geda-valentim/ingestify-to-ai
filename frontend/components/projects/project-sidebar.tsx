"use client";

import { Folder as FolderIcon, FolderOpen, Inbox, Layers, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Project } from "@/types/api";

/** `folder_id=root`: the jobs of a project that are in no folder. */
export const ROOT_FOLDER = "root";

export interface LocationFilter {
  projectId: string | null;
  /** A folder id, `ROOT_FOLDER`, or null for the whole project. */
  folderId: string | null;
}

/** The project a filter points at; `folder_id` alone is allowed and implies its project. */
export function filterProject(projects: Project[], filter: LocationFilter): Project | undefined {
  if (filter.projectId) return projects.find((p) => p.id === filter.projectId);
  if (filter.folderId && filter.folderId !== ROOT_FOLDER)
    return projects.find((p) => p.folders?.some((f) => f.id === filter.folderId));
  return undefined;
}

function folderLabel(project: Project | undefined, folderId: string | null): string | null {
  if (!folderId) return null;
  if (folderId === ROOT_FOLDER) return "No folder";
  return project?.folders?.find((f) => f.id === folderId)?.name ?? null;
}

/** "Client X › Audio" for the current filter, or null for "All jobs". */
export function filterTitle(projects: Project[], filter: LocationFilter) {
  const project = filterProject(projects, filter);
  if (!project) return null;
  return { project: project.name, folder: folderLabel(project, filter.folderId) };
}

function Count({ n, active }: { n: number; active?: boolean }) {
  return (
    <span
      className={cn(
        "ml-auto shrink-0 rounded-full px-1.5 py-0.5 text-xs tabular-nums",
        active ? "bg-primary text-primary-foreground" : "text-muted-foreground"
      )}
    >
      {n}
    </span>
  );
}

const itemClass = (active: boolean) =>
  cn(
    "flex w-full min-w-0 items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors",
    active ? "bg-secondary font-medium text-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground"
  );

/** Desktop (md and up): "All jobs", every project with its count, and the selected project's folders. */
export function ProjectSidebar({
  projects,
  isLoading,
  error,
  filter,
  onSelect,
}: {
  projects: Project[];
  isLoading: boolean;
  error: string | null;
  filter: LocationFilter;
  onSelect: (filter: LocationFilter) => void;
}) {
  const selected = filterProject(projects, filter);
  const total = projects.reduce((sum, p) => sum + p.job_count, 0);

  return (
    <nav aria-label="Projects" className="space-y-3">
      <button
        type="button"
        className={itemClass(!selected && !filter.projectId)}
        onClick={() => onSelect({ projectId: null, folderId: null })}
        aria-current={!selected && !filter.projectId ? "page" : undefined}
      >
        <Layers className="h-4 w-4 shrink-0" />
        <span className="truncate">All jobs</span>
        {projects.length > 0 && <Count n={total} active={!selected && !filter.projectId} />}
      </button>

      <div>
        <p className="px-2 pb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Projects</p>
        {isLoading ? (
          <div className="flex items-center gap-2 px-2 py-1.5 text-sm text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Loading…
          </div>
        ) : error ? (
          <p className="px-2 py-1.5 text-xs text-destructive">{error}</p>
        ) : projects.length === 0 ? (
          <p className="px-2 py-1.5 text-xs text-muted-foreground">No projects yet. Name one when you upload.</p>
        ) : (
          <ul className="space-y-0.5">
            {projects.map((p) => {
              const isSelected = selected?.id === p.id;
              const projectActive = isSelected && !filter.folderId;
              return (
                <li key={p.id}>
                  <button
                    type="button"
                    className={itemClass(projectActive)}
                    onClick={() => onSelect({ projectId: p.id, folderId: null })}
                    aria-current={projectActive ? "page" : undefined}
                    title={p.name}
                  >
                    {isSelected ? (
                      <FolderOpen className="h-4 w-4 shrink-0" />
                    ) : (
                      <FolderIcon className="h-4 w-4 shrink-0" />
                    )}
                    <span className="truncate">{p.name}</span>
                    <Count n={p.job_count} active={projectActive} />
                  </button>

                  {isSelected && (
                    <ul className="ml-4 mt-0.5 space-y-0.5 border-l pl-2">
                      {(p.folders ?? []).map((f) => {
                        const active = filter.folderId === f.id;
                        return (
                          <li key={f.id}>
                            <button
                              type="button"
                              className={itemClass(active)}
                              onClick={() => onSelect({ projectId: p.id, folderId: f.id })}
                              aria-current={active ? "page" : undefined}
                              title={f.name}
                            >
                              <FolderIcon className="h-3.5 w-3.5 shrink-0" />
                              <span className="truncate">{f.name}</span>
                              <Count n={f.job_count} active={active} />
                            </button>
                          </li>
                        );
                      })}
                      <li>
                        <button
                          type="button"
                          className={itemClass(filter.folderId === ROOT_FOLDER)}
                          onClick={() => onSelect({ projectId: p.id, folderId: ROOT_FOLDER })}
                          aria-current={filter.folderId === ROOT_FOLDER ? "page" : undefined}
                        >
                          <Inbox className="h-3.5 w-3.5 shrink-0" />
                          <span className="truncate italic">No folder</span>
                          <Count n={p.root_job_count} active={filter.folderId === ROOT_FOLDER} />
                        </button>
                      </li>
                    </ul>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </nav>
  );
}

const selectClass =
  "h-10 w-full min-w-0 rounded-md border border-input bg-background px-3 text-sm ring-offset-background focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2";

/** Below md there is no room for a column (and no Sheet component): two plain selects. */
export function ProjectSelects({
  projects,
  filter,
  onSelect,
}: {
  projects: Project[];
  filter: LocationFilter;
  onSelect: (filter: LocationFilter) => void;
}) {
  const selected = filterProject(projects, filter);
  const total = projects.reduce((sum, p) => sum + p.job_count, 0);

  return (
    <div className="grid grid-cols-2 gap-2">
      <select
        aria-label="Project"
        className={selectClass}
        value={selected?.id ?? ""}
        onChange={(e) => onSelect({ projectId: e.target.value || null, folderId: null })}
      >
        <option value="">All jobs ({total})</option>
        {projects.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name} ({p.job_count})
          </option>
        ))}
      </select>
      <select
        aria-label="Folder"
        className={selectClass}
        disabled={!selected}
        value={filter.folderId ?? ""}
        onChange={(e) => selected && onSelect({ projectId: selected.id, folderId: e.target.value || null })}
      >
        <option value="">{selected ? "All folders" : "Folder"}</option>
        {selected?.folders?.map((f) => (
          <option key={f.id} value={f.id}>
            {f.name} ({f.job_count})
          </option>
        ))}
        {selected && <option value={ROOT_FOLDER}>No folder ({selected.root_job_count})</option>}
      </select>
    </div>
  );
}
