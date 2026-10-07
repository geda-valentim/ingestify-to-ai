"use client";
import { useState } from "react";
import { downloadText } from "@/lib/utils";
import type { FacialBlock } from "@/types/faces";
import { faceMarkdown } from "./face-markdown";
import { Button } from "@/components/ui/button";

const reasons: Record<string, string> = {
  no_faces: "Nenhum rosto detectado.", not_requested: "Esta etapa não foi solicitada.",
  face_landmarks_unavailable: "Não foi possível obter os movimentos deste rosto.",
  face_association_ambiguous: "Não foi possível associar esta análise ao rosto com segurança.",
  dependency_failed: "Uma etapa anterior falhou.", face_provider_unavailable: "Modelo facial indisponível.",
  deadline: "O prazo total terminou.", cancelled: "A análise foi cancelada.",
};
const message = (code?: string | null) => code ? reasons[code] ?? code : "Sem resultado disponível.";

export function FaceView({ analysis, imageBase64, mime, width, height, fileName }: {
  analysis: FacialBlock; imageBase64?: string | null; mime: string; width: number; height: number; fileName: string;
}) {
  const [faceId, setFaceId] = useState(analysis.faces[0]?.face_id);
  const [boxes, setBoxes] = useState(true);
  const [keypoints, setKeypoints] = useState(false);
  const [landmarks, setLandmarks] = useState(false);
  const selected = analysis.faces.find(face => face.face_id === faceId) ?? analysis.faces[0];
  const detection = analysis.detection;
  return <section className="min-w-0 space-y-4" aria-label="Rostos e expressões">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div><h2 className="text-xl font-semibold">Rostos e expressões</h2><p className="mt-1 text-sm text-muted-foreground">
        {analysis.coverage.task_families_completed}/{analysis.coverage.task_families_total} famílias concluídas · {detection.selected_count ?? 0} rostos selecionados
      </p></div>
      <div className="flex flex-wrap gap-2">      <Button size="sm" onClick={() => downloadText(`${fileName}.faces.json`, JSON.stringify(analysis, null, 2), "application/json")}>Baixar análise facial</Button><Button size="sm" variant="outline" onClick={() => downloadText(`${fileName}.faces.md`, faceMarkdown(analysis), "text/markdown")}>Baixar facial Markdown</Button></div>
    </div>
    <p className="text-xs text-muted-foreground">Estimativa de expressão visível; não determina o estado emocional. Os scores não são probabilidades calibradas.</p>
    {detection.selection_limited && <p role="status" className="rounded border p-3 text-sm">Limite aplicado: {detection.selected_count} de {detection.detected_count} detecções foram analisadas; {detection.omitted_count} omitidas.</p>}
    <div className="flex flex-wrap gap-4 text-sm">
      {([["Caixas", boxes, setBoxes], ["Keypoints", keypoints, setKeypoints], ["Landmarks", landmarks, setLandmarks]] as const).map(([label, active, set]) =>
        <label key={label} className="flex items-center gap-2"><input type="checkbox" checked={active} onChange={e => set(e.target.checked)} />{label}</label>)}
    </div>
    {imageBase64 && width > 0 && height > 0 && <div className="relative mx-auto w-fit max-w-full overflow-hidden rounded-lg border">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img alt="Imagem analisada com camadas faciais" src={`data:${mime};base64,${imageBase64}`} className="block max-h-[65vh] max-w-full object-contain" />
      <svg viewBox={`0 0 ${width} ${height}`} className="absolute inset-0 h-full w-full" aria-label="Camadas faciais">
        {analysis.faces.map(face => <g key={face.face_id} onClick={() => setFaceId(face.face_id)}>
          {boxes && <rect x={face.bbox[0]} y={face.bbox[1]} width={face.bbox[2]-face.bbox[0]} height={face.bbox[3]-face.bbox[1]} fill="transparent" stroke={face.face_id === selected?.face_id ? "#22c55e" : "#38bdf8"} strokeWidth={Math.max(1, width/350)} className="cursor-pointer" />}
          {keypoints && face.keypoints.map(point => <circle key={point.index} cx={point.x} cy={point.y} r={Math.max(1, width/220)} fill="#facc15" />)}
          {landmarks && face.face_id === selected?.face_id && face.movements.landmarks?.map(point => <circle key={point.index} cx={point.x} cy={point.y} r={Math.max(.5, width/700)} fill="#22c55e" />)}
        </g>)}
      </svg>
    </div>}
    {!analysis.faces.length ? <p role="status" className="rounded border p-4 text-sm">{detection.status === "succeeded" ? "Nenhum rosto detectado nesta imagem." : message(detection.reason_code)}</p> : <>
      <label className="block space-y-1 text-sm">Rosto selecionado<select aria-label="Rosto selecionado" value={selected?.face_id} onChange={e => setFaceId(e.target.value)} className="block h-10 w-full rounded border bg-background px-3">
        {analysis.faces.map(face => <option key={face.face_id} value={face.face_id}>{face.face_id} · detecção {(100*face.detection_confidence).toFixed(1)}%</option>)}
      </select></label>
      {selected && <div className="grid gap-4 md:grid-cols-2">
        <section className="space-y-3 rounded border p-4"><h3 className="font-medium">Expressão estimada</h3>
          <p className="text-sm">{selected.expression.status === "succeeded" ? selected.expression.label ?? "Inconclusiva: score abaixo do limiar" : message(selected.expression.reason_code)}</p>
          {selected.expression.scores?.map(item => <div key={item.label} className="space-y-1"><div className="flex justify-between text-xs"><span>{item.label}</span><span>{(item.score*100).toFixed(1)}%</span></div><progress value={item.score} max={1} className="h-2 w-full" /></div>)}
        </section>
        <section className="space-y-3 rounded border p-4"><h3 className="font-medium">Movimentos faciais</h3>
          {selected.movements.status !== "succeeded" ? <p className="text-sm">{message(selected.movements.reason_code)}</p> : <>
            <p className="text-xs text-muted-foreground">{selected.movements.landmarks?.length} landmarks · {selected.movements.blendshapes?.length} coeficientes. Intensidades de movimento facial.</p>
            <div className="max-h-80 space-y-2 overflow-y-auto">{[...(selected.movements.blendshapes ?? [])].sort((a,b) => b.score-a.score).map(item => <div key={item.name} className="flex justify-between gap-2 text-xs"><span className="break-all">{item.name}</span><span>{item.score.toFixed(3)}</span></div>)}</div>
          </>}
        </section>
      </div>}
    </>}
    <details className="rounded border p-3"><summary className="cursor-pointer text-sm">Parâmetros aplicados e modelos</summary>
      <pre className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify({ request: analysis.request, models: analysis.models }, null, 2)}</pre>
    </details>
    <details className="rounded border p-3"><summary className="cursor-pointer text-sm">Etapas e cobertura por rosto</summary>
      <ul className="mt-3 space-y-2 text-xs">{analysis.steps.map(step => <li key={step.step_id}>{step.operation} {step.face_id} · {step.status}{step.reason_code ? ` · ${message(step.reason_code)}` : ""}</li>)}</ul>
    </details>
  </section>;
}
