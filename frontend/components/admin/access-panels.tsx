"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import {
  ConstraintsFields,
  defaultConstraints,
} from "@/components/admin/access-constraints-fields";
import { settingsSelectClass as selectClass } from "@/components/admin/runtime-settings-fields";
import { QueryError } from "@/components/admin/compute-ui";
import { accessApi } from "@/lib/access-api";
import { computeApi } from "@/lib/api";
import type {
  Constraints,
  InstallationPrincipal,
  ResourceScope,
} from "@/types/access";
import { AdminError } from "@/components/admin/admin-error";

/** busy/error around a write, then a refetch of what it changed. */
function useWrite(refetch: () => Promise<unknown>) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  async function perform(fn: () => Promise<unknown>): Promise<boolean> {
    setBusy(true);
    setError(null);
    try {
      await fn();
      return true;
    } catch (e) {
      setError(e);
      return false;
    } finally {
      await refetch();
      setBusy(false);
    }
  }
  const alert =
    error != null ? <AdminError error={error} fallback="Falha ao salvar" /> : null;
  return { busy, perform, alert };
}

/** Políticas: the ABAC conditions of engines bindings (0009, `access.grants.manage`). */
export function PoliciesPanel() {
  const policies = useQuery({
    queryKey: ["access-policies"],
    queryFn: accessApi.policies,
  });
  const { busy, perform, alert } = useWrite(() => policies.refetch());
  const [name, setName] = useState("");
  const [constraints, setConstraints] =
    useState<Constraints>(defaultConstraints());
  const [policyEdit, setPolicyEdit] = useState("");
  return (
    <div className="space-y-6">
      {alert}
      <Card>
        <CardHeader>
          <CardTitle>
            {policyEdit ? "Nova revisão da política" : "Criar política ABAC"}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              perform(async () => {
                if (policyEdit) {
                  const p = policies.data?.find((p) => p.id === policyEdit);
                  if (p) await accessApi.revisePolicy(p, constraints);
                } else await accessApi.createPolicy({ name, constraints });
                setPolicyEdit("");
                setName("");
              });
            }}
          >
            <Label htmlFor="policy-name">Nome da política</Label>
            <Input
              id="policy-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              disabled={!!policyEdit}
            />
            <ConstraintsFields value={constraints} onChange={setConstraints} />
            <Button type="submit" disabled={busy}>
              {policyEdit ? "Salvar nova revisão" : "Criar política"}
            </Button>
            {policyEdit && (
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setPolicyEdit("");
                  setName("");
                }}
              >
                Cancelar edição
              </Button>
            )}
          </form>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Políticas existentes</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {policies.error ? (
            <QueryError
              error={policies.error}
              what="as políticas"
              onRetry={() => policies.refetch()}
            />
          ) : policies.data && policies.data.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nenhuma política.</p>
          ) : (
            policies.data?.map((p) => (
              <div key={p.id} className="rounded-md border p-3">
                <strong>{p.name}</strong>
                <p className="text-sm">
                  {p.revisions.map((r) => `r${r.revision}`).join(", ")} ·{" "}
                  {p.id}
                </p>
                <Button
                  variant="outline"
                  className="mt-2"
                  onClick={() => {
                    setPolicyEdit(p.id);
                    setName(p.name);
                    setConstraints(p.revisions[0].constraints);
                  }}
                >
                  Nova revisão
                </Button>
              </div>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}

/** Atributos de engine: the trusted environment of each engine (bootstrap). */
export function AttributesPanel() {
  const engines = useQuery({
    queryKey: ["admin", "engines"],
    queryFn: computeApi.engines,
  });
  const attributes = useQuery({
    queryKey: ["access-attributes"],
    queryFn: accessApi.attributes,
  });
  const { busy, perform, alert } = useWrite(() => attributes.refetch());
  return (
    <Card>
      <CardHeader>
        <CardTitle>Ambiente confiável das engines</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {alert}
        {engines.error || attributes.error ? (
          <QueryError
            error={engines.error || attributes.error}
            what="os atributos"
            onRetry={() => {
              engines.refetch();
              attributes.refetch();
            }}
          />
        ) : (
          engines.data?.map((e) => {
            const a = attributes.data?.find((a) => a.engine_id === e.id);
            return (
              <div key={e.id} className="flex flex-wrap items-center gap-3">
                <span className="min-w-48">{e.display_name}</span>
                <select
                  aria-label={`Ambiente ${e.display_name}`}
                  className={selectClass + " max-w-xs"}
                  value={a?.environment || ""}
                  disabled={busy}
                  onChange={(v) =>
                    perform(() =>
                      accessApi.classify(e.id, v.target.value, a?.version || 0),
                    )
                  }
                >
                  <option value="">Não classificada</option>
                  {["development", "staging", "production"].map((env) => (
                    <option key={env}>{env}</option>
                  ))}
                </select>
              </div>
            );
          })
        )}
      </CardContent>
    </Card>
  );
}

/** Recursos: consumers of shared canonical resources (bootstrap). */
export function ResourcesPanel() {
  const resources = useQuery({
    queryKey: ["access-resources"],
    queryFn: accessApi.resources,
  });
  const { busy, perform, alert } = useWrite(() => resources.refetch());
  return (
    <Card>
      <CardHeader>
        <CardTitle>Consumidores de recursos compartilhados</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm">
          Declare todos os consumidores, inclusive outras features do worker
          genérico. Recursos não qualificados bloqueiam operações delegadas.
        </p>
        {alert}
        {resources.error ? (
          <QueryError
            error={resources.error}
            what="os recursos"
            onRetry={() => resources.refetch()}
          />
        ) : resources.data && resources.data.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nenhum recurso.</p>
        ) : (
          resources.data?.map((r) => (
            <ResourceEditor
              key={`${r.key}:${r.version}`}
              resource={r}
              busy={busy}
              save={(body) => perform(() => accessApi.qualify(body))}
            />
          ))
        )}
      </CardContent>
    </Card>
  );
}

function ResourceEditor({
  resource: r,
  busy,
  save,
}: {
  resource: ResourceScope;
  busy: boolean;
  save: (r: ResourceScope) => void;
}) {
  const [consumers, setConsumers] = useState(r.consumers);
  const [qualified, setQualified] = useState(r.qualified);
  return (
    <div className="rounded-md border p-3 space-y-3">
      <p className="text-sm break-all font-medium">{r.key}</p>
      {consumers.map((c, i) => (
        <div key={i} className="flex flex-wrap gap-2">
          <Input
            aria-label={`Engine consumidor ${i + 1} ${r.key}`}
            placeholder="ID da engine"
            value={c.engine_id}
            onChange={(e) =>
              setConsumers(
                consumers.map((v, j) =>
                  j === i ? { ...v, engine_id: e.target.value } : v,
                ),
              )
            }
          />
          <Input
            aria-label={`Feature consumidor ${i + 1} ${r.key}`}
            placeholder="Feature"
            value={c.feature}
            onChange={(e) =>
              setConsumers(
                consumers.map((v, j) =>
                  j === i ? { ...v, feature: e.target.value } : v,
                ),
              )
            }
          />
          <Button
            variant="outline"
            onClick={() => setConsumers(consumers.filter((_, j) => j !== i))}
          >
            Remover consumidor
          </Button>
        </div>
      ))}
      <Button
        variant="outline"
        onClick={() =>
          setConsumers([...consumers, { engine_id: "", feature: "" }])
        }
      >
        Adicionar consumidor
      </Button>
      <label className="flex gap-2 text-sm">
        <input
          type="checkbox"
          checked={qualified}
          onChange={(e) => setQualified(e.target.checked)}
        />
        Confirmei todos os consumidores deste recurso
      </label>
      <Button
        disabled={
          busy ||
          !consumers.length ||
          consumers.some((c) => !c.engine_id || !c.feature)
        }
        onClick={() => save({ ...r, consumers, qualified })}
      >
        Salvar escopo
      </Button>
    </div>
  );
}

/**
 * Principais de instalação: the `installation:<nome>` OS principals the direct
 * CLI acts as (0009, bootstrap). Registering or toggling one bumps the epoch.
 */
export function PrincipalsPanel() {
  const principals = useQuery({
    queryKey: ["access-principals"],
    queryFn: accessApi.principals,
  });
  const { busy, perform, alert } = useWrite(() => principals.refetch());
  const [name, setName] = useState("");
  const id = `installation:${name.trim()}`;
  const valid = /^[a-z0-9_-]{1,23}$/.test(name.trim());
  return (
    <div className="space-y-6">
      {alert}
      <Card>
        <CardHeader>
          <CardTitle>Registrar principal de instalação</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              perform(() => accessApi.registerPrincipal(id)).then(
                (ok) => ok && setName(""),
              );
            }}
          >
            <p className="text-sm">
              A CLI direta age como <code>installation:&lt;nome&gt;</code> com
              ENGINE_INSTALLATION_PRINCIPAL_ID e --installation-principal. Não
              é um usuário delegado e não recebe concessões.
            </p>
            <div className="max-w-sm">
              <Label htmlFor="principal-name">
                Nome (a-z, 0-9, _ e -, até 23)
              </Label>
              <Input
                id="principal-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </div>
            <Button type="submit" disabled={busy || !valid}>
              Registrar {valid ? id : "principal"}
            </Button>
          </form>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Principais registrados</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {principals.error ? (
            <QueryError
              error={principals.error}
              what="os principais"
              onRetry={() => principals.refetch()}
            />
          ) : principals.data && principals.data.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Nenhum principal registrado.
            </p>
          ) : (
            principals.data?.map((p: InstallationPrincipal) => (
              <div
                key={p.id}
                className="flex flex-wrap items-center gap-3 rounded-md border p-3"
              >
                <span className="font-medium break-all">{p.id}</span>
                <span className="text-sm text-muted-foreground">
                  {p.active ? "Ativo" : "Inativo"} · v{p.version}
                </span>
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() =>
                    perform(() => accessApi.setPrincipal(p, !p.active))
                  }
                >
                  {p.active ? "Desativar" : "Ativar"}
                </Button>
              </div>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}
