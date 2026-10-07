"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { accessApi } from "@/lib/access-api";
import { engineControlApi } from "@/lib/engine-control-api";
import { useAuthStore } from "@/lib/store/auth";
import type { Engine } from "@/types/compute";
import { settingsSelectClass } from "./runtime-settings-fields";
import { AdminError } from "./admin-error";
export function ExecutionProfileBinding({
  engine,
  feature,
  onChanged,
  onTestConnection,
  connectionVerified,
}: {
  engine: Engine;
  feature: string;
  onChanged: () => void;
  /** Runs the engine's "Testar" (records the provider identity binding requires). */
  onTestConnection?: () => void;
  /** false when the adapter needs a verified identity that is still missing. */
  connectionVerified?: boolean | null;
}) {
  const user = useAuthStore((s) => s.user);
  const router = useRouter();
  const canBind =
    user?.is_admin || user?.permissions?.includes("engine_runtime.bind");
  const canCreate =
    user?.is_admin || user?.permissions?.includes("execution_profiles.create");
  const [selected, setSelected] = useState("");
  const [revision, setRevision] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const list = useQuery({
    queryKey: ["execution-profiles"],
    queryFn: accessApi.profiles,
  });
  const detail = useQuery({
    queryKey: ["execution-profile", selected],
    queryFn: () => accessApi.profile(selected),
    enabled: !!selected,
  });
  const current = useQuery({
    queryKey: ["control", "profile", engine.id, feature],
    queryFn: () => engineControlApi.profile(engine.id, feature),
  });
  const choices = list.data?.filter(
    (p) =>
      p.adapter_type === engine.adapter_type &&
      p.feature === feature &&
      p.status !== "archived",
  );
  const chosen = detail.data?.revisions?.find((r) => r.id === revision);
  const createUrl = `/admin/execution-profiles?engine_id=${encodeURIComponent(engine.id)}&feature=${encodeURIComponent(feature)}`;
  async function bind() {
    setBusy(true);
    setError(null);
    try {
      // One attempt with the engine version reviewed by the user. Never refresh-and-retry a write.
      await accessApi.bind(engine.id, feature, engine.version, revision);
      await current.refetch();
      onChanged();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="rounded-md border p-4 space-y-3">
      <h3 className="font-semibold">Perfil de execução publicado</h3>
      <p className="text-sm text-muted-foreground">
        Vincular salva uma revisão desejada. Use uma operação para aplicar ao
        executor.
      </p>
      {connectionVerified === false && (
        <AdminError
          tone="info"
          title="Teste a conexão antes de vincular"
          guided={{
            message:
              "Esta engine precisa de uma conexão verificada com o provedor antes de receber um perfil. Use “Testar conexão”; depois escolha o perfil.",
            nextSteps: ["test_connection"],
            code: "TEST_CONNECTION_FIRST",
          }}
          actions={onTestConnection ? { test_connection: onTestConnection } : {}}
        />
      )}
      {canBind && list.isSuccess && choices?.length === 0 && (
        <AdminError
          tone="info"
          title="Nenhum perfil disponível"
          guided={{
            message: `Não há perfil de execução ativo para ${engine.adapter_type} / ${feature} no seu escopo. ${canCreate ? "Crie e publique um perfil para vinculá-lo aqui." : "Peça a quem configura runtime para criar e publicar um."}`,
            nextSteps: canCreate ? ["create_profile"] : ["request_access"],
          }}
          actions={canCreate ? { create_profile: () => router.push(createUrl) } : {}}
        />
      )}
      {current.data?.source_profile_revision_id && (
        <p className="text-sm">
          Origem: {current.data.source_profile_revision_id} · desejado r
          {current.data.revision}
        </p>
      )}
      {!canBind ? (
        <p className="text-sm">
          Solicite ao configurador de runtime a vinculação de um perfil
          publicado.
        </p>
      ) : (
        <>
          <Label htmlFor="execution-profile">Escolher perfil</Label>
          <select
            id="execution-profile"
            className={settingsSelectClass}
            value={selected}
            onChange={(e) => {
              setSelected(e.target.value);
              setRevision("");
            }}
          >
            <option value="">Selecione um perfil</option>
            {choices?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} · {p.environment}
              </option>
            ))}
          </select>
          {selected && (
            <>
              <Label htmlFor="execution-revision">Revisão publicada</Label>
              <select
                id="execution-revision"
                className={settingsSelectClass}
                value={revision}
                onChange={(e) => setRevision(e.target.value)}
              >
                <option value="">Selecione uma revisão</option>
                {detail.data?.revisions
                  ?.filter((r) => r.published_at)
                  .map((r) => (
                    <option key={r.id} value={r.id}>
                      Revisão {r.revision}
                    </option>
                  ))}
              </select>
            </>
          )}
          {chosen && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <caption className="text-left py-2">
                  Mudanças no desejado
                </caption>
                <thead>
                  <tr>
                    <th className="text-left">Parâmetro</th>
                    <th className="text-left">Atual</th>
                    <th className="text-left">Escolhido</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries({
                    Modelo: [
                      current.data?.profile.model_profile_id,
                      chosen.settings.model_profile_id,
                    ],
                    Réplicas: [
                      current.data?.profile.max_replicas,
                      chosen.settings.max_replicas,
                    ],
                    Concorrência: [
                      current.data?.profile.binding.executions_per_worker,
                      chosen.settings.binding.executions_per_worker,
                    ],
                    CPU: [
                      current.data?.profile.binding.cpu,
                      chosen.settings.binding.cpu,
                    ],
                    Memória: [
                      current.data?.profile.memory_mb,
                      chosen.settings.memory_mb,
                    ],
                    GPU: [
                      current.data?.profile.binding.gpu_ref ||
                        current.data?.profile.binding.gpu_type,
                      chosen.settings.binding.gpu_ref ||
                        chosen.settings.binding.gpu_type,
                    ],
                    Host: [
                      current.data?.profile.provider_settings.host_id,
                      chosen.settings.provider_settings.host_id,
                    ],
                    Aquecimento: [
                      current.data?.profile.warm_until,
                      chosen.warm_for_seconds
                        ? `${chosen.warm_for_seconds}s a partir da vinculação`
                        : "Sem prazo",
                    ],
                  }).map(([k, v]) => (
                    <tr key={k}>
                      <td className="py-1">{k}</td>
                      <td>{String(v[0] ?? "—")}</td>
                      <td>{String(v[1] ?? "—")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <Button disabled={!chosen || busy} onClick={bind}>
            {busy ? "Vinculando…" : "Vincular ao desejado"}
          </Button>
        </>
      )}
      <div className="flex gap-4 text-sm">
        <Link className="underline" href="/admin/execution-profiles">
          Biblioteca de perfis
        </Link>
        {canCreate && (
          <Link className="underline" href={createUrl}>
            Criar perfil
          </Link>
        )}
        {user?.is_admin && (
          <Link className="underline" href="/admin/access">
            Ambientes e escopos
          </Link>
        )}
      </div>
      {(error != null || list.error || detail.error) && (
        <AdminError
          error={error ?? list.error ?? detail.error}
          fallback="Falha ao vincular"
          actions={{
            ...(onTestConnection && { test_connection: onTestConnection }),
            ...(canCreate && {
              create_profile: () => router.push(createUrl),
            }),
            reload: () => {
              setError(null);
              current.refetch();
              list.refetch();
            },
          }}
        />
      )}
    </div>
  );
}
