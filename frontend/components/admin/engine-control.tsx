"use client";
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  engineControlApi as api,
  createIdempotencyKey,
} from "@/lib/engine-control-api";
import { computeApi } from "@/lib/api";
import { RuntimeSettingsFields } from "./runtime-settings-fields";
import { ExecutionProfileBinding } from "./execution-profile-binding";
import { AdminError } from "./admin-error";
import { guidedOperationError } from "@/lib/admin-errors";
import { useAuthStore } from "@/lib/store/auth";
import type { Engine, Feature } from "@/types/compute";
import type {
  RuntimeProfile,
  ControlPlan,
  Operation,
  OperationEvent,
} from "@/types/engine-control";

const labels: Record<string, string> = {
  test: "Testar",
  reconcile: "Reconciliar gasto",
  deploy: "Deploy",
  start: "Iniciar",
  drain_stop: "Drenar e parar",
  restart: "Reiniciar",
  scale: "Aplicar escala",
  warmup: "Aquecer",
  cooldown: "Liberar modelo",
  apply_profile: "Aplicar perfil",
  benchmark: "Benchmark",
};
const terminal = new Set([
  "succeeded",
  "failed",
  "cancelled",
  "needs_attention",
]);
const selectClass = "h-10 w-full rounded-md border bg-background px-3 text-sm";
const localDatetime = (value: string) => {
  const date = new Date(value);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
};

