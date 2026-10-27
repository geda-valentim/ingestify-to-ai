"use client";
import { featureReplicas, type FeatureReplicas } from "@/lib/engine-replicas";
import type { RuntimeStatus } from "@/types/engine-control";

const n = (v: number | null) => (v == null ? "—" : String(v));
const modeLabel: Record<string, string> = { stopped: "parada", standby: "standby" };

function desiredCell(r: FeatureReplicas) {
  if (r.desired == null) return `0 (${modeLabel[r.mode ?? ""] ?? r.mode})`;
  return String(r.desired);
}

function appliedCell(r: FeatureReplicas) {
  const applied = r.appliedRevision == null ? "nenhuma" : `revisão ${r.appliedRevision}`;
  return r.appliedRevision === r.desiredRevision
    ? applied
    : `${applied} · revisão ${r.desiredRevision} salva, não aplicada`;
}

/** Desired, applied and observed replicas per feature, then per resource. */
export function EngineReplicas({ status }: { status: RuntimeStatus | undefined }) {
  const rows = featureReplicas(status);
  return (
    <>
      {rows.length > 0 && (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-muted-foreground">
              <th className="text-left font-medium">Feature</th>
              <th className="text-left font-medium">Desejadas</th>
              <th className="text-left font-medium">Aplicada</th>
              <th className="text-left font-medium">Vivas</th>
              <th className="text-left font-medium">Com modelo pronto</th>
              <th className="text-left font-medium">Observado</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.feature} className="border-t">
                <td className="py-1">{r.feature}</td>
                <td className="py-1">{desiredCell(r)}</td>
                <td className="py-1">{appliedCell(r)}</td>
                <td className="py-1">{n(r.alive)}</td>
                <td className="py-1">{n(r.ready)}</td>
                <td className="py-1">
                  {r.observedAt
                    ? new Date(r.observedAt + "Z").toLocaleString()
                    : "desconhecido"}
                  {r.busy && " · operação em curso"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {status?.resources.map((r) => (
        <div key={r.key} className="rounded border p-3 text-sm">
          <div className="break-all font-mono text-xs">{r.key}</div>
          <p>
            {r.maintenance ? "Em manutenção" : "Admissão disponível"} ·{" "}
            {String(r.observed.replicas_alive ?? "—")} vivas /{" "}
            {String(r.observed.ready_replicas ?? "—")} com modelo pronto
          </p>
        </div>
      ))}
    </>
  );
}
