"use client";

import { Suspense, useState, useEffect, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FileText, Upload as UploadIcon, Link as LinkIcon, Cloud } from "lucide-react";
import { useAuthStore } from "@/lib/store/auth";
import { loginUrl } from "@/lib/session";
import { ApiError, jobsApi } from "@/lib/api";
import { formatApiError } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";
import { Button } from "@/components/ui/button";
import { AppHeader } from "@/components/app-header";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { FileUpload } from "@/components/upload/file-upload";
import { TagInput } from "@/components/tag-input";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { LocationChoice } from "@/components/projects/location-combobox";
import { UploadLocationFields, locationLabel } from "@/components/projects/upload-location-fields";
import {
  forgetLastProject,
  readLastProject,
  useProjects,
  writeLastProject,
} from "@/components/projects/use-projects";
import type { UploadLocation, UploadRequest } from "@/types/api";

export default function ConversionPage() {
  // useSearchParams needs a Suspense boundary in the App Router.
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center">
          <div className="text-muted-foreground">Loading...</div>
        </div>
      }
    >
      <ConversionWorkspace />
    </Suspense>
  );
}

/** The request fields for a chosen project/folder: ids when picked, names when typed. */
function toUploadLocation(project: LocationChoice, folder: LocationChoice | null): UploadLocation {
  return {
    ...(project.id ? { project_id: project.id } : { project: project.name }),
    ...(folder ? (folder.id ? { folder_id: folder.id } : { folder: folder.name }) : {}),
  };
}

