"use client";

import { useEffect, useId } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { datalakeApi } from "@/lib/datalake-api";
import { useAuthStore } from "@/lib/store/auth";
import { formatApiError } from "@/lib/utils";
import type { PartitionField, PartitionPreviewRequest, PartitionStrategy } from "@/types/datalake";

const selectClass = "h-10 w-full rounded-md border bg-background px-3 text-sm";
export const PARTITION_LABELS = { none: "Atual · pasta e ID do job", date: "Por data", project_date: "Projeto + data", custom: "Personalizada" };
const FIELDS: Record<PartitionField["field"], string> = { date: "Data (conforme granularidade)", year: "Ano", month: "Mês", day: "Dia", hour: "Hora", project_id: "ID do projeto", folder_id: "ID da pasta", source_type: "Origem", custom: "Campo personalizado" };

export function activePartitionValues(strategy: PartitionStrategy, values: Record<string, string>, previous: PartitionStrategy) {
  const keys = new Set(strategy.mode === "custom" ? strategy.fields.filter((field) => field.field === "custom").map((field) => field.key) : []);
  const previousKeys = new Set(previous.mode === "custom" ? previous.fields.filter((field) => field.field === "custom").map((field) => field.key) : []);
  // Remove values for deleted directory dimensions, while retaining context
  // provided through the API that was never a directory dimension.
  return Object.fromEntries(Object.entries(values).filter(([key]) => keys.has(key) || !previousKeys.has(key)));
}

export function PartitionValuesFields({ strategy, values, onChange, required = false }: { strategy: PartitionStrategy; values: Record<string, string>; onChange: (value: Record<string, string>) => void; required?: boolean }) {
  const id = useId();
  const fields = strategy.mode === "custom" ? strategy.fields.filter((field) => field.field === "custom" && field.key) : [];
  if (!fields.length) return null;
  return <div className="space-y-3"><p className="text-sm font-medium">Valores dos campos personalizados</p>{fields.map((field, index) => <div key={index}><Label htmlFor={id + index}>{field.key}{required && strategy.missing === "require" ? " (obrigatório)" : ""}</Label><Input id={id + index} value={values[field.key!] ?? ""} maxLength={128} required={required && strategy.missing === "require"} onChange={(e) => onChange({ ...values, [field.key!]: e.target.value })} placeholder={required ? "Valor nesta solicitação" : "Padrão opcional; pode ser preenchido na solicitação"} /></div>)}</div>;
}

