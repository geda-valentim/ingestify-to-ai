"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Check, Database, Loader2, Plus, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { datalakeApi } from "@/lib/datalake-api";
import { formatApiError, cn } from "@/lib/utils";
import { PROVIDER_LABELS, type DatalakeConnection, type DatalakeProvider } from "@/types/datalake";
import { DEFAULT_PARTITION, type PartitionStrategy } from "@/types/datalake";
import { PartitionEditor, PartitionPreview, PartitionValuesFields, PARTITION_LABELS, activePartitionValues } from "./partition-editor";

const STEPS = ["Conexão", "Buckets", "Padrões", "Revisão"];
const CREDENTIAL_FIELDS: Record<DatalakeProvider, { key: string; label: string; multiline?: boolean; optional?: boolean }[]> = {
  s3: [{ key: "access_key", label: "Access key" }, { key: "secret_key", label: "Secret key" }, { key: "session_token", label: "Session token", optional: true }],
  minio: [{ key: "access_key", label: "Access key" }, { key: "secret_key", label: "Secret key" }],
  gcs: [{ key: "service_account_json", label: "JSON da conta de serviço", multiline: true }],
  azure: [{ key: "connection_string", label: "Connection string", multiline: true }],
};
const selectClass = "h-10 w-full rounded-md border bg-background px-3 text-sm";

