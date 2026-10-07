"use client";
import { useEffect, useState } from "react";
import { Label } from "@/components/ui/label";
import { ModelOptions } from "./model-options";
import type { DocumentCapabilities, DocumentFormat, DocumentOptions } from "@/types/api";

export function DocumentOptionsFields({ capabilities, preset, onPreset, value, onChange, disabled, onValid }: {
  capabilities: DocumentCapabilities; preset: string; onPreset: (preset: string) => void;
  value: DocumentOptions; onChange: (value: DocumentOptions) => void;
  disabled: boolean; onValid: (valid: boolean) => void;
}) {
  const formats = value.formats ?? ["markdown"];
  const [errors, setErrors] = useState<Record<string, boolean>>({});
  useEffect(() => { onValid(!Object.entries(errors).some(([name, invalid]) => invalid && (name === "pipeline" || name === "limits" || formats.includes(name as DocumentFormat)))); }, [errors, formats, onValid]);
  const report = (name: string, valid: boolean) => setErrors((previous) => previous[name] === !valid ? previous : { ...previous, [name]: !valid });
  const changeFormat = (format: DocumentFormat, checked: boolean) => {
    const next = checked ? [...formats, format] : formats.filter((item) => item !== format);
    if (!next.length) return;
    const exports = Object.fromEntries(Object.entries(value.export_options ?? {}).filter(([key]) => next.includes(key as DocumentFormat)));
    onChange({ ...value, formats: next, output_format: next.includes(value.output_format ?? "markdown") ? value.output_format ?? "markdown" : next[0], export_options: exports });
  };
  return <details className="space-y-4 rounded-lg border p-4">
    <summary className="cursor-pointer text-sm font-medium">Opções de documentos · Docling {capabilities.version}</summary>
    {!capabilities.workers_running && <p className="text-xs text-muted-foreground">Nenhum worker de documentos ativo foi detectado; novas solicitações aguardam na fila.</p>}
    {capabilities.worker_prerequisites?.length > 0 && <p className="text-xs text-muted-foreground">OCR instalado: {Object.entries(capabilities.worker_prerequisites[0].ocr_dependencies).filter(([, installed]) => installed).map(([name]) => name).join(", ")}. Os pesos de enriquecimentos opcionais podem precisar de download.</p>}
    <div><Label htmlFor="docling-preset">Preset de conversão</Label><select id="docling-preset" disabled={disabled} value={preset} onChange={(event) => onPreset(event.target.value)} className="h-10 w-full rounded border bg-background px-3">{Object.keys(capabilities.presets).map((name) => <option key={name} value={name}>{name}</option>)}</select></div>
    <details className="space-y-3"><summary className="cursor-pointer text-sm">OCR, tabelas, imagens e enriquecimentos</summary>
      <ModelOptions schema={capabilities.pipeline_schema} defaults={capabilities.presets[preset]} value={value.pipeline ?? {}} onChange={(pipeline) => onChange({ ...value, pipeline })} onValid={(valid) => report("pipeline", valid)} disabled={disabled} />
    </details>
    <fieldset className="space-y-2"><legend className="text-sm font-medium">Exportações</legend><div className="flex flex-wrap gap-4">{(Object.keys(capabilities.exports) as DocumentFormat[]).map((format) => <label key={format} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={formats.includes(format)} disabled={disabled} onChange={(event) => changeFormat(format, event.target.checked)} />{format.toUpperCase()}</label>)}</div></fieldset>
    <div><Label htmlFor="document-format">Formato padrão do resultado</Label><select id="document-format" value={value.output_format ?? "markdown"} disabled={disabled} onChange={(event) => onChange({ ...value, output_format: event.target.value as DocumentFormat })} className="h-10 w-full rounded border bg-background px-3">{formats.map((format) => <option key={format} value={format}>{format.toUpperCase()}</option>)}</select></div>
    {formats.map((format) => <details key={format} className="space-y-3"><summary className="cursor-pointer text-sm">Parâmetros de {format.toUpperCase()}</summary>
      <ModelOptions schema={capabilities.exports[format].parameters_schema} value={value.export_options?.[format] ?? {}} onChange={(parameters) => onChange({ ...value, export_options: { ...value.export_options, [format]: parameters } })} onValid={(valid) => report(format, valid)} disabled={disabled} />
    </details>)}
    <details className="space-y-3"><summary className="cursor-pointer text-sm">Páginas e limites</summary><ModelOptions schema={{ properties: {
      page_range: { type: "array", title: "Intervalo de páginas [primeira, última]", description: "Numeração original do PDF, começando em 1." },
      max_num_pages: { type: "integer", minimum: 1, title: "Máximo de páginas" },
      max_file_size: { type: "integer", minimum: 1, title: "Tamanho máximo em bytes" },
      raises_on_error: { type: "boolean", default: true, title: "Falhar quando a conversão apresentar erro" },
    } }} value={Object.fromEntries(Object.entries(value).filter(([name]) => ["page_range", "max_num_pages", "max_file_size", "raises_on_error"].includes(name)))} onChange={(limits) => {
      const next = { ...value }; delete next.page_range; delete next.max_num_pages; delete next.max_file_size; delete next.raises_on_error;
      onChange({ ...next, ...limits });
    }} disabled={disabled} onValid={(valid) => report("limits", valid)} /></details>
    {capabilities.restrictions.map((restriction) => <p key={restriction} className="text-xs text-muted-foreground">{restriction}</p>)}
  </details>;
}