export function EngineControl({
  engine,
  onChanged,
}: {
  engine: Engine;
  onChanged: () => void;
}) {
  const client = useQueryClient();
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const libraryEnabled = user?.engine_access_enabled;
  const canCreateProfile =
    !!user?.is_admin ||
    !!user?.permissions?.includes("execution_profiles.create");
  const [tab, setTab] = useState("overview");
  const [feature, setFeature] = useState("transcription");
  const [form, setForm] = useState<RuntimeProfile | null>(null);
  const [plan, setPlan] = useState<ControlPlan | null>(null);
  const [operation, setOperation] = useState<string | null>(null);
  const [maxUsd, setMaxUsd] = useState("0.10");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const key = useRef<string | null>(null);
  const discovered = useQuery({
    queryKey: ["control", "discover", engine.id],
    queryFn: () => api.capabilities(engine.id),
  });
  useEffect(() => {
    const fs = discovered.data?.features;
    if (fs?.length && !fs.includes(feature)) setFeature(fs[0]);
  }, [discovered.data, feature]);
  const featureReady =
    !libraryEnabled || !!discovered.data?.features.includes(feature);
  const caps = useQuery({
    queryKey: ["control", "caps", engine.id, feature],
    queryFn: () => api.capabilities(engine.id, feature),
    enabled: featureReady,
    refetchInterval: 10000,
  });
  const models = useQuery({
    queryKey: ["control", "models"],
    queryFn: api.models,
  });
  const profile = useQuery({
    queryKey: ["control", "profile", engine.id, feature],
    queryFn: () => api.profile(engine.id, feature),
    enabled: featureReady,
  });
  const runtime = useQuery({
    queryKey: ["control", "runtime", engine.id],
    queryFn: () => api.status(engine.id),
    refetchInterval: 5000,
  });
  const history = useQuery({
    queryKey: ["control", "history", engine.id],
    queryFn: () => api.history(engine.id),
    refetchInterval: 5000,
  });
  const adapters = useQuery({
    queryKey: ["admin", "adapters"],
    queryFn: computeApi.adapters,
  });
  const d = caps.data;
  const selectableFeatures = discovered.data?.features || d?.features || [];
  const setup = d?.setup;
  // Disabled actions explained once per reason, except the setup reason shown above.
  const blocked = Object.values(
    (d?.actions || [])
      .filter((a) => !a.enabled && a.reason && a.reason !== setup?.code)
      .reduce<Record<string, { reason: string; message: string; types: string[] }>>(
        (acc, a) => {
          const r = a.reason as string;
          acc[r] = acc[r] || { reason: r, message: a.message || r, types: [] };
          acc[r].types.push(labels[a.type] || a.type);
          return acc;
        },
        {},
      ),
  );
  const availableModels = models.data?.filter(
    (p) => p.feature === feature && p.adapters.includes(engine.adapter_type),
  );
  useEffect(() => {
    if (!featureReady || !models.data || profile.isLoading) return;
    const saved = profile.data?.profile;
    const binding = saved?.binding ||
      engine.features[feature as Feature]?.binding || {
        workers: 1,
        executions_per_worker: 1,
      };
    setForm({
      adapter_version: 1,
      schema_version: 1,
      binding,
      model_profile_id:
        saved?.model_profile_id ||
        availableModels?.find((p) => p.approved)?.id ||
        "",
      desired_replicas: saved?.desired_replicas ?? binding.workers,
      max_replicas: saved?.max_replicas ?? binding.workers,
      min_ready_replicas: saved?.min_ready_replicas ?? 0,
      idle_timeout_seconds: saved?.idle_timeout_seconds ?? 60,
      warmup_mode: saved?.warmup_mode ?? "on_start",
      warm_until: saved?.warm_until ?? null,
      memory_mb: saved?.memory_mb ?? null,
      provider_settings: saved?.provider_settings || {},
    });
    setPlan(null);
    // Reset on the selected saved revision, not every background engine poll.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    feature,
    featureReady,
    profile.data?.revision,
    profile.isLoading,
    models.data,
  ]);
  useEffect(() => {
    if (!operation && history.data?.operations[0])
      setOperation(history.data.operations[0].operation_id);
  }, [history.data, operation]);
  const refresh = async () => {
    onChanged();
    await client.invalidateQueries({ queryKey: ["control"] });
  };
  const perform = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  async function save() {
    if (!form) return;
    await api.save(engine.id, feature, engine.version, form);
    setPlan(null);
    await refresh();
  }
  async function preview(action: string) {
    const p = await api.plan(engine.id, {
      type: action,
      feature,
      engine_version: engine.version,
      profile_revision: profile.data?.revision,
      max_usd: maxUsd,
      drain_timeout_seconds: 900,
    });
    key.current = createIdempotencyKey();
    setPlan(p);
  }
  const testEnabled = !!d?.actions.find((a) => a.type === "test")?.enabled;
  const createProfileUrl = `/admin/execution-profiles?engine_id=${encodeURIComponent(engine.id)}&feature=${encodeURIComponent(feature)}`;
  // Next steps the page can perform directly (the others are shown as plain items).
  const stepActions: Partial<Record<string, () => void>> = {
    ...(testEnabled && { test_connection: () => perform(() => preview("test")) }),
    bind_profile: () => setTab("configuration"),
    ...(canCreateProfile && {
      create_profile: () =>
        libraryEnabled ? router.push(createProfileUrl) : setTab("configuration"),
    }),
    configure_credentials: () => setTab("configuration"),
    set_warm_until: () => setTab("configuration"),
    set_budget: () => setTab("operations"),
    reload: () => {
      setError(null);
      refresh();
    },
  };
  const visibleSteps = (steps: string[]) =>
    steps.filter((s) => s !== "create_profile" || canCreateProfile);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Operar engine</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {caps.error != null && (
          <AdminError
            error={caps.error}
            title="Não foi possível carregar as operações desta engine"
            actions={stepActions}
          />
        )}
        {error != null && <AdminError error={error} actions={stepActions} />}
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="flex flex-wrap h-auto justify-start">
            <TabsTrigger value="overview">Visão geral</TabsTrigger>
            <TabsTrigger value="configuration">Configuração</TabsTrigger>
            <TabsTrigger value="models">Modelos</TabsTrigger>
            <TabsTrigger value="operations">Operações</TabsTrigger>
          </TabsList>
          <TabsContent value="overview" className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Configuração desejada, perfil aplicado e observação do executor
              são estados separados.
            </p>
            <div className="grid gap-3 sm:grid-cols-3">
              <div>Desejado: revisão {profile.data?.revision ?? "—"}</div>
              <div>
                Aplicado:{" "}
                {runtime.data?.applied.find((p) => p.feature === feature)
                  ?.revision ?? "—"}
              </div>
              <div>
                Observado:{" "}
                {runtime.data?.resources[0]?.observed_at
                  ? new Date(
                      runtime.data.resources[0].observed_at + "Z",
                    ).toLocaleString()
                  : "desconhecido"}
              </div>
            </div>
            {runtime.data?.resources.map((r) => (
              <div key={r.key} className="rounded border p-3 text-sm">
                <div className="break-all font-mono text-xs">{r.key}</div>
                <p>
                  {r.maintenance ? "Em manutenção" : "Admissão disponível"} ·{" "}
                  {String(r.observed.replicas_alive ?? "—")} vivos /{" "}
                  {String(r.observed.ready_replicas ?? "—")} prontos
                </p>
              </div>
            ))}
            {setup?.message && (
              <AdminError
                tone="info"
                title={`Configuração necessária${setup.feature ? ` para ${setup.feature}` : ""}`}
                guided={{
                  message: setup.message,
                  nextSteps: visibleSteps(setup.next_steps),
                  code: setup.code ?? undefined,
                }}
                actions={stepActions}
              />
            )}
            <div className="flex flex-wrap gap-2">
              {d?.actions.map((a) => (
                <Button
                  key={a.type}
                  variant="outline"
                  disabled={busy || !a.enabled}
                  title={a.enabled ? labels[a.type] : a.message || a.reason || ""}
                  onClick={() => perform(() => preview(a.type))}
                >
                  {labels[a.type] || a.type}
                </Button>
              ))}
            </div>
            {blocked.length > 0 && (
              <ul className="space-y-1 text-sm text-muted-foreground">
                {blocked.map((b) => (
                  <li key={b.reason}>
                    <span className="font-medium">{b.types.join(", ")}:</span>{" "}
                    {b.message}{" "}
                    <span className="font-mono text-[11px]">({b.reason})</span>
                  </li>
                ))}
              </ul>
            )}
            {(!libraryEnabled || user?.is_admin) &&
              !!d?.credential_fields.length && (
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() =>
                    perform(async () => {
                      await api.quick(
                        engine.id,
                        engine.status === "active" ? "pause" : "activate",
                        engine.version,
                      );
                      await refresh();
                    })
                  }
                >
                  {engine.status === "active"
                    ? "Pausar novas colocações"
                    : "Ativar colocações"}
                </Button>
              )}
          </TabsContent>
          <TabsContent value="configuration" className="space-y-4">
            {libraryEnabled && featureReady && (
              <ExecutionProfileBinding
                engine={engine}
                feature={feature}
                onTestConnection={
                  testEnabled
                    ? () => {
                        setTab("overview");
                        perform(() => preview("test"));
                      }
                    : undefined
                }
                connectionVerified={setup?.connection_verified}
                onChanged={() => {
                  onChanged();
                  client.invalidateQueries({ queryKey: ["control"] });
                }}
              />
            )}
            <div>
              <Label htmlFor="control-feature">Feature</Label>
              <select
                id="control-feature"
                className={selectClass}
                value={feature}
                onChange={(e) => setFeature(e.target.value)}
              >
                {selectableFeatures.map((f) => (
                  <option key={f}>{f}</option>
                ))}
              </select>
            </div>
            {(!libraryEnabled || user?.is_admin) && (
              <>
                <p className="text-sm text-muted-foreground">
                  Configuração manual de bootstrap. Use a biblioteca para
                  compartilhar revisões publicadas.
                </p>
                {form && (
                  <RuntimeSettingsFields
                    value={form}
                    onChange={(v) => {
                      setForm(v);
                      setPlan(null);
                    }}
                    descriptor={d}
                    models={availableModels || []}
                    hosts={d?.hosts || []}
                    gpuOptions={(() => {
                      const opts = adapters.data?.find(
                        (a) => a.type === engine.adapter_type,
                      )?.gpu_options;
                      return Array.isArray(opts) ? opts : [];
                    })()}
                    localGpus={engine.config.gpus || []}
                  />
                )}
                <div>
                  <Label htmlFor="control-until">Manter aquecido até</Label>
                  <Input
                    id="control-until"
                    type="datetime-local"
                    value={
                      form?.warm_until ? localDatetime(form.warm_until) : ""
                    }
                    onChange={(e) =>
                      form &&
                      setForm({
                        ...form,
                        warm_until: e.target.value
                          ? new Date(e.target.value).toISOString()
                          : null,
                      })
                    }
                  />
                </div>
                <Button
                  disabled={busy || !form?.model_profile_id}
                  onClick={() => perform(save)}
                >
                  Salvar configuração desejada
                </Button>
                <p className="text-xs text-muted-foreground">
                  Salvar cria uma revisão. Revise e aplique uma operação para
                  alterar o runtime.
                </p>
              </>
            )}
            {d &&
            (user?.is_admin ||
              !libraryEnabled ||
              user?.permissions?.includes(
                "engine_connections.credentials.manage",
              )) &&
            (d.requires_budget || d.credential_fields.length) ? (
              <QuickConfiguration
                engine={engine}
                fields={d.credential_fields.map((f) => ({
                  name: f.name,
                  label: f.label,
                }))}
                onChanged={refresh}
                canBudget={!!user?.is_admin || !libraryEnabled}
              />
            ) : null}
          </TabsContent>
          <TabsContent value="models">
            <div className="space-y-3">
              {availableModels?.map((m) => (
                <div key={m.id} className="rounded border p-3">
                  <p>
                    {m.title} · {m.approved ? "Aprovado" : "Indisponível"}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {m.model} · footprint {m.footprint_gb ?? "não qualificado"}{" "}
                    GB
                  </p>
                </div>
              ))}
            </div>
          </TabsContent>
          <TabsContent value="operations">
            <div>
              <Label htmlFor="control-max-usd">
                Teto reservado por operação (US$)
              </Label>
              <Input
                id="control-max-usd"
                type="number"
                min="0"
                step="0.01"
                value={maxUsd}
                onChange={(e) => {
                  setMaxUsd(e.target.value);
                  setPlan(null);
                }}
              />
            </div>
            <div className="space-y-2">
              {history.error != null && (
                <AdminError
                  error={history.error}
                  title="Não foi possível carregar o histórico"
                />
              )}
              {history.data?.operations.map((op) => (
                <button
                  key={op.operation_id}
                  onClick={() => setOperation(op.operation_id)}
                  className="w-full rounded border p-3 text-left text-sm"
                >
                  {op.stage} · {op.state} ·{" "}
                  {new Date(op.created_at + "Z").toLocaleString()}
                </button>
              ))}
            </div>
          </TabsContent>
        </Tabs>
        {plan && (
          <section
            aria-label="Revisar operação"
            className="space-y-3 rounded border p-4"
          >
            <h3 className="font-medium">
              Revisar: {labels[plan.type] || plan.type}
            </h3>
            <p>
              Revisão {plan.profile_revision ?? "—"} · reserva máxima US${" "}
              {plan.estimated_max_usd}
            </p>
            {plan.destructive && (
              <p className="text-amber-700">
                Esta operação encerra o deployment. Voltar exige novo deploy.
              </p>
            )}
            <p className="text-sm">Etapas: {plan.stages.join(" → ")}</p>
            <ul className="text-xs font-mono break-all">
              {plan.resources.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
            <div className="flex gap-2">
              <Button
                disabled={busy}
                onClick={() =>
                  perform(async () => {
                    const op = await api.execute(engine.id, plan, key.current!);
                    setOperation(op.operation_id);
                    setPlan(null);
                    setTab("operations");
                    await refresh();
                  })
                }
              >
                Confirmar e executar
              </Button>
              <Button variant="outline" onClick={() => setPlan(null)}>
                Fechar revisão
              </Button>
            </div>
          </section>
        )}
        {operation && <OperationConsole id={operation} onFinished={refresh} />}
      </CardContent>
    </Card>
  );
}

