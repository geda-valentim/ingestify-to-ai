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
import { iamApi } from "@/lib/iam-api";
import type { AccessPolicy, Constraints } from "@/types/access";
import type { IamBinding, IamBindingCreate, IamRole } from "@/types/iam";

// Both families expire within 365 days (spec 0014 CA7, 0009 create_grant).
const MAX_DAYS = 365;
const DEFAULT_DAYS = 90;

type Family = IamBinding["family"];
const FAMILY_LABEL: Record<Family, string> = {
  platform: "Plataforma",
  engines: "Engines",
};

/** What the viewer may do with each family (spec 0018 CA11); the API decides again. */
export interface AccessAuthority {
  bootstrap: boolean;
  held: Set<string>;
  /** `iam.bindings.read`: see platform bindings. */
  platformRead: boolean;
  /** `iam.bindings.manage`: grant and revoke platform roles. */
  platformManage: boolean;
  /** `access.grants.manage` with engines access on: the 0009 family. */
  enginesManage: boolean;
}

/** `Date` -> the `YYYY-MM-DDTHH:mm` a datetime-local input takes, in local time. */
function localInput(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
function daysFromNow(days: number): Date {
  return new Date(Date.now() + days * 24 * 3600 * 1000);
}
/** The API serializes naive UTC datetimes. */
function parseUtc(iso: string): Date {
  return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + "Z");
}
function utc(iso: string): string {
  return parseUtc(iso).toLocaleString();
}

/** `revision id` -> "política · rN", for the condition of an engines binding. */
function revisionNames(policies: AccessPolicy[] | undefined) {
  return new Map(
    (policies ?? []).flatMap((p) =>
      p.revisions.map((r) => [r.id, `${p.name} · r${r.revision}`] as const),
    ),
  );
}

/**
 * Concessões (spec 0018 §4.6): every binding the viewer can see, of both
 * families, through `/admin/iam/bindings`. Each family keeps its own authority:
 * a platform role is granted with `iam.bindings.manage`, an engines role with
 * `access.grants.manage` (and the 0009 delegation envelope).
 */
