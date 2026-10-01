"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Folder as FolderIcon, Loader2, Pencil } from "lucide-react";
import { apiKeysApi } from "@/lib/api";
import { formatApiError } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";
import { Button } from "@/components/ui/button";
import type { APIKeyInfo, Project } from "@/types/api";
import type { LocationChoice } from "./location-combobox";
import { ProjectCombobox } from "./project-combobox";

export function ApiKeyProjectHelp() {
  return (
    <p className="text-xs text-muted-foreground">
      Uploads with this key that send no <code className="rounded bg-muted px-1">project</code> go to this project.
      When you change it, files already sent that are in another project will be processed again.
    </p>
  );
}

/**
 * A key's bound project, and rebinding it (`PATCH /api-keys/{id}`).
 *
 * Only existing projects can be picked here: the PATCH takes a `project_id`,
 * and phase 1 has no endpoint that creates a project on its own.
 */
export function ApiKeyProject({ apiKey, projects }: { apiKey: APIKeyInfo; projects: Project[] }) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<LocationChoice | null>(null);

  const save = useMutation({
    mutationFn: (projectId: string | null) => apiKeysApi.setProject(apiKey.id, projectId),
    onSuccess: (_, projectId) => {
      queryClient.invalidateQueries({ queryKey: ["api-keys"] });
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      setEditing(false);
      toast({
        title: projectId ? `“${apiKey.name}” now uploads to ${draft?.name ?? "the chosen project"}` : `“${apiKey.name}” has no project`,
        description: projectId ? undefined : "Its uploads must now send a project, or they are rejected.",
      });
    },
    onError: (error) => {
      toast({ title: "Could not change the key's project", description: formatApiError(error), variant: "destructive" });
    },
  });

  if (!editing) {
    return (
      <div className="flex min-w-0 flex-wrap items-center gap-2 text-sm">
        <span className="text-muted-foreground">Project:</span>
        {apiKey.project ? (
          <span className="inline-flex min-w-0 items-center gap-1 rounded-md border border-primary/20 bg-primary/5 px-2 py-0.5 text-xs font-medium">
            <FolderIcon className="h-3 w-3 shrink-0 text-primary" />
            <span className="truncate">{apiKey.project.name}</span>
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 text-xs text-amber-700 dark:text-amber-400">
            <AlertTriangle className="h-3 w-3" />
            None: uploads must send a project
          </span>
        )}
        <Button
          variant="ghost"
          size="sm"
          className="h-7 px-2"
          onClick={() => {
            setDraft(apiKey.project ? { id: apiKey.project.id, name: apiKey.project.name } : null);
            setEditing(true);
          }}
        >
          <Pencil className="h-3 w-3 mr-1" />
          Change
        </Button>
      </div>
    );
  }

  const unchanged = (draft?.id ?? null) === (apiKey.project?.id ?? null);

  return (
    <div className="space-y-2">
      <ProjectCombobox
        projects={projects}
        value={draft}
        onChange={setDraft}
        allowCreate={false}
        disabled={save.isPending}
        autoFocus
      />
      <ApiKeyProjectHelp />
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          onClick={() => draft?.id && save.mutate(draft.id)}
          disabled={!draft?.id || unchanged || save.isPending}
        >
          {save.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
          Save
        </Button>
        {apiKey.project && (
          <Button
            size="sm"
            variant="outline"
            disabled={save.isPending}
            onClick={() => {
              if (
                confirm(
                  `Remove the project from “${apiKey.name}”? Uploads with this key that send no project will be rejected.`
                )
              ) {
                save.mutate(null);
              }
            }}
          >
            Remove project
          </Button>
        )}
        <Button size="sm" variant="ghost" onClick={() => setEditing(false)} disabled={save.isPending}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
