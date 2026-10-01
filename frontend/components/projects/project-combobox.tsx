"use client";

import { useCallback, useMemo } from "react";
import { projectsApi } from "@/lib/api";
import type { Project } from "@/types/api";
import { LocationCombobox, type LocationChoice } from "./location-combobox";

/** Pick an existing project or type a new name (created by the upload's get-or-add). */
export function ProjectCombobox({
  projects,
  value,
  onChange,
  id,
  allowCreate = true,
  disabled,
  invalid,
  autoFocus,
  placeholder,
}: {
  projects: Project[];
  value: LocationChoice | null;
  onChange: (value: LocationChoice | null) => void;
  id?: string;
  allowCreate?: boolean;
  disabled?: boolean;
  invalid?: boolean;
  autoFocus?: boolean;
  placeholder?: string;
}) {
  const options = useMemo(
    () => projects.filter((p) => !p.archived).map((p) => ({ id: p.id, name: p.name, count: p.job_count })),
    [projects]
  );
  const resolve = useCallback((name: string) => projectsApi.resolve(name), []);

  return (
    <LocationCombobox
      id={id}
      noun="project"
      value={value}
      onChange={onChange}
      options={options}
      resolve={resolve}
      resolveKey={["projects"]}
      allowCreate={allowCreate}
      disabled={disabled}
      invalid={invalid}
      autoFocus={autoFocus}
      placeholder={placeholder ?? (allowCreate ? "Choose a project or type a new name" : "Choose a project")}
    />
  );
}
