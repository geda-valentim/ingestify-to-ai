"use client";

import { Suspense, useState, useEffect, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Upload as UploadIcon, Link as LinkIcon, Cloud } from "lucide-react";
import { useAuthStore } from "@/lib/store/auth";
import { loginUrl } from "@/lib/session";
import { ApiError, jobsApi, uploadSourceType } from "@/lib/api";
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
import { DocumentOptionsFields } from "@/components/upload/document-options";
import { ModelOptions } from "@/components/upload/model-options";
import { ImageRegionPicker } from "@/components/upload/image-region-picker";
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
import type { CaptionTask, VisionTask, UploadLocation, UploadRequest } from "@/types/api";
import type { DocumentOptions, ConvertRequest, AudioConversionOptions, TranscriptFormat } from "@/types/api";
import type { DatalakeDestination } from "@/types/datalake";
import { DatalakeDestinationFields } from "@/components/datalake/destination-fields";
import { datalakeApi } from "@/lib/datalake-api";

type ImportRequest = UploadLocation & { docling_preset?: string; conversion_options?: DocumentOptions; audio_options?: AudioConversionOptions; connection_id: string; bucket: string; key: string; name?: string; tags?: string[]; datalake?: DatalakeDestination };

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
  const [sourceTab, setSourceTab] = useState("file");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [imageEngine, setImageEngine] = useState<"vision" | "docling">("vision");
  const [externalProcessing, setExternalProcessing] = useState<"document" | "audio">("document");
  const [lakeKey, setLakeKey] = useState("");
  const [imageOperation, setImageOperation] = useState<"describe" | "ocr" | "analyze" | "full">("describe");
  const [imageTask, setImageTask] = useState<CaptionTask | "">("");
  const [analysisTask, setAnalysisTask] = useState<VisionTask>("<OD>");
  const [imageTextInput, setImageTextInput] = useState("");
  const [fullQueries, setFullQueries] = useState("");
  const [imageRegion, setImageRegion] = useState<number[] | null>(null);
  const [imageGeneration, setImageGeneration] = useState<Record<string, unknown>>({});
  const isImageFile = sourceTab === "file" && !!selectedFile && uploadSourceType(selectedFile.name) === "image";
  const isImage = isImageFile && imageEngine === "vision";
  const isAudio = (sourceTab === "file" && !!selectedFile && uploadSourceType(selectedFile.name) === "audio") ||
    (sourceTab === "datalake" && uploadSourceType(lakeKey) === "audio") ||
    (["url", "gdrive", "dropbox"].includes(sourceTab) && externalProcessing === "audio");
  const [documentPreset, setDocumentPreset] = useState("fast");
  const [documentOptions, setDocumentOptions] = useState<DocumentOptions>({});
  const [documentOptionsValid, setDocumentOptionsValid] = useState(true);
  const isDocument = !isImage && !isAudio;
  const documentCapabilities = useQuery({ queryKey: ["document-capabilities", token], queryFn: jobsApi.documentCapabilities,
    enabled: !!token && (isDocument || isImageFile), staleTime: 30_000 });
  const documentImageSupported = !!selectedFile && documentCapabilities.data?.image_extensions?.includes(selectedFile.name.split(".").pop()!.toLowerCase());
  const documentRequest = { docling_preset: documentPreset, conversion_options: documentOptions };
  const [audioOptions, setAudioOptions] = useState<Record<string, unknown>>({});
  const [audioOperation, setAudioOperation] = useState<"transcribe" | "detect_language" | "inspect">("transcribe");
  const [audioOptionsValid, setAudioOptionsValid] = useState(true);
  const [audioWords, setAudioWords] = useState(false);
  const [audioTimestamps, setAudioTimestamps] = useState(true);
  const [audioFormat, setAudioFormat] = useState("markdown");
  const [purgeAudio, setPurgeAudio] = useState(false);
  const audioRequest = { audio_options: { operation: audioOperation, decoding: audioOperation === "inspect" ? {} : audioOptions,
    include_timestamps: audioTimestamps, include_word_timestamps: audioOperation === "transcribe" && audioWords,
    output_format: audioFormat as TranscriptFormat, purge_source: purgeAudio } };
  const sourceRequest = isAudio ? audioRequest : documentRequest;
  const audioCapabilities = useQuery({ queryKey: ["audio-capabilities", token], queryFn: jobsApi.audioCapabilities,
    enabled: !!token && isAudio, staleTime: 30_000 });
  const audioUnavailable = isAudio && (audioCapabilities.isPending || audioCapabilities.isError || !audioCapabilities.data?.enabled);
  const imageCapabilities = useQuery({
    queryKey: ["image-capabilities", token], queryFn: jobsApi.imageCapabilities,
    enabled: !!token && isImage, staleTime: 30_000,
  });
  const imageSizeError = isImage && imageCapabilities.data && selectedFile!.size > imageCapabilities.data.max_image_size_mb * 1024 * 1024;
  const imageUnavailable = isImage && (imageCapabilities.isPending || imageCapabilities.isError || !imageCapabilities.data?.enabled || !imageCapabilities.data?.dependencies_installed || !imageCapabilities.data?.model_downloaded);
  const analysisTaskInfo = imageCapabilities.data?.tasks?.find((item) => item.task === analysisTask);
  const fullQueryValues = fullQueries.split("\n").map(query => query.trim()).filter(Boolean);
  const fullInputError = isImage && imageOperation === "full" && (fullQueryValues.length > 3 || fullQueryValues.join(". ").length > 2000);
  const imageInputError = fullInputError || (isImage && imageOperation === "analyze" && (
    !analysisTaskInfo || (analysisTaskInfo.input === "text" && !imageTextInput.trim()) ||
    (analysisTaskInfo.input === "region" && (!imageRegion || imageRegion[0] >= imageRegion[2] || imageRegion[1] >= imageRegion[3]))));
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
  const [destination, setDestination] = useState<DatalakeDestination | null>(null);
  const [lakeSource, setLakeSource] = useState<DatalakeDestination | null>(null);
  const sourceObjects = useQuery({ queryKey: ["datalake-objects", token, lakeSource],
    queryFn: () => datalakeApi.objects(lakeSource!.connection_id, lakeSource!.bucket, lakeSource!.prefix),
    enabled: !!token && !!lakeSource?.bucket });
  const [partitionValid, setPartitionValid] = useState(true);
  const validDestination = (isImage && imageOperation !== "full") || !destination || (!!destination.bucket.trim() && partitionValid);

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

  const fullSubmission = useRef<{ file: File; signature: string; key: string } | null>(null);
  const uploadMutation = useMutation({
    mutationFn: (request: UploadRequest | ConvertRequest | ImportRequest) => "connection_id" in request ? datalakeApi.import(request) : "source_type" in request ? jobsApi.convert(request) : jobsApi.upload(request),
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
      fullSubmission.current = null;
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
    if (!selectedFile || !project || !validDestination || imageSizeError || imageUnavailable || imageInputError || audioUnavailable || (isAudio && !audioOptionsValid) || (isDocument && !documentOptionsValid)) return;
    const request: UploadRequest = {
      file: selectedFile,
      ...(isDocument ? documentRequest : {}),
      ...(isImageFile ? { image_engine: imageEngine } : {}),
      name: isImage ? undefined : customName || undefined,
      tags,
      ...(isAudio ? { audio_decoding: audioOperation === "inspect" ? {} : audioOptions, audio_operation: audioOperation, include_timestamps: audioTimestamps, include_word_timestamps: audioOperation === "transcribe" && audioWords, output_format: audioFormat, purge_source: purgeAudio } : {}),
      ...toUploadLocation(project, folder),
      ...(isImage ? { image_operation: imageOperation,
        image_task: imageOperation === "analyze" ? analysisTask : imageOperation === "ocr" ? "<OCR_WITH_REGION>" : imageTask || imageCapabilities.data?.default_caption_task,
        image_text_input: imageOperation === "analyze" && analysisTaskInfo?.input === "text" ? imageTextInput.trim() : undefined,
        image_region: imageOperation === "analyze" && analysisTaskInfo?.input === "region" ? imageRegion ?? undefined : undefined,
        image_generation: imageGeneration,
        ...(imageOperation === "full" && destination ? { datalake: destination } : {}),
        image_full_options: imageOperation === "full" ? {
          ...(fullQueries.trim() ? { queries: fullQueries.split("\n").map(q => q.trim()).filter(Boolean) } : {}),
          ...(imageRegion ? { regions: [imageRegion] } : {}),
        } : undefined,
      } : destination ? { datalake: destination } : {}),
    };
    if (isImage && imageOperation === "full") {
      const signature = JSON.stringify({ ...request, file: undefined });
      if (!fullSubmission.current || fullSubmission.current.file !== selectedFile || fullSubmission.current.signature !== signature) {
        fullSubmission.current = { file: selectedFile, signature, key: crypto.randomUUID() };
      }
      request.image_idempotency_key = fullSubmission.current.key;
    }
    uploadMutation.mutate(request);
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
    if (!urlSource || !project || !validDestination || (isAudio ? audioUnavailable || !audioOptionsValid : !documentOptionsValid)) return;
    uploadMutation.mutate({ ...sourceRequest, source_type: "url", source: urlSource, name: customName || undefined, tags,
      ...toUploadLocation(project, folder), ...(destination ? { datalake: destination } : {}) });
  };

  const handleGdriveConvert = () => {
    if (!gdriveSource || !gdriveToken || !project || !validDestination || (isAudio ? audioUnavailable || !audioOptionsValid : !documentOptionsValid)) return;
    uploadMutation.mutate({ ...sourceRequest, source_type: "gdrive", source: gdriveSource, authToken: gdriveToken, name: customName || undefined, tags,
      ...toUploadLocation(project, folder), ...(destination ? { datalake: destination } : {}) });
  };

  const handleDropboxConvert = () => {
    if (!dropboxSource || !dropboxToken || !project || !validDestination || (isAudio ? audioUnavailable || !audioOptionsValid : !documentOptionsValid)) return;
    uploadMutation.mutate({ ...sourceRequest, source_type: "dropbox", source: dropboxSource, authToken: dropboxToken, name: customName || undefined, tags,
      ...toUploadLocation(project, folder), ...(destination ? { datalake: destination } : {}) });
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

              {["url", "gdrive", "dropbox"].includes(sourceTab) && <div className="space-y-2"><Label htmlFor="external-processing">Tipo de processamento</Label><select id="external-processing" value={externalProcessing} disabled={uploadMutation.isPending} onChange={(event) => setExternalProcessing(event.target.value as typeof externalProcessing)} className="h-10 w-full rounded border bg-background px-3"><option value="document">Documento · Docling</option><option value="audio">Áudio ou vídeo · Whisper</option></select></div>}
                  {isAudio && <div className="space-y-3 rounded-lg border p-4">
                    <p className="text-sm font-medium">Áudio: {audioCapabilities.data?.provider ?? "Verificando…"} · {audioCapabilities.data?.model}</p>
                    {audioCapabilities.data?.execution_reason && <p role="status" className="text-sm text-muted-foreground">{audioCapabilities.data.execution_reason}</p>}
                    {audioCapabilities.data && <>
                      <div><Label htmlFor="audio-operation">Operação de áudio</Label><select id="audio-operation" value={audioOperation} onChange={(e) => { setAudioOperation(e.target.value as typeof audioOperation); setAudioOptions({}); setAudioOptionsValid(true); }} className="h-10 w-full rounded border bg-background px-3">{audioCapabilities.data.operations.map((operation) => <option key={operation} value={operation}>{{ transcribe: "Transcrever ou traduzir", detect_language: "Detectar idioma", inspect: "Metadados do arquivo" }[operation]}</option>)}</select></div>
                      {audioOperation !== "inspect" && <ModelOptions schema={{ ...audioCapabilities.data.parameters_schema, properties: Object.fromEntries(Object.entries(audioCapabilities.data.parameters_schema.properties ?? {}).filter(([name]) => audioOperation === "transcribe" || !["language", "task"].includes(name))) }} value={audioOptions} onChange={setAudioOptions} onValid={setAudioOptionsValid} disabled={uploadMutation.isPending} />}
                      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={audioTimestamps} onChange={(e) => setAudioTimestamps(e.target.checked)} />Marcas de tempo no Markdown</label>
                      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={audioWords} onChange={(e) => setAudioWords(e.target.checked)} />Timestamps de palavras</label>
                      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={purgeAudio} onChange={(e) => setPurgeAudio(e.target.checked)} />Apagar arquivo original após concluir</label>
                      <div><Label htmlFor="audio-format">Formato padrão do resultado</Label><select id="audio-format" value={audioFormat} onChange={(e) => setAudioFormat(e.target.value)} className="h-10 w-full rounded border bg-background px-3">{audioCapabilities.data.formats.map((format) => <option key={format} value={format}>{format.toUpperCase()}</option>)}</select></div>
                      {audioCapabilities.data.restrictions.map((restriction) => <p key={restriction} className="text-xs text-muted-foreground">{restriction}</p>)}
                    </>}
                    {audioUnavailable && !audioCapabilities.isPending && <p role="alert" className="text-sm text-destructive">Transcrição indisponível.</p>}
                  </div>}
              {isDocument && documentCapabilities.data && <DocumentOptionsFields capabilities={documentCapabilities.data} preset={documentPreset} onPreset={setDocumentPreset} value={documentOptions} onChange={setDocumentOptions} disabled={uploadMutation.isPending} onValid={setDocumentOptionsValid} />}

              <Tabs value={sourceTab} onValueChange={setSourceTab} className="w-full">
                {(!isImage || imageOperation === "full") && <DatalakeDestinationFields value={destination} onChange={setDestination} disabled={uploadMutation.isPending} context={{ project_id: project?.id ?? (project ? "novo-projeto" : null), folder_id: folder?.id ?? (folder ? "nova-pasta" : null), source_type: sourceTab === "file" && selectedFile ? uploadSourceType(selectedFile.name) : sourceTab }} onValid={setPartitionValid} />}
                <TabsList className="mt-4 flex h-auto w-full flex-wrap gap-1">
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
                  <TabsTrigger value="datalake"><Cloud className="mr-2 h-4 w-4" />Datalake</TabsTrigger>
                </TabsList>

                <TabsContent value="datalake" className="mt-4 space-y-4">
                  <DatalakeDestinationFields source value={lakeSource} onChange={(value) => { setLakeSource(value); setLakeKey(""); }} disabled={uploadMutation.isPending} />
                  <div className="space-y-2"><Label htmlFor="datalake-source-key">Arquivo no bucket</Label>
                    <Input id="datalake-source-key" list="datalake-source-objects" value={lakeKey} onChange={(e) => setLakeKey(e.target.value)} placeholder="documentos/relatorio.pdf" />
                    <datalist id="datalake-source-objects">{sourceObjects.data?.objects.map((o) => <option key={o.key} value={o.key} />)}</datalist>
                    <p className="text-xs text-muted-foreground">Informe o caminho completo do arquivo ou escolha uma sugestão. Filtre a pasta de origem para encontrar outros arquivos.</p>
                    {sourceObjects.isError && <p className="text-xs text-muted-foreground">Não foi possível listar os arquivos. Você pode informar o caminho diretamente.</p>}
                  </div>
                  <div><Label htmlFor="datalake-import-name">Nome personalizado (opcional)</Label><Input id="datalake-import-name" value={customName} onChange={(e) => setCustomName(e.target.value)} /></div>
                  <Button className="w-full" disabled={!lakeSource?.bucket || !lakeKey || !project || !validDestination || (isAudio ? !!audioUnavailable || !audioOptionsValid : !documentOptionsValid) || uploadMutation.isPending} onClick={() => {
                    if (!lakeSource || !project) return;
                    uploadMutation.mutate({ ...sourceRequest, connection_id: lakeSource.connection_id, bucket: lakeSource.bucket, key: lakeKey,
                      name: customName || undefined, tags, ...toUploadLocation(project, folder), ...(destination ? { datalake: destination } : {}) });
                  }}>{uploadMutation.isPending ? "Processando…" : "Processar arquivo do bucket"}</Button>
                  {projectHint}
                </TabsContent>

                {/* File Upload Tab */}
                <TabsContent value="file" className="space-y-4 mt-4">
                  <FileUpload
                    onFileSelect={(file) => { setSelectedFile(file); setImageRegion(null); setImageEngine("vision");  }}
                    selectedFile={selectedFile}
                    onClear={() => setSelectedFile(null)}
                  />

                  {isImageFile && <div className="space-y-2"><Label htmlFor="image-engine">Modelo para a imagem</Label>
                    <select id="image-engine" value={imageEngine} disabled={uploadMutation.isPending} onChange={(event) => {
                      const engine = event.target.value as typeof imageEngine; setImageEngine(engine);
                      if (engine === "docling") setDocumentPreset("quality");
                    }} className="h-10 w-full rounded border bg-background px-3 text-sm">
                      <option value="vision">Florence-2 · descrição, OCR e análise visual</option>
                      <option value="docling" disabled={!documentImageSupported}>Docling · OCR, estrutura e exportações de documento</option>
                    </select>
                    {!documentImageSupported && <p className="text-xs text-muted-foreground">Docling aceita os formatos informados em seu catálogo; GIF utiliza Florence-2.</p>}
                  </div>}

                  {isImage && (
                    <div className="space-y-3 rounded-lg border p-4">
                      <div className="space-y-2">
                        <Label htmlFor="image-operation">Processamento da imagem</Label>
                        <select id="image-operation" value={imageOperation} onChange={(e) => setImageOperation(e.target.value as "describe" | "ocr" | "analyze" | "full")} disabled={uploadMutation.isPending} className="h-10 w-full rounded-md border bg-background px-3 text-sm">
                          <option value="describe">Descrever imagem</option>
                          <option value="ocr">Extrair texto (OCR com regiões)</option>
                          <option value="analyze">Detecção, segmentação e outras análises</option>
                          <option value="full">Full Analysis · todas as capacidades de visão</option>
                        </select>
                      </div>
                      {imageOperation === "describe" && imageCapabilities.data && (
                        <div className="space-y-2">
                          <Label htmlFor="image-task">Detalhamento da descrição</Label>
                          <select id="image-task" value={imageTask || imageCapabilities.data.default_caption_task} onChange={(e) => setImageTask(e.target.value as CaptionTask)} disabled={uploadMutation.isPending} className="h-10 w-full rounded-md border bg-background px-3 text-sm">
                            {imageCapabilities.data.caption_tasks.map((task) => <option key={task} value={task}>{{ "<CAPTION>": "Breve", "<DETAILED_CAPTION>": "Detalhada", "<MORE_DETAILED_CAPTION>": "Muito detalhada" }[task]}</option>)}
                          </select>
                        </div>
                      )}
                      {imageOperation === "analyze" && <div className="space-y-3">
                        <div className="space-y-2"><Label htmlFor="analysis-task">Tarefa de visão</Label>
                          <select id="analysis-task" value={analysisTask} onChange={(e) => setAnalysisTask(e.target.value as VisionTask)} disabled={uploadMutation.isPending} className="h-10 w-full rounded-md border bg-background px-3 text-sm">
                            {imageCapabilities.data?.tasks?.map((item) => <option key={item.task} value={item.task}>{item.label}</option>)}
                          </select>
                        </div>
                        {analysisTaskInfo?.input === "text" && <div className="space-y-2"><Label htmlFor="image-text-input">Texto para localizar na imagem</Label>
                          <Input id="image-text-input" value={imageTextInput} onChange={(e) => setImageTextInput(e.target.value)} maxLength={2000} disabled={uploadMutation.isPending} placeholder="Ex.: um carro vermelho, uma pessoa ao lado da porta" />
                          <p className="text-xs text-muted-foreground">Descreva o objeto, a expressão ou a frase que a tarefa deve localizar.</p>
                        </div>}
                        {analysisTaskInfo?.input === "region" && selectedFile && <ImageRegionPicker file={selectedFile} region={imageRegion} onChange={setImageRegion} disabled={uploadMutation.isPending} />}
                        {imageInputError && <p className="text-xs text-muted-foreground">Preencha a entrada exigida pela tarefa escolhida.</p>}
                      </div>}
                      {imageOperation === "full" && <div className="space-y-3 rounded border p-3">
                        <p className="text-sm">Descrições, texto, objetos, regiões e segmentações em uma execução. A imagem basta: consultas e regiões são selecionadas automaticamente.</p>
                        <p className="text-xs text-muted-foreground">15 tarefas de visão; até 3 consultas, 4 regiões e 32 chamadas. Pode demorar mais. O resultado mostra cobertura e limites.</p>
                        <details className="space-y-3"><summary className="cursor-pointer text-sm font-medium">Consultas e região de interesse (opcional)</summary>
                          <label htmlFor="full-queries" className="text-sm">Objetos ou expressões, uma por linha (até 3)</label>
                          <textarea id="full-queries" value={fullQueries} onChange={event => { setFullQueries(event.target.value);  }} className="w-full rounded border bg-background p-2" maxLength={2000} placeholder="a red car" />
                          {fullInputError && <p role="alert" className="text-xs text-destructive">Use até três consultas, com no máximo 2000 caracteres no total.</p>}
                          {selectedFile && <ImageRegionPicker file={selectedFile} region={imageRegion} onChange={region => { setImageRegion(region);  }} disabled={uploadMutation.isPending} />}
                          <button type="button" className="text-xs underline" onClick={() => { setFullQueries(""); setImageRegion(null);  }}>Usar seleção automática</button>
                        </details>
                      </div>}
                      {imageCapabilities.data?.generation_schema && <details className="space-y-3 rounded border p-3">
                        <summary className="cursor-pointer text-sm font-medium">Opções de geração</summary>
                        <ModelOptions schema={imageCapabilities.data.generation_schema} defaults={imageCapabilities.data.generation_defaults} value={imageGeneration} onChange={value => { setImageGeneration(value);  }} disabled={uploadMutation.isPending} />
                        <button type="button" className="text-xs underline" onClick={() => setImageGeneration({})}>Restaurar padrões do serviço</button>
                      </details>}
                      <p className="text-xs text-muted-foreground">{imageCapabilities.data ? `Limite: ${imageCapabilities.data.max_image_size_mb} MB. ` : "Verificando disponibilidade… "}O nome do arquivo identifica o job. Imagens são salvas no projeto; Full Analysis também permite exportação para datalake quando um destino é selecionado.</p>
                      {imageSizeError && <p role="alert" className="text-sm text-destructive">A imagem excede o limite de tamanho.</p>}
                      {imageUnavailable && !imageCapabilities.isPending && <p role="alert" className="text-sm text-destructive">Processamento de imagens indisponível. {imageCapabilities.data?.reason || formatApiError(imageCapabilities.error, "Verifique a disponibilidade do serviço.")}</p>}
                    </div>
                  )}



                  {!isImage && <div className="space-y-2">
                    <Label htmlFor="customNameFile">Custom Name (Optional)</Label>
                    <Input
                      id="customNameFile"
                      type="text"
                      placeholder="e.g., Monthly Report 2025"
                      value={customName}
                      onChange={(e) => setCustomName(e.target.value)}
                    />
                  </div>}

                  <div className="space-y-2">
                    <Label htmlFor="tagsFile">Tags (Optional)</Label>
                    <TagInput id="tagsFile" value={tags} onChange={setTags} />
                  </div>

                  <Button
                    onClick={handleFileUpload}
                    disabled={!selectedFile || !project || !validDestination || !!imageSizeError || !!imageUnavailable || !!imageInputError || !!audioUnavailable || (isAudio && !audioOptionsValid) || (isDocument && !documentOptionsValid) || uploadMutation.isPending}
                    className="w-full"
                    size="lg"
                  >
                    {uploadMutation.isPending ? "Processando..." : "Processar arquivo"}
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
                    disabled={!urlSource || !project || !validDestination || (isAudio ? !!audioUnavailable || !audioOptionsValid : !documentOptionsValid) || uploadMutation.isPending}
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
                    disabled={!gdriveSource || !gdriveToken || !project || !validDestination || (isAudio ? !!audioUnavailable || !audioOptionsValid : !documentOptionsValid) || uploadMutation.isPending}
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
                    disabled={!dropboxSource || !dropboxToken || !project || !validDestination || (isAudio ? !!audioUnavailable || !audioOptionsValid : !documentOptionsValid) || uploadMutation.isPending}
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
                  <li>• Imagens (PNG, JPEG, WEBP, BMP, GIF, TIFF)</li>
                  <li>• Áudio e vídeo (MP3, WAV, MP4, M4A, WebM)</li>
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
                  <li>1. Upload your file</li>
                  <li>2. Choose the available processing options</li>
                  <li>3. Track progress in real-time</li>
                  <li>4. View and download the result</li>
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