function OperationConsole({
  id,
  onFinished,
}: {
  id: string;
  onFinished: () => Promise<void>;
}) {
  const [attempt, setAttempt] = useState(0);
  const [events, setEvents] = useState<OperationEvent[]>([]);
  const [autoScroll, setAutoScroll] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const seen = useRef<string | null>(null);
  const snapshot = useQuery({
    queryKey: ["control", "operation", id],
    queryFn: () => api.snapshot(id),
    refetchInterval: (q) =>
      q.state.data && terminal.has(q.state.data.state) ? false : 1000,
  });
  useEffect(() => {
    let stopped = false;
    let cursor = 0;
    setEvents([]);
    setError(null);
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const page = await api.events(id, cursor);
        if (stopped) return;
        cursor = page.next;
        setEvents((old) => [...old, ...page.events].slice(-500));
        setError(null);
        if (page.has_more || !terminal.has(page.state))
          timer = setTimeout(poll, page.has_more ? 0 : 1000);
      } catch (e) {
        if (!stopped) {
          setError(e);
          timer = setTimeout(poll, 3000);
        }
      }
    };
    poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [id, attempt]);
  useEffect(() => {
    if (autoScroll) bottom.current?.scrollIntoView({ block: "nearest" });
  }, [events, autoScroll]);
  useEffect(() => {
    if (
      snapshot.data &&
      terminal.has(snapshot.data.state) &&
      seen.current !== id
    ) {
      seen.current = id;
      onFinished();
    }
  }, [snapshot.data, id, onFinished]);
  const op = snapshot.data;
  return (
    <section aria-label="Console da operação" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-medium">
          {op?.stage ?? "Carregando"} · {op?.state ?? "—"}
        </h3>
        {op?.can_cancel && (
          <Button
            variant="outline"
            onClick={async () => {
              try {
                await api.cancel(id);
                snapshot.refetch();
              } catch (e) {
                setError(e);
              }
            }}
          >
            Solicitar cancelamento
          </Button>
        )}
      </div>
      {op?.state === "needs_attention" && (
        <Button
          variant="outline"
          disabled={!op.can_recover}
          onClick={async () => {
            try {
              await api.recover(id);
              seen.current = null;
              await snapshot.refetch();
              setAttempt((n) => n + 1);
            } catch (e) {
              setError(e);
            }
          }}
        >
          Reconciliar estado sem repetir operação
        </Button>
      )}
      {error != null && <AdminError error={error} />}
      {op?.error && (
        <AdminError
          title="A operação falhou"
          guided={guidedOperationError(op.error)}
        />
      )}
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={autoScroll}
          onChange={(e) => setAutoScroll(e.target.checked)}
        />
        Acompanhar últimos eventos
      </label>
      <div
        className="max-h-80 overflow-auto rounded bg-slate-950 p-3 font-mono text-xs text-slate-100"
        role="log"
        aria-live="polite"
      >
        {events.map((ev) => (
          <p key={ev.seq} className="whitespace-pre-wrap break-all">
            [{ev.seq}] {ev.stage}: {ev.payload.message || ev.type}
          </p>
        ))}
        <div ref={bottom} />
      </div>
      {op && (
        <p className="text-xs text-muted-foreground">
          Reservado: US$ {op.reserved_usd} · custo{" "}
          {op.cost_confirmed
            ? `confirmado: US$ ${op.actual_usd}`
            : "aguarda reconciliação"}
          . Fechar a página mantém a operação.
        </p>
      )}
    </section>
  );
}

