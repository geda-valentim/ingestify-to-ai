"use client";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type {
  RuntimeProfile,
  Capabilities,
  ModelProfile,
} from "@/types/engine-control";
export const settingsSelectClass =
  "h-10 w-full rounded-md border bg-background px-3 text-sm";
export function defaultRuntime(): RuntimeProfile {
  return {
    adapter_version: 1,
    schema_version: 1,
    binding: { workers: 1, executions_per_worker: 1, cpu: 1 },
    model_profile_id: "",
    desired_replicas: 1,
    max_replicas: 1,
    min_ready_replicas: 0,
    idle_timeout_seconds: 60,
    memory_mb: 1024,
    warmup_mode: "on_start",
    warm_until: null,
    provider_settings: {},
  };
}
export function RuntimeSettingsFields({
  value,
  onChange,
  descriptor,
  models,
  hosts = [],
  gpuOptions = [],
  localGpus = [],
}: {
  value: RuntimeProfile;
  onChange: (value: RuntimeProfile) => void;
  descriptor?: Capabilities;
  models: ModelProfile[];
  hosts?: { id: string }[];
  gpuOptions?: { gpu_type: string }[];
  localGpus?: { ref: string; name?: string }[];
}) {
  const form = value;
  const update = (patch: Partial<RuntimeProfile>) =>
    onChange({ ...form, ...patch });
  const binding = (patch: Partial<RuntimeProfile["binding"]>) =>
    update({ binding: { ...form.binding, ...patch } });
  const provider = (name: string, v: unknown) =>
    update({ provider_settings: { ...form.provider_settings, [name]: v } });
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div>
        <Label htmlFor="control-model">Modelo aprovado</Label>
        <select
          id="control-model"
          className={settingsSelectClass}
          value={form.model_profile_id}
          onChange={(e) => update({ model_profile_id: e.target.value })}
        >
          <option value="">Selecione</option>
          {models.map((m) => (
            <option key={m.id} value={m.id} disabled={!m.approved}>
              {m.title}
              {!m.approved ? " (indisponível)" : ""}
            </option>
          ))}
        </select>
      </div>
      {descriptor?.fields.map((f) => (
        <div key={f.name}>
          <Label htmlFor={`control-${f.name}`}>{f.label}</Label>
          <Input
            id={`control-${f.name}`}
            type={f.type === "number" ? "number" : "text"}
            min={f.min}
            max={f.max}
            value={String(form[f.name as keyof RuntimeProfile] ?? "")}
            onChange={(e) => {
              const patch: Partial<RuntimeProfile> = {
                [f.name]:
                  f.type === "number" ? Number(e.target.value) : e.target.value,
              };
              if (f.name === "max_replicas")
                patch.binding = {
                  ...form.binding,
                  workers: Number(e.target.value),
                };
              update(patch);
            }}
          />
        </div>
      ))}
      {descriptor?.provider_fields.map((f) => (
        <div key={f.name}>
          <Label htmlFor={`provider-${f.name}`}>{f.label}</Label>
          {f.name === "host_id" || f.type === "select" ? (
            <select
              id={`provider-${f.name}`}
              className={settingsSelectClass}
              value={String(form.provider_settings[f.name] ?? "")}
              onChange={(e) => provider(f.name, e.target.value)}
            >
              <option value="">Selecione</option>
              {f.name === "host_id"
                ? hosts.map((h) => <option key={h.id}>{h.id}</option>)
                : f.options?.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
            </select>
          ) : (
            <Input
              id={`provider-${f.name}`}
              type={f.type === "number" ? "number" : "text"}
              min={f.min}
              max={f.max}
              value={String(form.provider_settings[f.name] ?? "")}
              onChange={(e) =>
                provider(
                  f.name,
                  f.type === "number" ? Number(e.target.value) : e.target.value,
                )
              }
            />
          )}
        </div>
      ))}
      <div>
        <Label htmlFor="control-cpu">CPU por worker</Label>
        <Input
          id="control-cpu"
          type="number"
          min="0.25"
          max="256"
          step="0.25"
          value={form.binding.cpu ?? ""}
          onChange={(e) =>
            binding({
              cpu: e.target.value ? Number(e.target.value) : undefined,
            })
          }
        />
      </div>
      <div>
        <Label htmlFor="control-memory">Memória por worker em MiB</Label>
        <Input
          id="control-memory"
          type="number"
          min="256"
          max="262144"
          value={form.memory_mb ?? ""}
          onChange={(e) =>
            update({
              memory_mb: e.target.value ? Number(e.target.value) : null,
            })
          }
        />
      </div>
      <div>
        <Label htmlFor="control-concurrency">Execuções por worker</Label>
        <Input
          id="control-concurrency"
          type="number"
          min="1"
          max="100"
          value={form.binding.executions_per_worker}
          onChange={(e) =>
            binding({ executions_per_worker: Number(e.target.value) })
          }
        />
      </div>
      <div>
        <Label htmlFor="control-gpu">GPU</Label>
        {gpuOptions.length || localGpus.length ? (
          <select
            id="control-gpu"
            className={settingsSelectClass}
            value={form.binding.gpu_type || form.binding.gpu_ref || ""}
            onChange={(e) =>
              binding({
                gpu_type: gpuOptions.length
                  ? e.target.value || undefined
                  : undefined,
                gpu_ref: gpuOptions.length
                  ? undefined
                  : e.target.value || undefined,
              })
            }
          >
            <option value="">CPU / padrão do adapter</option>
            {gpuOptions.map((g) => (
              <option key={g.gpu_type}>{g.gpu_type}</option>
            ))}
            {localGpus.map((g) => (
              <option key={g.ref} value={g.ref}>
                {g.name || g.ref}
              </option>
            ))}
          </select>
        ) : (
          <Input
            id="control-gpu"
            placeholder="Referência da GPU na engine (opcional)"
            value={form.binding.gpu_ref || ""}
            onChange={(e) => binding({ gpu_ref: e.target.value || undefined })}
          />
        )}
      </div>
      <div>
        <Label htmlFor="warmup-mode">Warmup</Label>
        <select
          id="warmup-mode"
          className={settingsSelectClass}
          value={form.warmup_mode}
          onChange={(e) =>
            update({
              warmup_mode: e.target.value as RuntimeProfile["warmup_mode"],
            })
          }
        >
          <option value="on_start">Ao iniciar</option>
          <option value="manual">Manual</option>
        </select>
      </div>
    </div>
  );
}
