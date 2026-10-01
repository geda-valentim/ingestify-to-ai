"use client";

import { Label } from "@/components/ui/label";
import type { Project } from "@/types/api";
import { FolderCombobox } from "./folder-combobox";
import type { LocationChoice } from "./location-combobox";
import { ProjectCombobox } from "./project-combobox";

/** Project (required) and Folder (optional) of an upload. */
export function UploadLocationFields({
  projects,
  project,
  folder,
  onProjectChange,
  onFolderChange,
  disabled,
  loadError,
}: {
  projects: Project[];
  project: LocationChoice | null;
  folder: LocationChoice | null;
  onProjectChange: (value: LocationChoice | null) => void;
  onFolderChange: (value: LocationChoice | null) => void;
  disabled?: boolean;
  /** `GET /projects` failed: typing a name still works, picking from a list does not. */
  loadError?: string | null;
}) {
  const folders = project?.id ? projects.find((p) => p.id === project.id)?.folders ?? [] : [];

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div className="space-y-2">
        <Label htmlFor="uploadProject">
          Project <span className="text-destructive">*</span>
        </Label>
        <ProjectCombobox
          id="uploadProject"
          projects={projects}
          value={project}
          onChange={onProjectChange}
          disabled={disabled}
        />
        {loadError ? (
          <p className="text-xs text-destructive">Could not load your projects: {loadError}</p>
        ) : (
          project?.id === null && (
            <p className="text-xs text-muted-foreground">A new project “{project.name}” will be created.</p>
          )
        )}
      </div>
      <div className="space-y-2">
        <Label htmlFor="uploadFolder">Folder (Optional)</Label>
        <FolderCombobox
          id="uploadFolder"
          projectId={project?.id ?? null}
          projectChosen={project !== null}
          folders={folders}
          value={folder}
          onChange={onFolderChange}
          disabled={disabled}
        />
        {folder?.id === null && (
          <p className="text-xs text-muted-foreground">A new folder “{folder.name}” will be created.</p>
        )}
      </div>
    </div>
  );
}

/** "Client X › Audio" */
export function locationLabel(project: { name: string } | null | undefined, folder?: { name: string } | null) {
  if (!project) return "";
  return folder ? `${project.name} › ${folder.name}` : project.name;
}
