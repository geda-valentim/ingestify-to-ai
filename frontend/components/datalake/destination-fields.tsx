"use client";

import { useEffect, useId, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { datalakeApi } from "@/lib/datalake-api";
import { useAuthStore } from "@/lib/store/auth";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { DEFAULT_PARTITION, PROVIDER_LABELS, type DatalakeDestination, type PartitionPreviewRequest } from "@/types/datalake";
import { PartitionEditor, PartitionPreview, PartitionValuesFields, PARTITION_LABELS, activePartitionValues } from "./partition-editor";

export function DatalakeDestinationFields({ value, onChange, disabled = false, source = false, context, onValid }: {
  value: DatalakeDestination | null;
  onChange: (value: DatalakeDestination | null) => void;
  disabled?: boolean;
  source?: boolean;
  context?: Pick<PartitionPreviewRequest, "project_id" | "folder_id" | "source_type">;
  onValid?: (valid: boolean) => void;
}) {
  const id = useId();
  const [manual, setManual] = useState(false);
  const token = useAuthStore((s) => s.token);
  const connections = useQuery({ queryKey: ["datalakes", token], queryFn: datalakeApi.list, enabled: !!token });
  const buckets = useQuery({ queryKey: ["datalake-buckets", token, value?.connection_id],
    queryFn: () => datalakeApi.buckets(value!.connection_id), enabled: !!value?.connection_id && !!token });
  const choices = connections.data?.connections.filter((c) => c.enabled) ?? [];
  const validConnection = !value || choices.some((c) => c.id === value.connection_id);
  const connection = choices.find((c) => c.id === value?.connection_id);
  useEffect(() => { if (!value || source) onValid?.(true); else if (!connection) onValid?.(false); }, [value?.connection_id, source, connection, onValid]);
  const strategy = value?.partitioning ?? connection?.config.partitioning ?? DEFAULT_PARTITION;
  const partitionValues = { ...(connection?.config.default_partition_values ?? {}), ...(value?.partition_values ?? {}) };
  const bucketChoices = buckets.data?.buckets ?? connection?.config.buckets ?? [];
  const canEnterBucket = !connection?.config.buckets.length;
  const useManual = manual || (!buckets.isPending && !bucketChoices.length) || (!!value?.bucket && !bucketChoices.includes(value.bucket));
  const selectClass = "h-10 w-full rounded-md border bg-background px-3 text-sm disabled:opacity-50";
  return <fieldset disabled={disabled} className="space-y-3 rounded-lg border p-4">
    <legend className="px-1 text-sm font-medium">{source ? "Datalake de origem" : "Destino dos resultados"}</legend>
    <div className="space-y-1">
      <Label htmlFor={id + "-connection"}>1. Conexão</Label>
      <select id={id + "-connection"} className={selectClass} value={value?.connection_id ?? ""} onChange={(e) => {
        const connection = choices.find((c) => c.id === e.target.value);
        setManual(false);
        onChange(connection ? { connection_id: connection.id, bucket: connection.config.default_bucket ?? "", prefix: connection.config.default_prefix } : null);
      }}>
        <option value="">{source ? "Escolha uma conexão" : "Armazenamento padrão do Ingestify"}</option>
        {choices.map((c) => <option key={c.id} value={c.id}>{c.name} · {PROVIDER_LABELS[c.provider]}</option>)}
      </select>
    </div>
    {connections.isError && <p role="alert" className="text-sm text-destructive">Não foi possível carregar as conexões. <button type="button" className="underline" onClick={() => void connections.refetch()}>Tentar novamente</button></p>}
    {!validConnection && connections.isSuccess && <p role="alert" className="text-sm text-destructive">Esta conexão não está disponível. Escolha outra conexão.</p>}
    {value && <div className="grid gap-3 sm:grid-cols-2">
      <div className="space-y-1"><Label htmlFor={id + "-bucket"}>2. {connection?.provider === "azure" ? "Container (bucket)" : "Bucket"}</Label>
        {useManual ? <Input id={id + "-bucket"} value={value.bucket} onChange={(e) => onChange({ ...value, bucket: e.target.value })} placeholder="nome-do-bucket" maxLength={255} required />
          : <select id={id + "-bucket"} className={selectClass} value={value.bucket} onChange={(e) => onChange({ ...value, bucket: e.target.value })} required><option value="">Selecione um bucket</option>{bucketChoices.map((b) => <option key={b} value={b}>{b}{b === connection?.config.default_bucket ? " (padrão)" : ""}</option>)}</select>}
        {buckets.isFetching && <p role="status" className="text-xs text-muted-foreground">Carregando buckets…</p>}
        {!!bucketChoices.length && <p className="text-xs text-muted-foreground">{bucketChoices.length} {connection?.config.buckets.length ? "permitidos" : "disponíveis"}</p>}
        {canEnterBucket && !!bucketChoices.length && <button type="button" className="text-xs underline" onClick={() => { setManual(!useManual); if (useManual && !bucketChoices.includes(value.bucket)) onChange({ ...value, bucket: "" }); }}>{useManual ? "Ver lista de buckets" : "Informar outro bucket"}</button>}
        {buckets.isError && <p className="text-xs text-muted-foreground">Listagem indisponível. Informe o nome de um bucket permitido.</p>}
      </div>
      <div className="space-y-1"><Label htmlFor={id + "-prefix"}>3. {source ? "Filtrar por pasta" : "Pasta de destino (opcional)"}</Label>
        <Input id={id + "-prefix"} value={value.prefix} onChange={(e) => onChange({ ...value, prefix: e.target.value })} placeholder={source ? "documentos/" : "resultados/"} maxLength={700} /></div>
    </div>}
    {value && !source && connection && <>
      <div className="space-y-3 border-t pt-3"><p className="text-sm font-medium">Particionamento: {PARTITION_LABELS[strategy.mode]}</p>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!!value.partitioning} onChange={(e) => onChange({ ...value, partitioning: e.target.checked ? { ...strategy } : undefined })} />Personalizar particionamento nesta solicitação</label>
        {value.partitioning && <PartitionEditor value={strategy} onChange={(partitioning) => onChange({ ...value, partitioning, partition_values: activePartitionValues(partitioning, value.partition_values ?? {}, strategy) })} />}
        <PartitionValuesFields strategy={strategy} values={partitionValues} required onChange={(partition_values) => onChange({ ...value, partition_values })} />
        <PartitionPreview input={{ connection_id: connection.id, partitioning: value.partitioning ?? undefined, partition_values: value.partition_values, prefix: value.prefix, ...context }} onValid={onValid} />
      </div>
      <button type="button" className="text-xs underline" onClick={() => { setManual(false); onChange({ connection_id: connection.id, bucket: connection.config.default_bucket ?? "", prefix: connection.config.default_prefix }); }}>Usar padrões da conexão</button>
    </>}
    <p className="text-xs text-muted-foreground">{source ? "Selecione o bucket que contém seu arquivo." : value ? "Os resultados usarão a estratégia escolhida, com uma pasta por job." : "Os resultados ficam disponíveis na página do job."} <Link className="underline" href="/datalakes">Gerenciar conexões</Link></p>
  </fieldset>;
}
