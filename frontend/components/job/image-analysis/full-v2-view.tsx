"use client";
import { useState } from "react";
import type { ImageFullAnalysisResult, VisionTask } from "@/types/api";
import type { ImageFullV2Result } from "@/types/faces";
import { Button } from "@/components/ui/button";
import { downloadText } from "@/lib/utils";
import { AnalysisStatus } from "./analysis-status";
import { faceMarkdown } from "./face-markdown";
import { FaceView } from "./face-view";
import { FullImageView } from "./full-image-view";
import { analysisMarkdown } from "./analysis-model";

export function FullV2View({ image, fileName }: { image: ImageFullV2Result; fileName: string }) {
  const [tab, setTab] = useState("faces");
  const results = image.results.filter(step => step.kind === "florence");
  const families = image.coverage.families.filter(f => f.task.startsWith("<")) as ImageFullAnalysisResult["coverage"]["families"];
  const native: ImageFullAnalysisResult = { ...image, results, profile: "image-full-v1", schema_version: "image-full-result-v1",
    coverage: { families, task_families_total: 15, task_families_completed: families.filter(f => f.completed).length,
      instances_planned: results.length, instances_completed: results.filter(r => r.status === "succeeded").length } };
  const markdown = () => `# Full Analysis v2

Status: ${image.analysis_status}
Cobertura: ${image.coverage.task_families_completed}/${image.coverage.task_families_total} famílias
Motivo: ${image.reason_code ?? "—"}

` + analysisMarkdown(native) + "\n\n" + faceMarkdown(image.faces);
  return <div className="space-y-5">
    <section className="space-y-3 rounded-xl border p-4">
      <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-xl font-semibold">Full Analysis · rostos e expressões</h2><AnalysisStatus status={image.analysis_status} /></div>
      <p className="text-sm">{image.coverage.task_families_completed}/{image.coverage.task_families_total} famílias concluídas · {image.calls_started} chamadas · {(image.duration_ms/1000).toFixed(1)} s</p>
      <div className="flex flex-wrap gap-2"><Button size="sm" onClick={() => downloadText(`${fileName}.full.json`, JSON.stringify(image, null, 2), "application/json")}>Baixar Full JSON</Button><Button size="sm" variant="outline" onClick={() => downloadText(`${fileName}.full.md`, markdown(), "text/markdown")}>Baixar Markdown</Button></div>
    </section>
    <div role="group" aria-label="Análises da imagem" className="flex gap-2"><Button variant={tab === "faces" ? "default" : "outline"} onClick={() => setTab("faces")}>Rostos e expressões</Button><Button variant={tab === "florence" ? "default" : "outline"} onClick={() => setTab("florence")}>Análise visual · 15 famílias</Button></div>
    {tab === "faces" ? <FaceView analysis={image.faces} width={image.width} height={image.height} mime={image.image_mime_type ?? "image/png"} imageBase64={image.image_base64} fileName={fileName} /> : <FullImageView image={native} fileName={fileName} showSummary={false} />}
  </div>;
}