export function BindingsPanel({ authority: a }: { authority: AccessAuthority }) {
  const [showInactive, setShowInactive] = useState(false);
  const [filter, setFilter] = useState<"" | Family>("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const catalog = useQuery({
    queryKey: ["iam-catalog"],
    queryFn: iamApi.catalog,
  });
  const bindings = useQuery({
    queryKey: ["iam-bindings", showInactive],
    queryFn: () => iamApi.bindings(showInactive),
  });
  const policies = useQuery({
    queryKey: ["access-policies"],
    queryFn: accessApi.policies,
    enabled: a.enginesManage,
  });
  // The subject directory is bootstrap-only; others type the user ID.
  const subjects = useQuery({
    queryKey: ["access-subjects"],
    queryFn: accessApi.subjects,
    enabled: a.bootstrap,
  });
  const names = new Map(
    (subjects.data ?? []).map((s) => [s.id, `${s.username} · ${s.email}`]),
  );
  const conditions = revisionNames(policies.data);
  const rows = (bindings.data ?? []).filter(
    (b) => !filter || b.family === filter,
  );
  const canRevoke = (b: IamBinding) =>
    b.family === "platform" ? a.platformManage : a.enginesManage;

  async function perform(fn: () => Promise<unknown>): Promise<boolean> {
    setBusy(true);
    setError(null);
    try {
      await fn();
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha ao salvar");
      return false;
    } finally {
      // Also after a 409: the row comes back with its current version and state.
      await bindings.refetch();
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      {catalog.data?.mode &&
        catalog.data.mode !== "enforce" &&
        a.platformRead && (
          <p role="status" className="text-sm rounded-md border bg-muted/40 p-3">
            IAM_MODE={catalog.data.mode}: as concessões de plataforma ficam
            registradas mas não têm efeito até IAM_MODE=enforce.
          </p>
        )}
      {(error || catalog.error) && (
        <p role="alert" className="text-destructive">
          {error || String(catalog.error)}
        </p>
      )}
      {(a.platformManage || a.enginesManage) && catalog.data && (
        <GrantForm
          authority={a}
          roles={catalog.data.roles}
          policies={policies.data ?? []}
          subjects={subjects.data ?? []}
          busy={busy}
          submit={(body) => perform(() => iamApi.grant(body))}
        />
      )}
      <Card>
        <CardHeader>
          <CardTitle>Concessões e revogação</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2">
              <Label htmlFor="binding-family">Família</Label>
              <select
                id="binding-family"
                className={selectClass + " max-w-48"}
                value={filter}
                onChange={(e) => setFilter(e.target.value as "" | Family)}
              >
                <option value="">Todas</option>
                <option value="platform">{FAMILY_LABEL.platform}</option>
                <option value="engines">{FAMILY_LABEL.engines}</option>
              </select>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={showInactive}
                onChange={(e) => setShowInactive(e.target.checked)}
              />
              Incluir revogadas e expiradas
            </label>
          </div>
          {bindings.error ? (
            <QueryError
              error={bindings.error}
              what="as concessões"
              onRetry={() => bindings.refetch()}
            />
          ) : bindings.data && rows.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Nenhuma concessão visível.
            </p>
          ) : (
            rows.map((b) => (
              <BindingRow
                key={b.id}
                binding={b}
                name={names.get(b.subject_id)}
                condition={
                  b.condition_ref
                    ? conditions.get(b.condition_ref) ?? b.condition_ref
                    : undefined
                }
                busy={busy}
                canRevoke={canRevoke(b)}
                revoke={() => perform(() => iamApi.revoke(b))}
              />
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function GrantForm({
  authority: a,
  roles: catalogRoles,
  policies,
  subjects,
  busy,
  submit,
}: {
  authority: AccessAuthority;
  roles: IamRole[];
  policies: AccessPolicy[];
  subjects: { id: string; username: string; email: string }[];
  busy: boolean;
  submit: (body: IamBindingCreate) => Promise<boolean>;
}) {
  // Nobody grants a platform role whose permissions they lack (0014 CA7). An
  // engines role is bounded by the delegation envelope, which the API checks.
  const roles = catalogRoles.filter((r) =>
    r.family === "platform"
      ? a.platformManage &&
        (a.bootstrap || r.permissions.every((p) => a.held.has(p)))
      : a.enginesManage,
  );
  const enginePermissions = Array.from(
    new Set(
      catalogRoles
        .filter((r) => r.family === "engines")
        .flatMap((r) => r.permissions),
    ),
  ).sort();
  const [subject, setSubject] = useState("");
  const [role, setRole] = useState("");
  const [expires, setExpires] = useState(() =>
    localInput(daysFromNow(DEFAULT_DAYS)),
  );
  const [conditionRef, setConditionRef] = useState("");
  // null = every permission of the role (the API stores it materialized).
  const [permissions, setPermissions] = useState<string[] | null>(null);
  const [delegating, setDelegating] = useState(false);
  const [delegatePermissions, setDelegatePermissions] = useState<string[]>([]);
  const [delegateConstraints, setDelegateConstraints] =
    useState<Constraints>(defaultConstraints());
  const [duration, setDuration] = useState(3600);
  const selected = roles.find((r) => r.key === (role || roles[0]?.key));
  const engines = selected?.family === "engines";
  const chosen = permissions ?? selected?.permissions ?? [];
  if (!roles.length) return null;

  function toggle(list: string[], perm: string, on: boolean) {
    return on ? [...list, perm] : list.filter((p) => p !== perm);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Conceder papel</CardTitle>
      </CardHeader>
      <CardContent>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (!selected) return;
            const body: IamBindingCreate = {
              subject_type: "user",
              subject_id: subject.trim(),
              role: selected.key,
              expires_at: new Date(expires).toISOString(),
            };
            if (engines) {
              body.condition_ref = conditionRef;
              if (permissions) body.permissions = permissions;
              if (delegating && selected.key === "access_admin")
                body.delegation = {
                  permissions: delegatePermissions,
                  constraints: delegateConstraints,
                  max_grant_seconds: duration,
                };
            }
            submit(body).then((ok) => ok && setSubject(""));
          }}
        >
          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <Label htmlFor="grant-subject">ID do usuário</Label>
              <Input
                id="grant-subject"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                list="grant-subjects"
                required
              />
              <datalist id="grant-subjects">
                {subjects.map((s) => (
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
                value={selected?.key ?? ""}
                onChange={(e) => {
                  setRole(e.target.value);
                  setPermissions(null);
                  setDelegating(false);
                }}
              >
                {(["platform", "engines"] as const).map((family) => {
                  const options = roles.filter((r) => r.family === family);
                  return options.length ? (
                    <optgroup key={family} label={FAMILY_LABEL[family]}>
                      {options.map((r) => (
                        <option key={r.key} value={r.key}>
                          {r.key}
                        </option>
                      ))}
                    </optgroup>
                  ) : null;
                })}
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
                min={localInput(new Date())}
                max={localInput(daysFromNow(MAX_DAYS))}
                value={expires}
                onChange={(e) => setExpires(e.target.value)}
              />
            </div>
          </div>
          {selected && (
            <div className="text-sm space-y-1">
              <p>
                <span className="font-medium">
                  {FAMILY_LABEL[selected.family]}
                </span>{" "}
                · {selected.description}
              </p>
              {!engines && (
                <p className="text-xs text-muted-foreground">
                  {selected.permissions.join(", ")}
                </p>
              )}
            </div>
          )}
          {engines && selected && (
            <>
              <div className="max-w-md">
                <Label htmlFor="grant-condition">Revisão da política</Label>
                <select
                  id="grant-condition"
                  className={selectClass}
                  value={conditionRef}
                  onChange={(e) => setConditionRef(e.target.value)}
                  required
                >
                  <option value="">Selecione</option>
                  {policies.flatMap((p) =>
                    p.revisions.map((r) => (
                      <option key={r.id} value={r.id}>
                        {p.name} · r{r.revision}
                      </option>
                    )),
                  )}
                </select>
              </div>
              <fieldset>
                <legend className="font-medium mb-2">
                  Permissões concedidas
                </legend>
                <div className="grid gap-2 sm:grid-cols-2">
                  {selected.permissions.map((perm) => (
                    <label
                      key={perm}
                      className="flex items-center gap-2 text-sm"
                    >
                      <input
                        type="checkbox"
                        checked={chosen.includes(perm)}
                        onChange={(e) =>
                          setPermissions(toggle(chosen, perm, e.target.checked))
                        }
                      />
                      {perm}
                    </label>
                  ))}
                </div>
              </fieldset>
              {selected.key === "access_admin" && (
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
                        {enginePermissions.map((perm) => (
                          <label key={perm} className="flex gap-2 text-sm">
                            <input
                              type="checkbox"
                              checked={delegatePermissions.includes(perm)}
                              onChange={(e) =>
                                setDelegatePermissions(
                                  toggle(
                                    delegatePermissions,
                                    perm,
                                    e.target.checked,
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
            </>
          )}
          <Button
            type="submit"
            disabled={
              busy ||
              !selected ||
              !subject.trim() ||
              !expires ||
              (engines && (!conditionRef || chosen.length === 0))
            }
          >
            Conceder papel
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function BindingRow({
  binding: b,
  name,
  condition,
  busy,
  canRevoke,
  revoke,
}: {
  binding: IamBinding;
  name?: string;
  condition?: string;
  busy: boolean;
  canRevoke: boolean;
  revoke: () => void;
}) {
  const state = b.revoked_at
    ? `Revogada em ${utc(b.revoked_at)}`
    : b.active
      ? "Ativa"
      : // An engines binding is also inactive under a revoked or expired parent.
        parseUtc(b.expires_at) > new Date()
        ? "Inativa"
        : "Expirada";
  // A platform binding is revoked while active (0014); an engines one while not
  // revoked, as in 0009 (a dead parent does not revoke its children).
  const revocable = b.family === "platform" ? b.active : !b.revoked_at;
  return (
    <div className="rounded-md border p-3 space-y-2">
      <p className="flex flex-wrap items-center gap-2">
        <strong>{b.role}</strong>
        <span className="rounded border px-1.5 text-xs text-muted-foreground">
          {FAMILY_LABEL[b.family]}
        </span>
      </p>
      <p className="text-sm break-all">
        {b.subject_type === "user" ? "Usuário" : "Service principal"}{" "}
        {b.subject_id}
        {name ? ` (${name})` : ""}
      </p>
      <p className="text-sm">
        Até {utc(b.expires_at)} · {state}
        {b.granted_by ? ` · concedida por ${b.granted_by}` : ""}
      </p>
      {b.family === "engines" && (
        <>
          <p className="text-sm break-all">
            Política {condition ?? "—"}
            {b.parent_id ? ` · derivada de ${b.parent_id}` : ""}
            {b.delegation ? " · com envelope de delegação" : ""}
          </p>
          <p className="text-xs text-muted-foreground">
            {(b.permissions ?? []).join(", ")}
          </p>
        </>
      )}
      {canRevoke && revocable && (
        <Button variant="outline" disabled={busy} onClick={revoke}>
          Revogar
        </Button>
      )}
    </div>
  );
}
