"use client";
import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { jobsApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store/auth";
import { formatApiError } from "@/lib/utils";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { ModelOptions } from "./model-options";
import { FaceOptionsFields } from "./face-options";
import { ImageRegionPicker } from "./image-region-picker";
import { DatalakeDestinationFields } from "@/components/datalake/destination-fields";
import type { CaptionTask, VisionTask, UploadRequest } from "@/types/api";
import type { FaceOptions } from "@/types/faces";
import type { DatalakeDestination } from "@/types/datalake";

export function ImageUploadOptions({ file: selectedFile, disabled, onChange, onValid }: {
 file: File; disabled: boolean; onChange: (request: Partial<UploadRequest>) => void; onValid: (valid: boolean) => void;
}) {
 const token = useAuthStore(s => s.token);
 const isImage = true;
 const [generationValid, setGenerationValid] = useState(true);
 const [destination, setDestination] = useState<DatalakeDestination | null>(null);
 const [partitionValid, setPartitionValid] = useState(true);
  const [imageOperation, setImageOperation] = useState<"describe" | "ocr" | "analyze" | "full" | "faces">("describe");
  const [imageTask, setImageTask] = useState<CaptionTask | "">("");
  const [analysisTask, setAnalysisTask] = useState<VisionTask>("<OD>");
  const [imageTextInput, setImageTextInput] = useState("");
  const [faceOptions, setFaceOptions] = useState<FaceOptions>({});
  const [fullProfile, setFullProfile] = useState<"image-full-v1" | "image-full-v2">("image-full-v1");
  const fullProfileChosen = useRef(false);
  const [fullQueries, setFullQueries] = useState("");
  const [imageRegion, setImageRegion] = useState<number[] | null>(null);
  const [imageGeneration, setImageGeneration] = useState<Record<string, unknown>>({});
  const imageCapabilities = useQuery({
    queryKey: ["image-capabilities", token], queryFn: jobsApi.imageCapabilities,
    enabled: !!token && isImage, staleTime: 30_000,
  });
  const faceCapabilities = useQuery({ queryKey: ["face-capabilities", token], queryFn: jobsApi.faceCapabilities,
    enabled: !!token && isImage, staleTime: 30_000 });
  useEffect(() => {
    if (!fullProfileChosen.current && imageCapabilities.data?.full_profiles) {
      if (imageCapabilities.data.full_profiles.some(p => p.profile === "image-full-v2" && p.ready)) setFullProfile("image-full-v2");
      fullProfileChosen.current = true;
    }
  }, [imageCapabilities.data]);
  const needsFaces = imageOperation === "faces" || (imageOperation === "full" && fullProfile === "image-full-v2");
  const faceMode = imageOperation === "full" ? "expressions" : faceOptions.mode ?? "expressions";
  const faceStages = faceCapabilities.data?.stages;
  const faceUnavailable = needsFaces && (faceCapabilities.isPending || faceCapabilities.isError || !faceCapabilities.data?.enabled || !faceStages?.face_detection?.ready ||
    (faceMode === "expressions" && (!faceStages?.face_movements?.ready || !faceStages?.face_expression_classification?.ready)));
  const faceInputError = needsFaces && Object.entries(faceOptions).some(([key,value]) => key !== "mode" &&
    (typeof value !== "number" || !Number.isFinite(value) || (key === "max_faces" ? !Number.isInteger(value) || value < 1 || value > (imageOperation === "full" ? 5 : 10) : key === "deadline_seconds" ? !Number.isInteger(value) || value < 1 || value > 300 : value < 0 || value > 1)));
  const imageSizeError = isImage && imageCapabilities.data && selectedFile!.size > imageCapabilities.data.max_image_size_mb * 1024 * 1024;
  const imageUnavailable = isImage && (faceUnavailable || (imageOperation !== "faces" && (imageCapabilities.isPending || imageCapabilities.isError || !imageCapabilities.data?.enabled || !imageCapabilities.data?.dependencies_installed || !imageCapabilities.data?.model_downloaded)));
  const analysisTaskInfo = imageCapabilities.data?.tasks?.find((item) => item.task === analysisTask);
  const fullQueryValues = fullQueries.split("\n").map(query => query.trim()).filter(Boolean);
  const fullInputError = isImage && imageOperation === "full" && (fullQueryValues.length > 3 || fullQueryValues.join(". ").length > 2000);
  const imageInputError = faceInputError || fullInputError || (isImage && imageOperation === "analyze" && (
    !analysisTaskInfo || (analysisTaskInfo.input === "text" && !imageTextInput.trim()) ||
    (analysisTaskInfo.input === "region" && (!imageRegion || imageRegion[0] >= imageRegion[2] || imageRegion[1] >= imageRegion[3]))));

  useEffect(() => {
    onChange({ image_operation: imageOperation,
      image_task: imageOperation === "analyze" ? analysisTask : imageOperation === "ocr" ? "<OCR_WITH_REGION>" : imageTask || imageCapabilities.data?.default_caption_task,
      image_text_input: imageOperation === "analyze" && analysisTaskInfo?.input === "text" ? imageTextInput.trim() : undefined,
      image_region: imageOperation === "analyze" && analysisTaskInfo?.input === "region" ? imageRegion ?? undefined : undefined,
      image_generation: imageGeneration,
      datalake: (imageOperation === "full" || imageOperation === "faces") && destination ? destination : undefined,
      face_options: imageOperation === "faces" ? faceOptions : undefined,
      image_full_options: imageOperation === "full" ? {
        profile: fullProfile,
        ...(fullProfile === "image-full-v2" ? { faces: Object.fromEntries(Object.entries({ ...faceOptions, mode: "expressions" }).filter(([key]) => key !== "deadline_seconds")) } : {}),
        ...(fullQueries.trim() ? { queries: fullQueries.split("\n").map(v => v.trim()).filter(Boolean) } : {}),
        ...(imageRegion ? { regions: [imageRegion] } : {}),
      } : undefined,
    });
    onValid(!imageUnavailable && !imageInputError && !imageSizeError && (imageOperation === "faces" || generationValid) && (!destination || (!!destination.bucket.trim() && partitionValid)));
  }, [imageOperation, analysisTask, imageTask, imageTextInput, imageRegion, imageGeneration, destination, faceOptions, fullProfile, fullQueries, imageCapabilities.data, analysisTaskInfo, imageUnavailable, imageInputError, imageSizeError, generationValid, partitionValid, onChange, onValid]);
  return <>
                    <div className="space-y-3 rounded-lg border p-4">
                      <div className="space-y-2">
                        <Label htmlFor="image-operation">Processamento da imagem</Label>
                        <select id="image-operation" value={imageOperation} onChange={(e) => setImageOperation(e.target.value as "describe" | "ocr" | "analyze" | "full" | "faces")} disabled={disabled} className="h-10 w-full rounded-md border bg-background px-3 text-sm">
                          <option value="describe">Descrever imagem</option>
                          <option value="ocr">Extrair texto (OCR com regiões)</option>
                          <option value="analyze">Detecção, segmentação e outras análises</option>
                          <option value="full">Full Analysis · todas as capacidades de visão</option>
                          <option value="faces">Rostos e expressões</option>
                        </select>
                      </div>
                      {imageOperation === "describe" && imageCapabilities.data && (
                        <div className="space-y-2">
                          <Label htmlFor="image-task">Detalhamento da descrição</Label>
                          <select id="image-task" value={imageTask || imageCapabilities.data.default_caption_task} onChange={(e) => setImageTask(e.target.value as CaptionTask)} disabled={disabled} className="h-10 w-full rounded-md border bg-background px-3 text-sm">
                            {imageCapabilities.data.caption_tasks.map((task) => <option key={task} value={task}>{{ "<CAPTION>": "Breve", "<DETAILED_CAPTION>": "Detalhada", "<MORE_DETAILED_CAPTION>": "Muito detalhada" }[task]}</option>)}
                          </select>
                        </div>
                      )}
                      {imageOperation === "analyze" && <div className="space-y-3">
                        <div className="space-y-2"><Label htmlFor="analysis-task">Tarefa de visão</Label>
                          <select id="analysis-task" value={analysisTask} onChange={(e) => setAnalysisTask(e.target.value as VisionTask)} disabled={disabled} className="h-10 w-full rounded-md border bg-background px-3 text-sm">
                            {imageCapabilities.data?.tasks?.map((item) => <option key={item.task} value={item.task}>{item.label}</option>)}
                          </select>
                        </div>
                        {analysisTaskInfo?.input === "text" && <div className="space-y-2"><Label htmlFor="image-text-input">Texto para localizar na imagem</Label>
                          <Input id="image-text-input" value={imageTextInput} onChange={(e) => setImageTextInput(e.target.value)} maxLength={2000} disabled={disabled} placeholder="Ex.: um carro vermelho, uma pessoa ao lado da porta" />
                          <p className="text-xs text-muted-foreground">Descreva o objeto, a expressão ou a frase que a tarefa deve localizar.</p>
                        </div>}
                        {analysisTaskInfo?.input === "region" && selectedFile && <ImageRegionPicker file={selectedFile} region={imageRegion} onChange={setImageRegion} disabled={disabled} />}
                        {imageInputError && <p className="text-xs text-muted-foreground">Preencha a entrada exigida pela tarefa escolhida.</p>}
                      </div>}
                      {imageOperation === "faces" && <FaceOptionsFields value={faceOptions} onChange={setFaceOptions} disabled={disabled} />}
                      {imageOperation === "full" && <div className="space-y-3 rounded border p-3">
                        <p className="text-sm">Descrições, texto, objetos, regiões e segmentações em uma execução. A imagem basta: consultas e regiões são selecionadas automaticamente.</p>
                        <label className="block space-y-1 text-sm">Perfil do Full Analysis<select aria-label="Perfil do Full Analysis" value={fullProfile} onChange={e => { fullProfileChosen.current = true; setFullProfile(e.target.value as typeof fullProfile); }} className="block h-10 w-full rounded border bg-background px-3">
                          <option value="image-full-v1">Florence · 15 famílias</option><option value="image-full-v2">Florence + rostos e expressões · 18 famílias</option>
                        </select></label>
                        {fullProfile === "image-full-v2" && <FaceOptionsFields full value={faceOptions} onChange={setFaceOptions} disabled={disabled} />}
                        <p className="text-xs text-muted-foreground">{fullProfile === "image-full-v2" ? "18 famílias; até 5 rostos e 54 chamadas incluindo recuperação." : "15 tarefas de visão; até 3 consultas, 4 regiões e 32 chamadas."} Pode demorar mais. O resultado mostra cobertura e limites.</p>
                        <details className="space-y-3"><summary className="cursor-pointer text-sm font-medium">Consultas e região de interesse (opcional)</summary>
                          <label htmlFor="full-queries" className="text-sm">Objetos ou expressões, uma por linha (até 3)</label>
                          <textarea id="full-queries" value={fullQueries} onChange={event => { setFullQueries(event.target.value);  }} className="w-full rounded border bg-background p-2" maxLength={2000} placeholder="a red car" />
                          {fullInputError && <p role="alert" className="text-xs text-destructive">Use até três consultas, com no máximo 2000 caracteres no total.</p>}
                          {selectedFile && <ImageRegionPicker file={selectedFile} region={imageRegion} onChange={region => { setImageRegion(region);  }} disabled={disabled} />}
                          <button type="button" className="text-xs underline" onClick={() => { setFullQueries(""); setImageRegion(null);  }}>Usar seleção automática</button>
                        </details>
                      </div>}
                      {imageOperation !== "faces" && imageCapabilities.data?.generation_schema && <details className="space-y-3 rounded border p-3">
                        <summary className="cursor-pointer text-sm font-medium">Opções de geração</summary>
                        <ModelOptions onValid={setGenerationValid} schema={imageCapabilities.data.generation_schema} defaults={imageCapabilities.data.generation_defaults} value={imageGeneration} onChange={value => { setImageGeneration(value);  }} disabled={disabled} />
                        <button type="button" className="text-xs underline" onClick={() => setImageGeneration({})}>Restaurar padrões do serviço</button>
                      </details>}
                      <p className="text-xs text-muted-foreground">{imageCapabilities.data ? `Limite: ${imageCapabilities.data.max_image_size_mb} MB. ` : "Verificando disponibilidade… "}O nome do arquivo identifica o job. Imagens são salvas no projeto; Full Analysis também permite exportação para datalake quando um destino é selecionado.</p>
                      {faceInputError && <p role="alert" className="text-sm text-destructive">Revise os parâmetros faciais e os limites exibidos.</p>}
                      {imageSizeError && <p role="alert" className="text-sm text-destructive">A imagem excede o limite de tamanho.</p>}
                      {imageUnavailable && !imageCapabilities.isPending && <p role="alert" className="text-sm text-destructive">Processamento de imagens indisponível. {(faceUnavailable ? faceCapabilities.data?.reason || "Modelos faciais indisponíveis neste worker." : imageCapabilities.data?.reason) || formatApiError(imageCapabilities.error, "Verifique a disponibilidade do serviço.")}</p>}
                    </div>
{(imageOperation === "full" || imageOperation === "faces") && <DatalakeDestinationFields value={destination} onChange={setDestination} onValid={setPartitionValid} disabled={disabled} />}
</>;
}