export function ConnectionEditor({ connection, onClose, onSaved }: { connection: DatalakeConnection | null; onClose: () => void; onSaved: () => void }) {
  const queryClient = useQueryClient();
  const [step, setStep] = useState(0);
  const [provider, setProvider] = useState<DatalakeProvider>(connection?.provider ?? "s3");
  const [name, setName] = useState(connection?.name ?? "");
  const [endpoint, setEndpoint] = useState(connection?.config.endpoint ?? "");
  const [region, setRegion] = useState(connection?.config.region ?? "");
  const [projectId, setProjectId] = useState(connection?.config.project_id ?? "");
  const [selected, setSelected] = useState<string[]>(connection?.config.buckets ?? []);
  const [allowAll, setAllowAll] = useState(!!connection && !connection.config.buckets.length);
  const [available, setAvailable] = useState<string[]>([]);
  const [bucket, setBucket] = useState(connection?.config.default_bucket ?? "");
  const [prefix, setPrefix] = useState(connection?.config.default_prefix ?? "");
  const [partitioning, setPartitioning] = useState<PartitionStrategy>(connection?.config.partitioning ?? DEFAULT_PARTITION);
  const [partitionValues, setPartitionValues] = useState<Record<string, string>>(connection?.config.default_partition_values ?? {});
  const [partitionValid, setPartitionValid] = useState(true);
  const [credentials, setCredentials] = useState<Record<string, string>>({});
  const [filter, setFilter] = useState("");
  const [manualBucket, setManualBucket] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [newBucket, setNewBucket] = useState("");
  const [newLocation, setNewLocation] = useState("US");
  const [useAsDefault, setUseAsDefault] = useState(true);
  const [createdBuckets, setCreatedBuckets] = useState<string[]>([]);
  const config = { endpoint: endpoint.trim() || null, region: region.trim() || null, project_id: projectId.trim() || null,
    buckets: allowAll ? [] : selected, default_bucket: bucket || null, default_prefix: prefix,
    partitioning, default_partition_values: partitionValues };
  const draft = () => ({ provider, config: { endpoint: config.endpoint, region: config.region, project_id: config.project_id, buckets: [], default_bucket: null, default_prefix: "" },
    ...(connection ? { connection_id: connection.id } : {}),
    ...(Object.values(credentials).some(Boolean) || !connection ? { credentials } : {}) });
  const discover = useMutation({ mutationFn: () => datalakeApi.discover(draft()),
    onSuccess: (data) => setAvailable(data.buckets) });
  const validateBucket = useMutation({ mutationFn: () => datalakeApi.discover({ ...draft(), bucket: manualBucket.trim() }),
    onSuccess: (data) => { setAvailable((list) => Array.from(new Set([...list, ...data.buckets])).sort());
      setSelected((list) => Array.from(new Set([...list, ...data.buckets]))); setManualBucket(""); } });
  const createBucket = useMutation({ mutationFn: () => datalakeApi.createBucket({ ...draft(), bucket: newBucket.trim(),
    ...(provider === "gcs" ? { location: newLocation.trim() } : {}) }),
    onSuccess: async (data) => {
      setAvailable((list) => Array.from(new Set([...list, data.bucket])).sort());
      setSelected((list) => Array.from(new Set([...list, data.bucket])));
      setCreatedBuckets((list) => [...list, data.bucket]);
      if (useAsDefault) setBucket(data.bucket);
      setFilter(""); setNewBucket(""); setShowCreate(false);
      await queryClient.invalidateQueries({ queryKey: ["datalake-buckets"] });
    } });
  const save = useMutation({ mutationFn: () => {
    const body = { name: name.trim(), config, ...(Object.values(credentials).some(Boolean) ? { credentials } : {}) };
    return connection ? datalakeApi.update(connection.id, body) : datalakeApi.create({ ...body, provider, credentials });
  }, onSuccess: async () => { setCredentials({}); await queryClient.invalidateQueries({ queryKey: ["datalake-buckets"] }); onSaved(); } });
  const busy = discover.isPending || validateBucket.isPending || createBucket.isPending || save.isPending;
  const bucketLabel = provider === "azure" ? "Containers (buckets)" : "Buckets";
  const candidates = Array.from(new Set([...available, ...selected, ...(bucket ? [bucket] : [])])).sort();
  const permitted = allowAll ? candidates : selected;
  const validDefault = (!bucket || permitted.includes(bucket)) && partitionValid;
  const fieldsReady = !!name.trim() && (provider !== "minio" || !!endpoint.trim()) &&
    ((!!connection && !Object.values(credentials).some(Boolean)) || CREDENTIAL_FIELDS[provider].filter((f) => !f.optional).every((f) => !!credentials[f.key]?.trim()));
  const bucketsReady = allowAll || (selected.length > 0 && selected.length <= 100);
  const toggleBucket = (value: string) => {
    setSelected((list) => list.includes(value) ? list.filter((b) => b !== value) : [...list, value]);
    if (!allowAll && bucket === value && selected.includes(value)) setBucket("");
  };
  const close = () => { setCredentials({}); onClose(); };
  const next = () => {
    save.reset();
    if (step === 0) { setAvailable([]); setStep(1); discover.mutate(); }
    else setStep((s) => Math.min(s + 1, 3));
  };
  return <Dialog open onOpenChange={(open) => { if (!open && !save.isPending && !createBucket.isPending) close(); }}>
    <DialogContent className="flex max-h-[90dvh] flex-col overflow-hidden sm:max-w-2xl">
      <DialogHeader><DialogTitle>{connection ? "Editar conexão" : "Nova conexão"}</DialogTitle>
        <DialogDescription>Conecte sua conta, veja os buckets e escolha os padrões para suas solicitações.</DialogDescription></DialogHeader>
      <ol aria-label="Etapas da configuração" className="grid shrink-0 grid-cols-4 gap-2">
        {STEPS.map((label, index) => <li key={label} aria-current={step === index ? "step" : undefined} className="min-w-0">
          <button type="button" disabled={busy || index >= step} onClick={() => setStep(index)} className={cn("flex w-full flex-col items-center gap-1 rounded-md p-2 text-xs", step === index ? "bg-primary/10 text-primary font-semibold" : "text-muted-foreground")}>
            <span className={cn("flex h-7 w-7 items-center justify-center rounded-full border", index < step && "border-primary bg-primary text-primary-foreground")}>{index < step ? <Check className="h-4 w-4" /> : index + 1}</span>{label}
          </button></li>)}
      </ol>
      <form className="flex min-h-0 flex-col gap-4" onSubmit={(e) => { e.preventDefault(); if (busy || (step === 0 ? !fieldsReady : step === 1 ? !bucketsReady : !validDefault)) return; if (step < 3) next(); else save.mutate(); }}>
        <div className="min-h-0 overflow-y-auto px-1 pb-1">
        <fieldset disabled={busy} className="min-w-0 space-y-4">
          <h2 className="text-lg font-semibold">{step + 1}. {STEPS[step]}</h2>
          {step === 0 && <>
            <div><Label htmlFor="datalake-name">Nome da conexão</Label><Input id="datalake-name" value={name} onChange={(e) => setName(e.target.value)} required maxLength={150} placeholder="Datalake da equipe" /></div>
            <div><Label htmlFor="datalake-provider">Provedor</Label><select id="datalake-provider" className={selectClass} value={provider} disabled={!!connection} onChange={(e) => { setProvider(e.target.value as DatalakeProvider); setCredentials({}); setEndpoint(""); setRegion(""); setProjectId(""); setAvailable([]); setSelected([]); setBucket(""); setShowCreate(false); setNewBucket(""); setCreatedBuckets([]); createBucket.reset(); }}>
              {Object.entries(PROVIDER_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
            {(provider === "s3" || provider === "minio") && <div className="grid gap-3 sm:grid-cols-2"><div><Label htmlFor="datalake-endpoint">Endpoint {provider === "s3" ? "(opcional)" : ""}</Label><Input id="datalake-endpoint" type="url" required={provider === "minio"} value={endpoint} onChange={(e) => setEndpoint(e.target.value)} placeholder={provider === "s3" ? "https://s3.amazonaws.com" : "https://minio.exemplo.com"} /></div><div><Label htmlFor="datalake-region">Região (opcional)</Label><Input id="datalake-region" value={region} onChange={(e) => setRegion(e.target.value)} /></div></div>}
            {provider === "gcs" && <div><Label htmlFor="datalake-project">Projeto GCP (opcional)</Label><Input id="datalake-project" value={projectId} onChange={(e) => setProjectId(e.target.value)} /></div>}
            {connection && <p className="text-sm text-muted-foreground">Deixe as credenciais vazias para manter as atuais.</p>}
            {CREDENTIAL_FIELDS[provider].map((field) => <div key={field.key}><Label htmlFor={"datalake-secret-" + field.key}>{field.label}{field.optional ? " (opcional)" : ""}</Label>
              {field.multiline ? <textarea id={"datalake-secret-" + field.key} className="min-h-32 w-full rounded-md border bg-background px-3 py-2 font-mono text-sm" value={credentials[field.key] ?? ""} onChange={(e) => setCredentials({ ...credentials, [field.key]: e.target.value })} required={!connection && !field.optional} autoComplete="off" spellCheck={false} />
                : <Input id={"datalake-secret-" + field.key} type="password" value={credentials[field.key] ?? ""} onChange={(e) => setCredentials({ ...credentials, [field.key]: e.target.value })} required={!connection && !field.optional} autoComplete="new-password" />}</div>)}
          </>}
          {step === 1 && <>
            <p className="text-sm text-muted-foreground">Selecione os {provider === "azure" ? "containers" : "buckets"} que poderão ser usados nesta conexão.</p>
            <div className="space-y-3 rounded-lg border p-3">
              <Button type="button" variant="outline" onClick={() => { setShowCreate((open) => !open); createBucket.reset(); }}><Plus className="h-4 w-4" />Criar bucket agora</Button>
              {showCreate && <>
                <div><Label htmlFor="datalake-new-bucket">{provider === "azure" ? "Nome do novo container" : "Nome do novo bucket"}</Label><Input id="datalake-new-bucket" value={newBucket} maxLength={provider === "gcs" ? 222 : 63} placeholder="meus-transcripts" onChange={(e) => { setNewBucket(e.target.value); createBucket.reset(); }} onKeyDown={(e) => { if (e.key === "Enter") e.preventDefault(); }} /><p className="mt-1 text-xs text-muted-foreground">Use letras minúsculas, números e hífens. Mínimo de 3 caracteres.</p></div>
                {provider === "gcs" ? <div><Label htmlFor="datalake-new-location">Localização GCP</Label><Input id="datalake-new-location" value={newLocation} maxLength={100} placeholder="southamerica-east1 ou US" onChange={(e) => { setNewLocation(e.target.value); createBucket.reset(); }} onKeyDown={(e) => { if (e.key === "Enter") e.preventDefault(); }} /><p className="mt-1 text-xs text-muted-foreground">Confirme a região ou multirregião antes de criar.</p></div> : <p className="text-xs text-muted-foreground">{provider === "azure" ? "O container será criado na conta Azure informada, com acesso privado." : `Região: ${region.trim() || "us-east-1"}. Para alterar, volte à etapa Conexão.`}</p>}
                <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={useAsDefault} onChange={(e) => setUseAsDefault(e.target.checked)} />Usar como bucket padrão</label>
                <p className="text-xs text-muted-foreground">A criação acontece agora na sua conta. Cancelar o assistente não apaga o bucket criado.</p>
                <Button type="button" disabled={newBucket.trim().length < 3 || (provider === "gcs" && !newLocation.trim()) || (!allowAll && selected.length >= 100)} onClick={() => createBucket.mutate()}>{createBucket.isPending && <Loader2 className="h-4 w-4 animate-spin" />}{createBucket.isPending ? "Criando…" : provider === "azure" ? "Criar container" : "Criar bucket"}</Button>
                {!allowAll && selected.length >= 100 && <p className="text-xs text-muted-foreground">Remova um bucket da seleção para incluir o novo.</p>}
                {createBucket.isError && <p role="alert" className="text-sm text-destructive">{formatApiError(createBucket.error)}</p>}
              </>}
            </div>
            <label className="flex items-start gap-2 rounded-lg border p-3 text-sm"><input type="checkbox" className="mt-1" checked={allowAll} onChange={(e) => { setAllowAll(e.target.checked); if (!e.target.checked && bucket && !selected.includes(bucket)) setBucket(""); }} /><span>Permitir todos os buckets acessíveis<span className="block text-xs text-muted-foreground">Inclui buckets futuros aos quais esta conta tenha acesso.</span></span></label>
            <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-sm font-medium">{bucketLabel} disponíveis ({candidates.length})</h3><Button type="button" variant="outline" size="sm" onClick={() => discover.mutate()}><RefreshCw className="h-4 w-4" />Atualizar lista</Button></div>
            {discover.isPending && <p role="status" className="flex items-center gap-2 text-sm"><Loader2 className="h-4 w-4 animate-spin" />Consultando os buckets da conta…</p>}
            {discover.isError && <p role="alert" className="text-sm text-destructive">{formatApiError(discover.error)}</p>}
            {discover.isSuccess && !available.length && <p role="status" className="text-sm text-muted-foreground">A conta não retornou buckets. Informe um nome abaixo para verificar o acesso.</p>}
            {!!candidates.length && <>
              <Input aria-label="Buscar buckets" placeholder="Buscar bucket…" value={filter} onChange={(e) => setFilter(e.target.value)} />
              {!allowAll && <div className="flex flex-wrap gap-2"><Button type="button" size="sm" variant="ghost" disabled={candidates.length > 100} onClick={() => setSelected(candidates)}>Selecionar todos</Button><Button type="button" size="sm" variant="ghost" onClick={() => { setSelected([]); setBucket(""); }}>Limpar seleção</Button><span className="self-center text-xs text-muted-foreground">{selected.length} selecionados</span></div>}
              <div aria-label="Buckets disponíveis" className="max-h-52 space-y-2 overflow-y-auto">{candidates.filter((b) => b.toLowerCase().includes(filter.toLowerCase())).map((b) => <label key={b} className="flex cursor-pointer items-center gap-3 rounded-lg border p-3 text-sm"><input type="checkbox" checked={allowAll || selected.includes(b)} disabled={allowAll} onChange={() => toggleBucket(b)} aria-label={`Permitir ${b}`} /><Database className="h-4 w-4 shrink-0 text-muted-foreground" /><span className="min-w-0 flex-1 break-all">{b}{!available.includes(b) && <span className="block text-xs text-muted-foreground">Configurado · não listado pela conta</span>}</span>{bucket === b && <span className="shrink-0 rounded bg-primary/10 px-2 py-1 text-xs text-primary">Padrão</span>}</label>)}</div>
            </>}
            <div className="space-y-2 rounded-lg bg-muted/40 p-3"><Label htmlFor="datalake-manual-bucket">Verificar outro bucket</Label><div className="flex gap-2"><Input id="datalake-manual-bucket" placeholder="nome-do-bucket" value={manualBucket} maxLength={255} onChange={(e) => { setManualBucket(e.target.value); validateBucket.reset(); }} /><Button type="button" variant="outline" disabled={!manualBucket.trim()} onClick={() => validateBucket.mutate()}>Verificar</Button></div><p className="text-xs text-muted-foreground">Use quando a conta permite acessar um bucket, mas não listar todos.</p>{validateBucket.isError && <p role="alert" className="text-sm text-destructive">{formatApiError(validateBucket.error)}</p>}</div>
            {!bucketsReady && <p className="text-xs text-muted-foreground">Selecione de 1 a 100 buckets ou permita todos os acessíveis.</p>}
          </>}
          {!!createdBuckets.length && <p role="status" className="break-words rounded-lg bg-primary/10 p-3 text-sm">Criado nesta conta: {createdBuckets.join(", ")}. O bucket permanecerá no provedor mesmo se você cancelar a configuração.</p>}
          {step === 2 && <>
            <p className="text-sm text-muted-foreground">Estes valores serão preenchidos ao escolher a conexão. Você poderá alterá-los em cada solicitação.</p>
            <div><Label htmlFor="datalake-default-bucket">Bucket padrão (opcional)</Label><select id="datalake-default-bucket" className={selectClass} value={bucket} onChange={(e) => setBucket(e.target.value)}><option value="">Escolher na solicitação</option>{permitted.map((b) => <option key={b} value={b}>{b}</option>)}</select></div>
            <div><Label htmlFor="datalake-default-prefix">Pasta padrão (opcional)</Label><Input id="datalake-default-prefix" value={prefix} maxLength={700} onChange={(e) => setPrefix(e.target.value)} placeholder="resultados/" /></div>
            <PartitionEditor value={partitioning} onChange={(value) => { setPartitioning(value); setPartitionValues((values) => activePartitionValues(value, values, partitioning)); setPartitionValid(false); }} />
            <PartitionValuesFields strategy={partitioning} values={partitionValues} onChange={setPartitionValues} />
            <PartitionPreview demo input={{ partitioning, prefix, partition_values: partitionValues }} onValid={setPartitionValid} />
          </>}
          {step === 3 && <>
            <p className="text-sm text-muted-foreground">Confira as escolhas antes de salvar.</p>
            <dl className="space-y-3 rounded-lg border p-4 text-sm">{[["Conexão", name], ["Provedor", PROVIDER_LABELS[provider]], ...(endpoint ? [["Endpoint", endpoint]] : []), ["Buckets permitidos", allowAll ? "Todos os acessíveis" : selected.join(", ")], ["Bucket padrão", bucket || "Escolher na solicitação"], ["Pasta padrão", prefix || "Raiz do bucket"]].map(([label, value]) => <div key={label}><dt className="text-muted-foreground">{label}</dt><dd className="break-all font-medium">{value}</dd></div>)}</dl>
            <p className="text-xs text-muted-foreground">As credenciais são criptografadas no servidor. A conexão só será salva ao confirmar esta etapa.</p>
            <p className="text-sm">Particionamento: {PARTITION_LABELS[partitioning.mode]} · {partitioning.timezone} · {partitioning.analytics === "jsonl" ? "Dataset JSONL" : "Arquivos de resultado"}</p>
            {partitioning.mode !== "none" && <div className="space-y-1 text-xs text-muted-foreground"><p>Ordem: {partitioning.fields.map((field) => field.key || field.field).join(" → ")} · Data: {{ month: "mês", day: "dia", hour: "hora" }[partitioning.granularity]}</p><p>Valores ausentes: {partitioning.missing === "require" ? "exigir preenchimento" : `usar ${partitioning.fallback}`}</p></div>}
            <PartitionPreview demo input={{ partitioning, prefix, partition_values: partitionValues }} onValid={setPartitionValid} />
          </>}
          {save.isError && <p role="alert" className="text-sm text-destructive">{formatApiError(save.error)}</p>}
        </fieldset>
        </div>
        <div className="relative z-10 flex shrink-0 flex-wrap items-center justify-between gap-2 border-t bg-background pt-4"><Button type="button" variant="ghost" disabled={save.isPending || createBucket.isPending} onClick={close}>Cancelar</Button><div className="flex gap-2">{step > 0 && <Button type="button" variant="outline" disabled={busy} onClick={() => setStep((s) => s - 1)}><ArrowLeft className="h-4 w-4" />Voltar</Button>}
          <Button type="submit" disabled={busy || (step === 0 ? !fieldsReady : step === 1 ? !bucketsReady : !validDefault)}>{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}{step === 3 ? (save.isPending ? "Salvando…" : "Salvar conexão") : step === 0 ? "Ver buckets" : "Continuar"}{step < 3 && <ArrowRight className="h-4 w-4" />}</Button></div></div>
      </form>
    </DialogContent>
  </Dialog>;
}