export function PartitionEditor({ value, onChange }: { value: PartitionStrategy; onChange: (value: PartitionStrategy) => void }) {
  const id = useId();
  const update = (fields: PartitionField[]) => onChange({ ...value, fields });
  const newCustomKey = (except = -1) => { let index = 1; while (value.fields.some((field, i) => i !== except && field.key === "custom_" + index)) index++; return "custom_" + index; };
  const move = (index: number, offset: number) => { const fields = [...value.fields]; [fields[index], fields[index + offset]] = [fields[index + offset], fields[index]]; update(fields); };
  return <div className="space-y-3 rounded-lg border p-3">
    <div><Label htmlFor={id + "-mode"}>Estratégia de particionamento</Label><select id={id + "-mode"} className={selectClass} value={value.mode} onChange={(e) => {
      const mode = e.target.value as PartitionStrategy["mode"];
      onChange({ ...value, mode, fields: mode === "custom" ? (value.fields.length ? value.fields : [{ field: "date" }]) : mode === "project_date" ? [{ field: "project_id" }, { field: "date" }] : mode === "date" ? [{ field: "date" }] : [] });
    }}>{Object.entries(PARTITION_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></div>
    {value.mode === "custom" && <div className="space-y-2"><p className="text-sm font-medium">Campos na ordem do caminho</p>{value.fields.map((field, index) => <div key={index} className="space-y-2 rounded-md bg-muted/40 p-2">
      <Label htmlFor={id + "-field-" + index}>Campo {index + 1}</Label><select id={id + "-field-" + index} className={selectClass} value={field.field} onChange={(e) => update(value.fields.map((f, i) => i === index ? { field: e.target.value as PartitionField["field"], ...(e.target.value === "custom" ? { key: newCustomKey(index) } : {}) } : f))}>{Object.entries(FIELDS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>
      {field.field === "custom" && <div><Label htmlFor={id + "-key-" + index}>Chave do campo {index + 1}</Label><Input id={id + "-key-" + index} value={field.key ?? ""} maxLength={32} placeholder="cliente ou departamento" onChange={(e) => update(value.fields.map((f, i) => i === index ? { ...f, key: e.target.value } : f))} /><p className="text-xs text-muted-foreground">Letras minúsculas, números e sublinhado; comece com letra.</p></div>}
      <div className="flex gap-1"><Button type="button" size="sm" variant="ghost" aria-label={`Subir campo ${index + 1}`} disabled={!index} onClick={() => move(index, -1)}><ArrowUp className="h-4 w-4" /></Button><Button type="button" size="sm" variant="ghost" aria-label={`Descer campo ${index + 1}`} disabled={index === value.fields.length - 1} onClick={() => move(index, 1)}><ArrowDown className="h-4 w-4" /></Button><Button type="button" size="sm" variant="ghost" aria-label={`Remover campo ${index + 1}`} onClick={() => update(value.fields.filter((_, i) => i !== index))}><Trash2 className="h-4 w-4" /></Button></div>
    </div>)}<Button type="button" variant="outline" size="sm" disabled={value.fields.length >= 8} onClick={() => update([...value.fields, { field: "custom", key: newCustomKey() }])}><Plus className="h-4 w-4" />Adicionar campo</Button></div>}
    {value.mode !== "none" && <>
      <div className="grid gap-3 sm:grid-cols-2"><div><Label htmlFor={id + "-granularity"}>Granularidade da data</Label><select id={id + "-granularity"} className={selectClass} value={value.granularity} onChange={(e) => onChange({ ...value, granularity: e.target.value as PartitionStrategy["granularity"] })}><option value="month">Mês</option><option value="day">Dia</option><option value="hour">Hora</option></select></div><div><Label htmlFor={id + "-timezone"}>Fuso horário</Label><Input id={id + "-timezone"} value={value.timezone} list={id + "-zones"} maxLength={100} onChange={(e) => onChange({ ...value, timezone: e.target.value })} /><datalist id={id + "-zones"}>{["UTC", "America/Sao_Paulo", "America/New_York", "Europe/Lisbon"].map((zone) => <option key={zone} value={zone} />)}</datalist></div></div>
      <div><Label htmlFor={id + "-missing"}>Quando um valor estiver ausente</Label><select id={id + "-missing"} className={selectClass} value={value.missing} onChange={(e) => onChange({ ...value, missing: e.target.value as PartitionStrategy["missing"] })}><option value="fallback">Usar valor substituto</option><option value="require">Exigir preenchimento</option></select></div>
      {value.missing === "fallback" && <div><Label htmlFor={id + "-fallback"}>Valor substituto</Label><Input id={id + "-fallback"} value={value.fallback} maxLength={128} onChange={(e) => onChange({ ...value, fallback: e.target.value })} /></div>}
      <p className="text-xs text-muted-foreground">A data será a de criação do job. Alterar a estratégia afeta somente novas solicitações.</p>
    </>}
    <div><Label htmlFor={id + "-analytics"}>Exportação analítica</Label><select id={id + "-analytics"} className={selectClass} value={value.analytics} onChange={(e) => onChange({ ...value, analytics: e.target.value as PartitionStrategy["analytics"] })}><option value="none">Somente arquivos de resultado</option><option value="jsonl">Arquivos + dataset JSONL</option></select><p className="mt-1 text-xs text-muted-foreground">JSONL contém uma linha por job, com texto, metadados e resultado completo. Dataset e esquema ficam em pastas próprias.</p></div>
  </div>;
}

export function PartitionPreview({ input, demo = false, onValid }: { input: PartitionPreviewRequest; demo?: boolean; onValid?: (valid: boolean) => void }) {
  const token = useAuthStore((s) => s.token);
  const fields = input.partitioning?.mode === "custom" ? input.partitioning.fields : [];
  const request = demo ? { ...input, project_id: "projeto-exemplo", folder_id: "pasta-exemplo", source_type: "file", partition_values: {
    ...Object.fromEntries(fields.filter((f) => f.field === "custom" && f.key).map((f) => [f.key!, "exemplo"])), ...Object.fromEntries(Object.entries(input.partition_values ?? {}).filter(([, value]) => value.trim())) } } : input;
  const preview = useQuery({ queryKey: ["partition-preview", token, request], queryFn: () => datalakeApi.partitionPreview(request), enabled: !!token, retry: false, staleTime: 30_000 });
  useEffect(() => { onValid?.(preview.isSuccess && !preview.isFetching); }, [preview.isSuccess, preview.isFetching, onValid]);
  const path = (value: string) => value.replace("00000000-0000-0000-0000-000000000000", "[ID do job]");
  return <div aria-label="Prévia do particionamento" className="space-y-2 rounded-lg bg-muted/40 p-3 text-sm"><p className="font-medium">{demo ? "Exemplo de destino" : "Prévia do destino"}</p>
    {preview.isFetching && <p role="status" className="text-xs text-muted-foreground">Calculando caminho…</p>}
    {preview.isError && <p role="alert" className="text-sm text-destructive">{formatApiError(preview.error)}</p>}
    {preview.data && <><p className="break-all font-mono text-xs">{path(preview.data.resolved_path)}/</p>{preview.data.dataset_path && <><p className="text-xs font-medium">Dataset JSONL</p><p className="break-all font-mono text-xs">{path(preview.data.dataset_path)}</p></>}</>}
    <p className="text-xs text-muted-foreground">{demo ? "Exemplo com IDs e valores ilustrativos. " : ""}A prévia usa a data atual. O caminho definitivo usa a criação do job e é preservado nos retries. Cada layout tem uma versão própria.</p>
    {!demo && (input.project_id === "novo-projeto" || input.folder_id === "nova-pasta") && <p className="text-xs text-muted-foreground">Projetos e pastas novos aparecem com IDs ilustrativos até o envio da solicitação.</p>}
  </div>;
}