function QuickConfiguration({
  engine,
  fields,
  onChanged,
  canBudget = true,
}: {
  engine: Engine;
  canBudget?: boolean;
  fields: { name: string; label: string }[];
  onChanged: () => Promise<void>;
}) {
  const [credentials, setCredentials] = useState<Record<string, string>>({});
  const [password, setPassword] = useState("");
  const [budget, setBudget] = useState(String(engine.budget.limit_usd ?? "30"));
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  async function submit(action: string, body: Record<string, unknown>) {
    setBusy(true);
    setError(null);
    try {
      await api.quick(engine.id, action, engine.version, body);
      setCredentials({});
      setPassword("");
      await onChanged();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="space-y-3 border-t pt-4">
      <h3 className="font-medium">Orçamento e credenciais</h3>
      {error != null && <AdminError error={error} />}
      {canBudget && (
        <>
          <Label htmlFor="engine-budget">Limite por período (US$)</Label>
          <Input
            id="engine-budget"
            type="number"
            min="0"
            value={budget}
            onChange={(e) => setBudget(e.target.value)}
          />
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => submit("budget", { limit_usd: budget })}
          >
            Salvar orçamento
          </Button>
        </>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        {fields.map((f) => (
          <div key={f.name}>
            <Label htmlFor={`credential-${f.name}`}>{f.label}</Label>
            <Input
              id={`credential-${f.name}`}
              type="password"
              autoComplete="new-password"
              value={credentials[f.name] || ""}
              placeholder={
                engine.credentials[f.name]?.is_set
                  ? "Configurada; valor oculto"
                  : "Não configurada"
              }
              onChange={(e) =>
                setCredentials({ ...credentials, [f.name]: e.target.value })
              }
            />
          </div>
        ))}
      </div>
      <Label htmlFor="credential-password">
        Sua senha para confirmar a troca
      </Label>
      <Input
        id="credential-password"
        type="password"
        autoComplete="current-password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />
      <Button
        variant="outline"
        disabled={busy || !password || fields.some((f) => !credentials[f.name])}
        onClick={() =>
          submit("credentials", {
            fields: credentials,
            current_password: password,
          })
        }
      >
        Salvar credenciais
      </Button>
    </div>
  );
}

export function CreateEngine() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [adapter, setAdapter] = useState("");
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const descriptors = useQuery({
    queryKey: ["control", "adapters"],
    queryFn: api.adapters,
  });
  return (
    <div>
      <Button onClick={() => setOpen(!open)} variant="outline">
        Adicionar engine
      </Button>
      {open && (
        <div className="mt-3 space-y-3 rounded border p-4">
          {error != null && <AdminError error={error} />}
          <Label htmlFor="new-adapter">Adapter</Label>
          <select
            id="new-adapter"
            className={selectClass}
            value={adapter}
            onChange={(e) => setAdapter(e.target.value)}
          >
            <option value="">Selecione</option>
            {descriptors.data
              ?.filter((d) => d.create_connection)
              .map((d) => (
                <option key={d.type} value={d.type}>
                  {d.title}
                </option>
              ))}
          </select>
          <Label htmlFor="new-name">Nome</Label>
          <Input
            id="new-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <Label htmlFor="new-slug">Identificador</Label>
          <Input
            id="new-slug"
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
          />
          <Button
            disabled={busy || !adapter || !slug || !name}
            onClick={async () => {
              setBusy(true);
              try {
                const e = await api.create({
                  adapter_type: adapter,
                  display_name: name,
                  slug,
                });
                router.push(`/admin/engines/${e.id}`);
              } catch (e) {
                setError(e);
              } finally {
                setBusy(false);
              }
            }}
          >
            Criar conexão pausada
          </Button>
        </div>
      )}
    </div>
  );
}