function ConversionWorkspace() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const { user } = useAuthStore();
  const token = useAuthStore((state) => state.token);
  const isAuthenticated = useAuthStore((state) => state.token !== null && state.user !== null);
  const hasHydrated = useAuthStore((state) => state._hasHydrated);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [customName, setCustomName] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);
  const [urlSource, setUrlSource] = useState("");
  const [gdriveSource, setGdriveSource] = useState("");
  const [gdriveToken, setGdriveToken] = useState("");
  const [dropboxSource, setDropboxSource] = useState("");
  const [dropboxToken, setDropboxToken] = useState("");
  const [project, setProject] = useState<LocationChoice | null>(null);
  const [folder, setFolder] = useState<LocationChoice | null>(null);

  const projectsQuery = useProjects();
  const projects = projectsQuery.data?.projects ?? [];

  useEffect(() => {
    if (hasHydrated && !isAuthenticated) {
      router.replace(loginUrl());
    }
  }, [isAuthenticated, hasHydrated, router]);

  // The starting project is never one the user did not choose: the URL
  // (?project_id= / ?project=, e.g. "New upload" from a project in /jobs), else
  // the last project this user uploaded to, else none.
  const initialized = useRef(false);
  useEffect(() => {
    if (initialized.current || !user) return;
    const listReady = projectsQuery.isSuccess || projectsQuery.isError;
    const urlProjectId = searchParams.get("project_id");
    const urlProject = searchParams.get("project")?.trim();
    const urlFolderId = searchParams.get("folder_id");
    const urlFolder = searchParams.get("folder")?.trim();

    if (urlProjectId) {
      if (!listReady) return;
      const p = projects.find((x) => x.id === urlProjectId && !x.archived);
      if (p) {
        setProject({ id: p.id, name: p.name });
        const f = urlFolderId ? p.folders?.find((x) => x.id === urlFolderId) : undefined;
        if (f) setFolder({ id: f.id, name: f.name });
        else if (urlFolder) setFolder({ id: null, name: urlFolder });
      }
    } else if (urlProject) {
      setProject({ id: null, name: urlProject });
      if (urlFolder) setFolder({ id: null, name: urlFolder });
    } else {
      const last = readLastProject(user.id);
      if (last) {
        if (!listReady) return;
        if (projectsQuery.isError) {
          setProject(last);
        } else {
          // Show its current name, and drop it if the project is gone.
          const p = projects.find((x) => x.id === last.id && !x.archived);
          if (p) setProject({ id: p.id, name: p.name });
          else forgetLastProject(user.id);
        }
      }
    }
    initialized.current = true;
  }, [user, searchParams, projects, projectsQuery.isSuccess, projectsQuery.isError]);

  const handleProjectChange = (next: LocationChoice | null) => {
    // A typed name that turned out to be an existing project is the same choice:
    // keep the folder. Any other change of project clears it.
    const sameName = project?.id === null && next?.id && next.name === project.name;
    const sameProject = next?.id != null && next.id === project?.id;
    if (!sameName && !sameProject) setFolder(null);
    setProject(next);
  };

  const uploadMutation = useMutation({
    mutationFn: (request: UploadRequest) => jobsApi.upload(request),
    onSuccess: (data) => {
      setUploadSuccess(data.job_id);
      if (data.project && user) writeLastProject(user.id, data.project);
      else if (project?.id && user) writeLastProject(user.id, { id: project.id, name: project.name });
      const sentTo = data.project ? locationLabel(data.project, data.folder) : project ? locationLabel(project, folder) : "";
      const created = [data.project?.created && "Project created", data.folder?.created && "Folder created"]
        .filter(Boolean)
        .join(" · ");
      toast({
        title: sentTo ? `Sent to ${sentTo}` : "Upload started",
        description: created || undefined,
      });
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      // Clear all forms
      setSelectedFile(null);
      setCustomName("");
      setTags([]);
      setUrlSource("");
      setGdriveSource("");
      setGdriveToken("");
      setDropboxSource("");
      setDropboxToken("");
      // Redirect to job status page after 2 seconds
      setTimeout(() => {
        router.push(`/jobs/${data.job_id}`);
      }, 2000);
    },
  });

  const handleFileUpload = () => {
    if (!selectedFile || !project) return;
    uploadMutation.mutate({
      file: selectedFile,
      name: customName || undefined,
      tags,
      ...toUploadLocation(project, folder),
    });
  };

  // A remembered project that has since disappeared answers 404: forget it.
  useEffect(() => {
    const error = uploadMutation.error;
    if (error instanceof ApiError && error.status === 404 && user) forgetLastProject(user.id);
  }, [uploadMutation.error, user]);

  const projectHint = !project ? (
    <p className="text-center text-xs text-muted-foreground">Choose or create a project</p>
  ) : null;

  const handleUrlConvert = () => {
    if (!urlSource) return;
    // URL conversion not yet implemented in API
    alert("URL conversion coming soon!");
  };

  const handleGdriveConvert = () => {
    if (!gdriveSource || !gdriveToken) return;
    // Google Drive conversion not yet implemented in API
    alert("Google Drive conversion coming soon!");
  };

  const handleDropboxConvert = () => {
    if (!dropboxSource || !dropboxToken) return;
    // Dropbox conversion not yet implemented in API
    alert("Dropbox conversion coming soon!");
  };

  if (!user) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-muted-foreground">Loading...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-background via-background to-muted">
      {/* Header */}
      <AppHeader />

      {/* Main Content */}
      <main className="container mx-auto px-4 py-12">
        <div className="max-w-3xl mx-auto space-y-8">
          {/* Conversion Card */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <FileText className="h-5 w-5" />
                <span>Convert Document</span>
              </CardTitle>
              <CardDescription>
                Choose your document source and convert it to Markdown format
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {uploadSuccess && (
                <div className="rounded-md bg-green-500/10 border border-green-500/20 p-4 text-sm text-green-600 dark:text-green-400">
                  <p className="font-medium">Conversion started!</p>
                  <p className="text-xs mt-1">Job ID: {uploadSuccess}</p>
                  <p className="text-xs mt-1">Redirecting to job status...</p>
                </div>
              )}

              {uploadMutation.isError && (
                <div
                  role="alert"
                  className="rounded-md bg-destructive/10 border border-destructive/20 p-4 text-sm text-destructive"
                >
                  <p className="font-medium">
                    {uploadMutation.error instanceof ApiError && uploadMutation.error.status === 422
                      ? "The upload was rejected"
                      : "Conversion failed"}
                  </p>
                  {/* The API's message can span lines (the "project required" one carries a curl example). */}
                  <p className="mt-1 whitespace-pre-line break-words text-xs">
                    {formatApiError(uploadMutation.error, "Please try again.")}
                  </p>
                </div>
              )}

              <UploadLocationFields
                projects={projects}
                project={project}
                folder={folder}
                onProjectChange={handleProjectChange}
                onFolderChange={setFolder}
                disabled={uploadMutation.isPending}
                loadError={projectsQuery.isError ? formatApiError(projectsQuery.error) : null}
              />

              <Tabs defaultValue="file" className="w-full">
                <TabsList className="grid w-full grid-cols-4">
                  <TabsTrigger value="file">
                    <UploadIcon className="h-4 w-4 mr-2" />
                    File
                  </TabsTrigger>
                  <TabsTrigger value="url">
                    <LinkIcon className="h-4 w-4 mr-2" />
                    URL
                  </TabsTrigger>
                  <TabsTrigger value="gdrive">
                    <Cloud className="h-4 w-4 mr-2" />
                    Google Drive
                  </TabsTrigger>
                  <TabsTrigger value="dropbox">
                    <Cloud className="h-4 w-4 mr-2" />
                    Dropbox
                  </TabsTrigger>
                </TabsList>

                {/* File Upload Tab */}
                <TabsContent value="file" className="space-y-4 mt-4">
                  <FileUpload
                    onFileSelect={setSelectedFile}
                    selectedFile={selectedFile}
                    onClear={() => setSelectedFile(null)}
                  />

                  <div className="space-y-2">
                    <Label htmlFor="customNameFile">Custom Name (Optional)</Label>
                    <Input
                      id="customNameFile"
                      type="text"
                      placeholder="e.g., Monthly Report 2025"
                      value={customName}
                      onChange={(e) => setCustomName(e.target.value)}
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="tagsFile">Tags (Optional)</Label>
                    <TagInput id="tagsFile" value={tags} onChange={setTags} />
                  </div>

                  <Button
                    onClick={handleFileUpload}
                    disabled={!selectedFile || !project || uploadMutation.isPending}
                    className="w-full"
                    size="lg"
                  >
                    {uploadMutation.isPending ? "Converting..." : "Convert to Markdown"}
                  </Button>
                  {projectHint}
                </TabsContent>

                {/* URL Tab */}
                <TabsContent value="url" className="space-y-4 mt-4">
                  <div className="space-y-2">
                    <Label htmlFor="urlSource">Document URL</Label>
                    <Input
                      id="urlSource"
                      type="url"
                      placeholder="https://example.com/document.pdf"
                      value={urlSource}
                      onChange={(e) => setUrlSource(e.target.value)}
                    />
                    <p className="text-xs text-muted-foreground">
                      Enter a public URL to a document (PDF, DOCX, etc.)
                    </p>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="customNameUrl">Custom Name (Optional)</Label>
                    <Input
                      id="customNameUrl"
                      type="text"
                      placeholder="e.g., Monthly Report 2025"
                      value={customName}
                      onChange={(e) => setCustomName(e.target.value)}
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="tagsUrl">Tags (Optional)</Label>
                    <TagInput id="tagsUrl" value={tags} onChange={setTags} />
                  </div>

                  <Button
                    onClick={handleUrlConvert}
                    disabled={!urlSource || !project || uploadMutation.isPending}
                    className="w-full"
                    size="lg"
                  >
                    {uploadMutation.isPending ? "Converting..." : "Convert from URL"}
                  </Button>
                  {projectHint}
                </TabsContent>

                {/* Google Drive Tab */}
                <TabsContent value="gdrive" className="space-y-4 mt-4">
                  <div className="space-y-2">
                    <Label htmlFor="gdriveSource">Google Drive File ID</Label>
                    <Input
                      id="gdriveSource"
                      type="text"
                      placeholder="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
                      value={gdriveSource}
                      onChange={(e) => setGdriveSource(e.target.value)}
                    />
                    <p className="text-xs text-muted-foreground">
                      The file ID from your Google Drive URL
                    </p>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="gdriveToken">OAuth2 Token</Label>
                    <Input
                      id="gdriveToken"
                      type="password"
                      placeholder="ya29.a0AfH6SMB..."
                      value={gdriveToken}
                      onChange={(e) => setGdriveToken(e.target.value)}
                    />
                    <p className="text-xs text-muted-foreground">
                      Your Google OAuth2 access token
                    </p>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="customNameGdrive">Custom Name (Optional)</Label>
                    <Input
                      id="customNameGdrive"
                      type="text"
                      placeholder="e.g., Monthly Report 2025"
                      value={customName}
                      onChange={(e) => setCustomName(e.target.value)}
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="tagsGdrive">Tags (Optional)</Label>
                    <TagInput id="tagsGdrive" value={tags} onChange={setTags} />
                  </div>

                  <Button
                    onClick={handleGdriveConvert}
                    disabled={!gdriveSource || !gdriveToken || !project || uploadMutation.isPending}
                    className="w-full"
                    size="lg"
                  >
                    {uploadMutation.isPending ? "Converting..." : "Convert from Google Drive"}
                  </Button>
                  {projectHint}
                </TabsContent>

                {/* Dropbox Tab */}
                <TabsContent value="dropbox" className="space-y-4 mt-4">
                  <div className="space-y-2">
                    <Label htmlFor="dropboxSource">Dropbox File Path</Label>
                    <Input
                      id="dropboxSource"
                      type="text"
                      placeholder="/documents/report.pdf"
                      value={dropboxSource}
                      onChange={(e) => setDropboxSource(e.target.value)}
                    />
                    <p className="text-xs text-muted-foreground">
                      The path to your file in Dropbox
                    </p>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="dropboxToken">Access Token</Label>
                    <Input
                      id="dropboxToken"
                      type="password"
                      placeholder="sl.B1a2c3..."
                      value={dropboxToken}
                      onChange={(e) => setDropboxToken(e.target.value)}
                    />
                    <p className="text-xs text-muted-foreground">
                      Your Dropbox access token
                    </p>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="customNameDropbox">Custom Name (Optional)</Label>
                    <Input
                      id="customNameDropbox"
                      type="text"
                      placeholder="e.g., Monthly Report 2025"
                      value={customName}
                      onChange={(e) => setCustomName(e.target.value)}
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="tagsDropbox">Tags (Optional)</Label>
                    <TagInput id="tagsDropbox" value={tags} onChange={setTags} />
                  </div>

                  <Button
                    onClick={handleDropboxConvert}
                    disabled={!dropboxSource || !dropboxToken || !project || uploadMutation.isPending}
                    className="w-full"
                    size="lg"
                  >
                    {uploadMutation.isPending ? "Converting..." : "Convert from Dropbox"}
                  </Button>
                  {projectHint}
                </TabsContent>
              </Tabs>
            </CardContent>
          </Card>

          {/* Info Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Supported Formats</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="text-sm space-y-2 text-muted-foreground">
                  <li>• PDF Documents</li>
                  <li>• Microsoft Word (DOCX, DOC)</li>
                  <li>• HTML Files</li>
                  <li>• PowerPoint (PPTX)</li>
                  <li>• Excel (XLSX)</li>
                  <li>• Rich Text Format (RTF)</li>
                  <li>• OpenDocument Text (ODT)</li>
                </ul>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-lg">How It Works</CardTitle>
              </CardHeader>
              <CardContent>
                <ol className="text-sm space-y-2 text-muted-foreground">
                  <li>1. Upload your document</li>
                  <li>2. Processing starts automatically</li>
                  <li>3. Track progress in real-time</li>
                  <li>4. Download Markdown output</li>
                  <li>5. Search and manage your jobs</li>
                </ol>
              </CardContent>
            </Card>
          </div>
        </div>
      </main>
    </div>
  );
}
