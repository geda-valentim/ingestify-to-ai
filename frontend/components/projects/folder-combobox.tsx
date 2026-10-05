"use client";

import { useCallback, useMemo } from "react";
import { projectsApi } from "@/lib/api";
import type { Folder } from "@/types/api";
import { LocationCombobox, type LocationChoice } from "./location-combobox";

/**
 * Optional folder inside the chosen project. Enabled once the project is
 * known; for a project that is about to be created there is nothing to list or
 * resolve, so any folder typed there will be new too.
 */
export function FolderCombobox({
  projectId,
  projectChosen,
  folders,
  value,
  onChange,
  id,
  disabled,
}: {
  /** The chosen project's id, or null if the project is a new name. */
  projectId: string | null;
  /** Whether a project (existing or new) has been chosen at all. */
  projectChosen: boolean;
  folders: Folder[];
  value: LocationChoice | null;
  onChange: (value: LocationChoice | null) => void;
  id?: string;
  disabled?: boolean;
}) {
  const options = useMemo(
    () => (projectId ? folders.map((f) => ({ id: f.id, name: f.name, count: f.job_count })) : []),
    [folders, projectId]
  );
  const resolve = useCallback(
    (name: string) =>
      projectId
        ? projectsApi.resolveFolder(projectId, name)
        : // A new project has no folders: every name is new. Other shape checks are left to the upload.
          Promise.resolve(
            name.includes("/")
              ? { valid: false, error: "A folder name cannot contain “/”" }
              : { valid: true, match: null }
          ),
    [projectId]
  );

  return (
    <LocationCombobox
      id={id}
      noun="folder"
      value={value}
      onChange={onChange}
      options={options}
      resolve={resolve}
      resolveKey={["folders", projectId ?? "new"]}
      disabled={disabled || !projectChosen}
      placeholder={projectChosen ? "No folder (project root)" : "Choose a project first"}
    />
  );
}
