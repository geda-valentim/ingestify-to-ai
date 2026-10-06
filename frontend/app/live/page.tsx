"use client";

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

export default function LivePage() {
  const user = useAuthStore((s) => s.user);
  const hydrated = useAuthStore((s) => s._hasHydrated);
  const router = useRouter();
  const projects = useProjects();
  const capture = useLiveCapture();
  const [project, setProject] = useState<LocationChoice | null>(null);
  const [folder, setFolder] = useState<LocationChoice | null>(null);
  const [diarize, setDiarize] = useState(false);
  const [name, setName] = useState("Transcrição ao vivo");
  const busy = ["starting", "listening", "finishing"].includes(capture.state);
  useEffect(() => { if (hydrated && !user) router.replace(loginUrl()); }, [hydrated, user, router]);
  if (!hydrated || !user) return null;
  return <div className="min-h-screen bg-background">
    <AppHeader />
    <main className="container mx-auto max-w-4xl p-4 space-y-6">
      <div><h1 className="text-2xl font-bold">Transcrever ao vivo</h1>
        <p className="text-muted-foreground">Legendas em português pelo microfone. Finalize para guardar o texto no seu projeto.</p></div>
      <div className="space-y-4 border rounded-lg p-4">
        <div><Label htmlFor="live-name">Nome</Label><Input id="live-name" value={name} onChange={(e) => setName(e.target.value)} disabled={busy} maxLength={1000} /></div>
        <UploadLocationFields projects={projects.data?.projects ?? []} project={project} folder={folder}
          onProjectChange={(value) => { setProject(value); setFolder(null); }} onFolderChange={setFolder}
          disabled={busy} loadError={projects.isError ? "Tente novamente ou informe um nome." : null} />
        <p className="text-sm">Idioma: Português · O áudio não é armazenado.</p>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={diarize} disabled={busy} onChange={(e) => setDiarize(e.target.checked)} />Identificar falantes durante a captura</label>
        <div className="flex gap-3 flex-wrap">
          {!busy && <Button disabled={!project || !name.trim()} onClick={() => capture.start({
            ...(project?.id ? { project_id: project.id } : { project: project?.name }),
            ...(folder?.id ? { folder_id: folder.id } : folder ? { folder: folder.name } : {}),
          }, name.trim(), diarize)}>Iniciar microfone</Button>}
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
          preloaded={capture.segments.length} immediate partial={capture.partial} diarization={capture.diarization} />
      </div>}
    </main>
  </div>;
}
