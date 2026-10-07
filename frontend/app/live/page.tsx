"use client";

import { useQuery } from "@tanstack/react-query";
import { liveApi } from "@/lib/api";
import { ModelOptions } from "@/components/upload/model-options";
import type { LiveOptions } from "@/types/live";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AppHeader } from "@/components/app-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { UploadLocationFields } from "@/components/projects/upload-location-fields";
import type { LocationChoice } from "@/components/projects/location-combobox";
import { useProjects } from "@/components/projects/use-projects";
import { LiveTranscriptView } from "@/components/job/live-transcript";
import { useLiveCapture } from "@/hooks/use-live-capture";
import { useAuthStore } from "@/lib/store/auth";
import { loginUrl } from "@/lib/session";
import { DatalakeDestinationFields } from "@/components/datalake/destination-fields";
import type { DatalakeDestination } from "@/types/datalake";

export default function LivePage() {
  const user = useAuthStore((s) => s.user);
  const hydrated = useAuthStore((s) => s._hasHydrated);
  const router = useRouter();
  const projects = useProjects();
  const capture = useLiveCapture();
  const token = useAuthStore(s => s.token);
  const capabilities = useQuery({ queryKey: ["live-capabilities", token], queryFn: liveApi.capabilities, enabled: !!user && !!token, refetchInterval: 30000 });
  const [language, setLanguage] = useState("pt");
  const [options, setOptions] = useState<LiveOptions>({});
  const [optionsValid, setOptionsValid] = useState(true);
  const [optionsOpen, setOptionsOpen] = useState(false);
  const [project, setProject] = useState<LocationChoice | null>(null);
  const [folder, setFolder] = useState<LocationChoice | null>(null);
  const [name, setName] = useState("Transcrição ao vivo");
  const [partitionValid, setPartitionValid] = useState(true);
  const [destination, setDestination] = useState<DatalakeDestination | null>(null);
  const busy = ["starting", "listening", "finishing"].includes(capture.state);
  useEffect(() => { if (hydrated && !user) router.replace(loginUrl()); }, [hydrated, user, router]);
  if (!hydrated || !user) return null;
  return <div className="min-h-screen bg-background">
    <AppHeader />
    <main className="container mx-auto max-w-4xl p-4 space-y-6">
      <div><h1 className="text-2xl font-bold">Transcrever ao vivo</h1>
        <p className="text-muted-foreground">Transcreva pelo microfone no idioma da conversa. Finalize para guardar o texto no seu projeto.</p></div>
      <div className="space-y-4 border rounded-lg p-4">
        <div><Label htmlFor="live-name">Nome</Label><Input id="live-name" value={name} onChange={(e) => setName(e.target.value)} disabled={busy} maxLength={1000} /></div>
        <UploadLocationFields projects={projects.data?.projects ?? []} project={project} folder={folder}
          onProjectChange={(value) => { setProject(value); setFolder(null); }} onFolderChange={setFolder}
          disabled={busy} loadError={projects.isError ? "Tente novamente ou informe um nome." : null} />
        <div><Label htmlFor="live-language">Idioma da conversa</Label><select id="live-language" value={language} onChange={event => setLanguage(event.target.value)} disabled={busy || !capabilities.data?.languages.length} className="h-10 w-full rounded-md border bg-background px-3 text-sm">
          {!capabilities.data?.languages.includes(language) && <option value={language}>{language} — indisponível</option>}
          {capabilities.data?.languages.map(code => <option key={code} value={code}>{new Intl.DisplayNames(["pt"], { type: "language" }).of(code) ?? code} ({code})</option>)}
        </select></div>
        {capabilities.isError && <p role="alert" className="text-sm text-destructive">Não foi possível verificar os modelos. <button className="underline" onClick={() => capabilities.refetch()}>Tentar novamente</button></p>}
        {capabilities.data && !capabilities.data.ready && <p role="status" className="text-sm text-muted-foreground">O worker ao vivo está indisponível. A disponibilidade é verificada automaticamente.</p>}
        {capabilities.data?.options_supported && <div className="space-y-4 rounded-lg border p-4"><button type="button" aria-expanded={optionsOpen} aria-controls="live-model-controls" onClick={() => setOptionsOpen(open => !open)} className="text-left text-sm font-medium">Controles do modelo · {capabilities.data.model}</button>
          {optionsOpen && <div id="live-model-controls" className="space-y-4">
          <ModelOptions schema={capabilities.data.options_schema} value={options as Record<string, unknown>} onChange={setOptions} disabled={busy} onValid={setOptionsValid} />
          <p className="text-xs text-muted-foreground">Prompts, vocabulário, decodificação e VAD são aplicados a esta sessão. Janelas maiores ou mais beams aumentam a latência. Timestamps e contexto confirmado são geridos pelo protocolo.</p>
          </div>}
        </div>}
        <p className="text-sm text-muted-foreground">O áudio não é armazenado. {capabilities.data && `Duração máxima: ${Math.floor(capabilities.data.max_duration_seconds / 60)} minutos.`}</p>
        <DatalakeDestinationFields value={destination} onChange={setDestination} disabled={busy} context={{ project_id: project?.id ?? (project ? "novo-projeto" : null), folder_id: folder?.id ?? (folder ? "nova-pasta" : null), source_type: "live" }} onValid={setPartitionValid} />
        <div className="flex gap-3 flex-wrap">
          {!busy && <Button disabled={!capabilities.data?.ready || !capabilities.data.languages.includes(language) || !optionsValid || !project || !name.trim() || (!!destination && (!destination.bucket.trim() || !partitionValid))} onClick={() => capture.start({
            ...(project?.id ? { project_id: project.id } : { project: project?.name }),
            ...(folder?.id ? { folder_id: folder.id } : folder ? { folder: folder.name } : {}),
            ...(destination ? { datalake: destination } : {}),
          }, name.trim(), { language, options: capabilities.data?.options_supported ? options : {} })}>Iniciar microfone</Button>}
          {capture.state === "listening" && <Button onClick={() => void capture.finish()}>Finalizar</Button>}
          {busy && <Button variant="outline" onClick={() => void capture.cancel()}>Cancelar</Button>}
          <span role="status" className="self-center text-sm text-muted-foreground">{{idle: "Pronto para iniciar", starting: "Conectando e verificando disponibilidade…", listening: "Ouvindo", finishing: "Finalizando e salvando…", completed: "Transcrição salva", interrupted: "Sessão interrompida", cancelled: "Sessão cancelada"}[capture.state]}</span>
        </div>
        {capture.error && <p role="alert" className="text-destructive">{capture.error}</p>}
        {capture.state === "completed" && capture.jobId && <Button asChild><Link href={`/jobs/${capture.jobId}`}>Ver resultado e baixar legendas</Link></Button>}
      </div>
      {(busy || capture.segments.length > 0) && <div className="h-[50vh] border rounded-lg overflow-hidden flex">
        <LiveTranscriptView status={{job_id: capture.jobId ?? "", type: "main", status: "processing", progress: 0,
          created_at: "", transcribed_seconds: capture.duration}} segments={capture.segments}
          preloaded={capture.segments.length} immediate partial={capture.partial} />
      </div>}
    </main>
  </div>;
}
