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
import { accessApi } from "@/lib/access-api";
import { computeApi } from "@/lib/api";
import type { Constraints, ResourceScope } from "@/types/access";
export default function AccessPage() {
  const me = useQuery({ queryKey: ["access-me"], queryFn: accessApi.me });
  const policies = useQuery({
    queryKey: ["access-policies"],
    queryFn: accessApi.policies,
  });
  const grants = useQuery({
    queryKey: ["access-grants"],
    queryFn: accessApi.grants,
  });
  const roles = useQuery({
    queryKey: ["access-roles"],
    queryFn: accessApi.roles,
  });
  const subjects = useQuery({
    queryKey: ["access-subjects"],
    queryFn: accessApi.subjects,
    enabled: !!me.data?.bootstrap,
  });
  const engines = useQuery({
    queryKey: ["admin", "engines"],
    queryFn: computeApi.engines,
    enabled: !!me.data?.bootstrap,
  });
  const attributes = useQuery({
    queryKey: ["access-attributes"],
    queryFn: accessApi.attributes,
    enabled: !!me.data?.bootstrap,
  });
  const resources = useQuery({
    queryKey: ["access-resources"],
    queryFn: accessApi.resources,
    enabled: !!me.data?.bootstrap,
  });
  const [name, setName] = useState("");
  const [constraints, setConstraints] =
    useState<Constraints>(defaultConstraints());
  const [policyId, setPolicyId] = useState("");
  const [subject, setSubject] = useState("");
  const [role, setRole] = useState("observer");
  const [permissions, setPermissions] = useState<string[] | null>(null);
  const [expires, setExpires] = useState("");
  const [delegating, setDelegating] = useState(false);
  const [delegatePermissions, setDelegatePermissions] = useState<string[]>([]);
  const [delegateConstraints, setDelegateConstraints] =
    useState<Constraints>(defaultConstraints());
  const [duration, setDuration] = useState(3600);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [policyEdit, setPolicyEdit] = useState("");
  async function perform(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await Promise.all([
        policies.refetch(),
        grants.refetch(),
        ...(me.data?.bootstrap
          ? [attributes.refetch(), resources.refetch()]
          : []),
      ]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha ao salvar");
    } finally {
      setBusy(false);
    }
  }
  const rolePermissions = roles.data?.[role] || [];
  const allPermissions = Array.from(
    new Set(Object.values(roles.data || {}).flat()),
  ).sort();
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold">Papéis e políticas de acesso</h2>
        <p className="text-muted-foreground">
          Papéis concedem ações. Cada grant fixa uma revisão da política e uma
          validade UTC. Uma ação precisa atender integralmente um grant.
        </p>
        <p className="text-sm mt-2">
          O bootstrap da plataforma é administrado separadamente. Administrador
          de acesso não recebe execução nem credenciais pelo seu papel.
        </p>
      </div>
      {!me.data?.enabled && (
        <p role="status">
          Acesso granular requer a migração 0009 e ENGINE_ACCESS_ENABLED.
        </p>
      )}
      {(error || policies.error || grants.error) && (
        <p role="alert" className="text-destructive">
          {error || String(policies.error || grants.error)}
        </p>
      )}
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
          {policies.data?.map((p) => (
            <div key={p.id} className="rounded-md border p-3">
              <strong>{p.name}</strong>
              <p className="text-sm">
                {p.revisions.map((r) => `r${r.revision}`).join(", ")} · {p.id}
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
          ))}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Conceder papel</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              perform(() =>
                accessApi.grant({
                  user_id: subject,
                  role,
                  policy_revision_id: policyId,
                  permissions: permissions ?? rolePermissions,
                  expires_at: new Date(expires).toISOString(),
                  delegation:
                    delegating && role === "access_admin"
                      ? {
                          permissions: delegatePermissions,
                          constraints: delegateConstraints,
                          max_grant_seconds: duration,
                        }
                      : null,
                }),
              );
            }}
          >
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <Label htmlFor="grant-subject">ID do usuário</Label>
                <Input
                  id="grant-subject"
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  list="access-subjects"
                  required
                />
                <datalist id="access-subjects">
                  {subjects.data?.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.username} · {s.email}
                    </option>
                  ))}
                </datalist>
              </div>
              <div>
                <Label htmlFor="grant-role">Papel</Label>
                <select
                  id="grant-role"
                  className={selectClass}
                  value={role}
                  onChange={(e) => {
                    setRole(e.target.value);
                    setPermissions(null);
                    setDelegating(false);
                  }}
                >
                  {Object.keys(roles.data || {}).map((r) => (
                    <option key={r}>{r}</option>
                  ))}
                </select>
              </div>
              <div>
                <Label htmlFor="grant-policy">Revisão da política</Label>
                <select
                  id="grant-policy"
                  className={selectClass}
                  value={policyId}
                  onChange={(e) => setPolicyId(e.target.value)}
                  required
                >
                  <option value="">Selecione</option>
                  {policies.data?.flatMap((p) =>
                    p.revisions.map((r) => (
                      <option key={r.id} value={r.id}>
                        {p.name} · r{r.revision}
                      </option>
                    )),
                  )}
                </select>
              </div>
              <div>
                <Label htmlFor="grant-expiry">
                  Válido até (horário local, convertido em UTC)
                </Label>
                <Input
                  id="grant-expiry"
                  type="datetime-local"
                  required
                  value={expires}
                  onChange={(e) => setExpires(e.target.value)}
                />
              </div>
            </div>
            <fieldset>
              <legend className="font-medium mb-2">
                Permissões concedidas
              </legend>
              <div className="grid gap-2 sm:grid-cols-2">
                {rolePermissions.map((perm) => (
                  <label key={perm} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={(permissions ?? rolePermissions).includes(perm)}
                      onChange={(e) =>
                        setPermissions(
                          e.target.checked
                            ? [...(permissions ?? rolePermissions), perm]
                            : (permissions ?? rolePermissions).filter(
                                (p) => p !== perm,
                              ),
                        )
                      }
                    />
                    {perm}
                  </label>
                ))}
              </div>
            </fieldset>
            {role === "access_admin" && (
              <>
                <label className="flex gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={delegating}
                    onChange={(e) => setDelegating(e.target.checked)}
                  />
                  Definir envelope de delegação (sem ele, nenhuma concessão)
                </label>
                {delegating && (
                  <div className="rounded-md border p-4 space-y-4">
                    <p className="text-sm">
                      O envelope limita concessões e não concede execução ao
                      administrador.
                    </p>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {allPermissions.map((perm) => (
                        <label key={perm} className="flex gap-2 text-sm">
                          <input
                            type="checkbox"
                            checked={delegatePermissions.includes(perm)}
                            onChange={(e) =>
                              setDelegatePermissions(
                                e.target.checked
                                  ? [...delegatePermissions, perm]
                                  : delegatePermissions.filter(
                                      (p) => p !== perm,
                                    ),
                              )
                            }
                          />
                          {perm}
                        </label>
                      ))}
                    </div>
                    <ConstraintsFields
                      prefix="delegation"
                      value={delegateConstraints}
                      onChange={setDelegateConstraints}
                    />
                    <Label htmlFor="delegation-duration">
                      Validade máxima concedível (s)
                    </Label>
                    <Input
                      id="delegation-duration"
                      type="number"
                      min="60"
                      max="31536000"
                      value={duration}
                      onChange={(e) => setDuration(Number(e.target.value))}
                    />
                  </div>
                )}
              </>
            )}
            <Button type="submit" disabled={busy || !policyId || !subject}>
              Conceder papel
            </Button>
          </form>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Grants e revogação</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {grants.data?.map((g) => (
            <div key={g.id} className="rounded-md border p-3 space-y-2">
              <strong>{g.role}</strong>
              <p className="text-sm">
                Usuário {g.user_id} · política {g.policy_revision_id}
              </p>
              <p className="text-sm">
                Até {new Date(g.expires_at + "Z").toLocaleString()} ·{" "}
                {g.revoked_at ? "Revogado" : "Concedido"}
                {g.parent_id ? ` · derivado de ${g.parent_id}` : ""}
              </p>
              <p className="text-xs text-muted-foreground">
                {g.permissions.join(", ")}
              </p>
              {!g.revoked_at && (
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() => perform(() => accessApi.revoke(g))}
                >
                  Revogar
                </Button>
              )}
            </div>
          ))}
        </CardContent>
      </Card>
      {me.data?.bootstrap && (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Ambiente confiável das engines</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {engines.data?.map((e) => {
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
                          accessApi.classify(
                            e.id,
                            v.target.value,
                            a?.version || 0,
                          ),
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
              })}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Consumidores de recursos compartilhados</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm">
                Declare todos os consumidores, inclusive outras features do
                worker genérico. Recursos não qualificados bloqueiam operações
                delegadas.
              </p>
              {resources.data?.map((r) => (
                <ResourceEditor
                  key={`${r.key}:${r.version}`}
                  resource={r}
                  busy={busy}
                  save={(body) => perform(() => accessApi.qualify(body))}
                />
              ))}
            </CardContent>
          </Card>
        </>
      )}
    </div>
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
