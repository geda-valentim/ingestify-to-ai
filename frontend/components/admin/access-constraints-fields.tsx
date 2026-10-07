"use client";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { Constraints } from "@/types/access";
export const defaultConstraints = (): Constraints => ({
  engine_ids: [],
  profile_ids: null,
  adapters: [],
  features: [],
  environments: ["development"],
  host_ids: null,
  gpu_uuids: null,
  model_ids: null,
  max_replicas: 1,
  max_concurrency: 1,
  max_cpu: 1,
  max_memory_mb: 1024,
  max_warm_seconds: 0,
  max_usd: "0",
});
const scopes = [
  ["engine_ids", "IDs de engines", false],
  ["profile_ids", "IDs de perfis", true],
  ["adapters", "Adapters (local, modal…)", false],
  ["features", "Features (transcription, document_conversion…)", false],
  ["environments", "Ambientes (development, staging, production)", false],
  ["host_ids", "IDs de hosts", true],
  ["gpu_uuids", "UUIDs de GPUs físicas", true],
  ["model_ids", "IDs de modelos aprovados", true],
] as const;
const caps = [
  ["max_replicas", "Máximo de réplicas", 0, 100, "1"],
  ["max_concurrency", "Máximo de execuções por worker", 1, 100, "1"],
  ["max_cpu", "Máximo de CPU por worker", 0.25, 256, ".25"],
  ["max_memory_mb", "Máximo de memória por worker (MiB)", 256, 262144, "1"],
  ["max_warm_seconds", "Máximo de tempo aquecido (s)", 0, 86400, "1"],
  ["max_usd", "Máximo por operação (US$)", 0, 1000, ".01"],
] as const;
export function ConstraintsFields({
  value,
  onChange,
  prefix = "scope",
}: {
  value: Constraints;
  onChange: (v: Constraints) => void;
  prefix?: string;
}) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {scopes.map(([key, label, optional]) => (
        <div key={key}>
          <Label htmlFor={`${prefix}-${key}`}>{label}</Label>
          <Input
            id={`${prefix}-${key}`}
            value={value[key]?.join(", ") || ""}
            placeholder={
              optional
                ? "Vazio: sem restrição adicional"
                : "Vazio: nenhum recurso permitido"
            }
            onChange={(e) => {
              const ids = e.target.value
                .split(",")
                .map((x) => x.trim())
                .filter(Boolean);
              onChange({
                ...value,
                [key]: optional && !ids.length ? null : ids,
              });
            }}
          />
          <p className="text-xs text-muted-foreground">
            Separe por vírgula.{" "}
            {optional ? "A delegação também limita estes valores." : ""}
          </p>
        </div>
      ))}
      {caps.map(([key, label, min, max, step]) => (
        <div key={key}>
          <Label htmlFor={`${prefix}-${key}`}>{label}</Label>
          <Input
            id={`${prefix}-${key}`}
            type="number"
            min={min}
            max={max}
            step={step}
            value={String(value[key])}
            onChange={(e) =>
              onChange({
                ...value,
                [key]:
                  key === "max_usd" ? e.target.value : Number(e.target.value),
              })
            }
          />
        </div>
      ))}
    </div>
  );
}
