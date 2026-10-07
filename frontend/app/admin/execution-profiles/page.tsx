"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import {
  RuntimeSettingsFields,
  defaultRuntime,
  settingsSelectClass as selectClass,
} from "@/components/admin/runtime-settings-fields";
import { accessApi } from "@/lib/access-api";
import { computeApi } from "@/lib/api";
import { engineControlApi } from "@/lib/engine-control-api";
import type { ExecutionProfile, ExecutionRevision } from "@/types/access";
import type { RuntimeProfile } from "@/types/engine-control";
import { AdminError } from "@/components/admin/admin-error";
export default function ExecutionProfilesPage() {
  const access = useQuery({ queryKey: ["access-me"], queryFn: accessApi.me });
  const list = useQuery({
    queryKey: ["execution-profiles"],
    queryFn: accessApi.profiles,
  });
  const descriptors = useQuery({
    queryKey: ["control", "adapters"],
    queryFn: engineControlApi.adapters,
  });
  const models = useQuery({
    queryKey: ["control", "models"],
    queryFn: engineControlApi.models,
  });
  const adapters = useQuery({
    queryKey: ["admin", "adapters"],
    queryFn: computeApi.adapters,
  });
  const hosts = useQuery({
    queryKey: ["execution-hosts"],
    queryFn: accessApi.hosts,
  });
  const [selected, setSelected] = useState("");
  const detail = useQuery({
    queryKey: ["execution-profile", selected],
    queryFn: () => accessApi.profile(selected),
    enabled: !!selected,
  });
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [adapter, setAdapter] = useState("local");
  const [feature, setFeature] = useState("transcription");
  const [environment, setEnvironment] = useState("development");
  const [form, setForm] = useState<RuntimeProfile>(defaultRuntime());
  const [warm, setWarm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [contextEngine, setContextEngine] = useState("");
  const [editing, setEditing] = useState(false);
  const engine = useQuery({
    queryKey: ["admin", "engine", contextEngine],
    queryFn: () => computeApi.engine(contextEngine),
    enabled: !!contextEngine,
  });
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setContextEngine(params.get("engine_id") || "");
    setFeature(params.get("feature") || "transcription");
  }, []);
  useEffect(() => {
    if (engine.data) setAdapter(engine.data.adapter_type);
  }, [engine.data]);
  useEffect(() => {
    const allowed = descriptors.data;
    if (!allowed?.length) return;
    const d = allowed.find((d) => d.type === adapter) || allowed[0];
    if (d.type !== adapter) {
      setAdapter(d.type);
      setForm(defaultRuntime());
    }
    if (!d.features.includes(feature)) {
      setFeature(d.features[0] || "");
      setForm(defaultRuntime());
    }
  }, [descriptors.data, adapter, feature]);
  const descriptor = descriptors.data?.find((d) => d.type === adapter);
  const canCreate =
    access.data?.bootstrap ||
    access.data?.permissions.includes("execution_profiles.create");
  function load(p: ExecutionProfile, r?: ExecutionRevision) {
    setName(p.name);
    setDescription(p.description);
    setAdapter(p.adapter_type);
    setFeature(p.feature);
    setEnvironment(p.environment);
    if (r) {
      setForm({ ...r.settings, warm_until: null });
      setWarm(r.warm_for_seconds?.toString() || "");
    }
    setEditing(true);
  }
  async function perform(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      await list.refetch();
      if (selected) await detail.refetch();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  function body() {
    return {
      name,
      description,
      adapter_type: adapter,
      feature,
      environment,
      settings: { ...form, warm_until: null },
      warm_for_seconds: warm ? Number(warm) : null,
    };
  }
  const p = detail.data;
  const gpuOptions = adapters.data?.find(
    (a) => a.type === adapter,
  )?.gpu_options;
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold">Perfis de execução</h2>
        <p className="text-muted-foreground">
          Biblioteca de configurações publicadas para vincular às engines.
          Publicar não aplica nem inicia recursos.
        </p>
        {contextEngine && (
          <Link
            href={`/admin/engines/${contextEngine}`}
            className="underline text-sm"
          >
            Voltar à engine
          </Link>
        )}
      </div>
      {!access.data?.enabled && (
        <p role="status">
          A biblioteca requer IAM_MODE=enforce (ou ENGINE_ACCESS_ENABLED=true) e
          as migrações 0009 e 0018. Consulte o runbook.
        </p>
      )}
      {(error != null || list.error) && (
        <AdminError
          error={error ?? list.error}
          fallback="Falha ao salvar"
          actions={{
            reload: () => {
              setError(null);
              list.refetch();
            },
          }}
        />
      )}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Biblioteca</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {canCreate && (
              <Button
                variant="outline"
                onClick={() => {
                  setSelected("");
                  setName("");
                  setDescription("");
                  setForm(defaultRuntime());
                  setWarm("");
                  setEditing(true);
                }}
              >
                Novo perfil
              </Button>
            )}
            {list.data?.map((item) => (
              <button
                key={item.id}
                className="block w-full rounded-md border p-3 text-left hover:bg-muted"
                onClick={() => {
                  setSelected(item.id);
                  setEditing(false);
                }}
              >
                <strong>{item.name}</strong>
                <p className="text-sm text-muted-foreground">
                  {item.adapter_type} · {item.feature} · {item.environment} ·{" "}
                  {item.status}
                </p>
              </button>
            ))}
            {list.data?.length === 0 && (
              <p>Nenhum perfil acessível. Crie o primeiro perfil.</p>
            )}
          </CardContent>
        </Card>
        {p && !editing && (
          <Card>
            <CardHeader>
              <CardTitle>{p.name}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p>{p.description}</p>
              <p className="text-sm">
                {p.adapter_type} · {p.feature} · {p.environment} · versão{" "}
                {p.version}
              </p>
              <div className="flex flex-wrap gap-2">
                {p.permissions.includes("update") &&
                  p.status !== "archived" && (
                    <Button onClick={() => load(p, p.revisions?.[0])}>
                      Nova revisão
                    </Button>
                  )}
                {canCreate && (
                  <Button
                    variant="outline"
                    onClick={() => {
                      load(p, p.revisions?.[0]);
                      setSelected("");
                      setName(`${p.name} (cópia)`);
                    }}
                  >
                    Clonar
                  </Button>
                )}
                {p.permissions.includes("archive") &&
                  p.status !== "archived" && (
                    <Button
                      variant="outline"
                      disabled={busy}
                      onClick={() => perform(() => accessApi.archive(p))}
                    >
                      Arquivar
                    </Button>
                  )}
              </div>
              {p.revisions?.map((r) => (
                <div key={r.id} className="rounded-md border p-3 space-y-2">
                  <p className="font-medium">
                    Revisão {r.revision} ·{" "}
                    {r.published_at ? "Publicada" : "Rascunho"}
                  </p>
                  <p className="text-sm">
                    {r.settings.model_profile_id} · {r.settings.max_replicas}{" "}
                    workers · E={r.settings.binding.executions_per_worker}
                  </p>
                  <p className="text-sm">
                    CPU {r.settings.binding.cpu ?? "padrão"} · memória{" "}
                    {r.settings.memory_mb ?? "padrão"} MiB · warmup{" "}
                    {r.warm_for_seconds ?? 0}s
                  </p>
                  {!r.published_at &&
                    p.permissions.includes("publish") &&
                    p.status !== "archived" && (
                      <Button
                        disabled={busy}
                        onClick={() =>
                          perform(() => accessApi.publish(p, r.id))
                        }
                      >
                        Publicar revisão {r.revision}
                      </Button>
                    )}
                </div>
              ))}
              <h3 className="font-medium">Vínculos acessíveis</h3>
              {p.bindings?.length ? (
                p.bindings.map((b, i) => (
                  <p key={i} className="text-sm">
                    <Link
                      className="underline"
                      href={`/admin/engines/${b.engine_id}`}
                    >
                      {b.engine_id}
                    </Link>{" "}
                    · {b.feature} · desejado r{b.revision} ·{" "}
                    {b.applied_at ? "aplicado" : "não aplicado"}
                  </p>
                ))
              ) : (
                <p className="text-sm">Nenhum vínculo.</p>
              )}
            </CardContent>
          </Card>
        )}
      </div>
      {(editing || (!selected && canCreate)) && (
        <Card>
          <CardHeader>
            <CardTitle>
              {selected ? "Criar revisão imutável" : "Criar perfil de execução"}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <form
              className="space-y-4"
              onSubmit={(e) => {
                e.preventDefault();
                perform(async () => {
                  const result =
                    selected && p
                      ? await accessApi.revise(selected, {
                          version: p.version,
                          settings: form,
                          warm_for_seconds: warm ? Number(warm) : null,
                        })
                      : await accessApi.create(body());
                  setSelected(result.id);
                  setEditing(false);
                });
              }}
            >
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <Label htmlFor="profile-name">Nome</Label>
                  <Input
                    id="profile-name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    required
                    maxLength={100}
                    disabled={!!selected}
                  />
                </div>
                <div>
                  <Label htmlFor="profile-description">Descrição</Label>
                  <Input
                    id="profile-description"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    maxLength={1000}
                    disabled={!!selected}
                  />
                </div>
                <div>
                  <Label htmlFor="profile-adapter">Provider</Label>
                  <select
                    id="profile-adapter"
                    className={selectClass}
                    value={adapter}
                    disabled={!!selected}
                    onChange={(e) => {
                      setAdapter(e.target.value);
                      setForm(defaultRuntime());
                    }}
                  >
                    {descriptors.data?.map((d) => (
                      <option key={d.type} value={d.type}>
                        {d.title}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <Label htmlFor="profile-feature">Feature</Label>
                  <select
                    id="profile-feature"
                    className={selectClass}
                    value={feature}
                    disabled={!!selected}
                    onChange={(e) => {
                      setFeature(e.target.value);
                      setForm(defaultRuntime());
                    }}
                  >
                    {descriptor?.features.map((f) => (
                      <option key={f}>{f}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <Label htmlFor="profile-environment">Ambiente</Label>
                  <select
                    id="profile-environment"
                    className={selectClass}
                    value={environment}
                    disabled={!!selected}
                    onChange={(e) => setEnvironment(e.target.value)}
                  >
                    {["development", "staging", "production"].map((env) => (
                      <option key={env}>{env}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <Label htmlFor="profile-warm">
                    Duração aquecida (segundos)
                  </Label>
                  <Input
                    id="profile-warm"
                    type="number"
                    min="1"
                    max="86400"
                    placeholder="Sem prazo"
                    value={warm}
                    onChange={(e) => setWarm(e.target.value)}
                  />
                </div>
              </div>
              <RuntimeSettingsFields
                value={form}
                onChange={setForm}
                descriptor={descriptor}
                models={
                  models.data?.filter(
                    (m) =>
                      m.adapters.includes(adapter) && m.feature === feature,
                  ) || []
                }
                hosts={hosts.data || []}
                gpuOptions={Array.isArray(gpuOptions) ? gpuOptions : []}
                localGpus={engine.data?.config.gpus || []}
              />
              <Button
                type="submit"
                disabled={busy || !form.model_profile_id || !name.trim()}
              >
                {selected ? "Salvar nova revisão" : "Salvar rascunho"}
              </Button>
              {contextEngine && access.data?.bootstrap && !selected && (
                <Button
                  type="button"
                  variant="outline"
                  disabled={busy || !name.trim() || !form.model_profile_id}
                  onClick={() =>
                    perform(async () => {
                      const imported = await accessApi.import(
                        contextEngine,
                        body(),
                      );
                      setSelected(imported.id);
                      setEditing(false);
                    })
                  }
                >
                  Importar desejado legado como rascunho
                </Button>
              )}
            </form>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
