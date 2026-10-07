"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { settingsSelectClass as selectClass } from "@/components/admin/runtime-settings-fields";
import { QueryError } from "@/components/admin/compute-ui";
import { accessApi } from "@/lib/access-api";
import { iamApi } from "@/lib/iam-api";
import { useAuthStore } from "@/lib/store/auth";
import type { IamBinding } from "@/types/iam";

// A platform binding expires within 365 days (spec 0014 CA7); the API enforces it.
const MAX_DAYS = 365;
const DEFAULT_DAYS = 90;

/** `Date` -> the `YYYY-MM-DDTHH:mm` a datetime-local input takes, in local time. */
function localInput(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
function daysFromNow(days: number): Date {
  return new Date(Date.now() + days * 24 * 3600 * 1000);
}
/** The API serializes naive UTC datetimes. */
function utc(iso: string): string {
  return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + "Z").toLocaleString();
}

/**
 * Admin → Acesso à plataforma (spec 0014 §4.10): platform-role bindings of the
 * IAM core. Separate from the 0009 engine grants on /admin/access: a platform
 * binding never opens the engine or execution-profile routes.
 */
export default function PlatformAccessPage() {
  const user = useAuthStore((s) => s.user);
  const bootstrap = !!(user?.bootstrap ?? user?.is_admin);
  const held = new Set(user?.permissions ?? []);
  const canManage = bootstrap || held.has("iam.bindings.manage");
  const [showInactive, setShowInactive] = useState(false);
  const catalog = useQuery({
    queryKey: ["iam-catalog"],
    queryFn: iamApi.catalog,
  });
  const bindings = useQuery({
    queryKey: ["iam-bindings", showInactive],
    queryFn: () => iamApi.bindings(showInactive),
  });
  // The 0009 subject list is bootstrap-only; others type the user ID.
  const subjects = useQuery({
    queryKey: ["access-subjects"],
    queryFn: accessApi.subjects,
    enabled: bootstrap,
  });
  // Nobody grants a role whose permissions they lack (CA7): offer only those.
  // Only the platform family is granted here; engines roles need a condition.
  const roles = (catalog.data?.roles ?? []).filter(
    (r) =>
      r.family === "platform" &&
      (bootstrap || r.permissions.every((p) => held.has(p))),
  );
  const [subject, setSubject] = useState("");
  const [role, setRole] = useState("");
  const [expires, setExpires] = useState(() =>
    localInput(daysFromNow(DEFAULT_DAYS)),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selectedRole = roles.find((r) => r.key === (role || roles[0]?.key));
  const names = new Map(
    (subjects.data ?? []).map((s) => [s.id, `${s.username} · ${s.email}`]),
  );

  async function perform(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha ao salvar");
    } finally {
      // Also after a 409: the row comes back with its current version and state.
      await bindings.refetch();
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold">Acesso à plataforma</h2>
        <p className="text-muted-foreground">
          Papéis de plataforma concedem administração entre usuários
          (estatísticas, recuperação de jobs, routing, auditoria) e o uso de
          engines remotas. Cada concessão tem validade UTC de no máximo{" "}
          {MAX_DAYS} dias e, com IAM_MODE=enforce, vale a partir da próxima
          requisição.
        </p>
        {catalog.data?.mode && catalog.data.mode !== "enforce" && (
          <p role="status" className="text-sm mt-2 rounded-md border bg-muted/40 p-3">
            IAM_MODE={catalog.data.mode}: as concessões ficam registradas mas
            não têm efeito até IAM_MODE=enforce.
          </p>
        )}
        <p className="text-sm mt-2">
          Estes papéis não abrem engines nem perfis de execução: esses seguem os
          grants de Acesso. O bootstrap da plataforma não aparece aqui.
        </p>
      </div>
      {(error || catalog.error) && (
        <p role="alert" className="text-destructive">
          {error || String(catalog.error)}
        </p>
      )}
      {canManage && (
        <Card>
          <CardHeader>
            <CardTitle>Conceder papel de plataforma</CardTitle>
          </CardHeader>
          <CardContent>
            <form
              className="space-y-4"
              onSubmit={(e) => {
                e.preventDefault();
                if (!selectedRole) return;
                perform(async () => {
                  await iamApi.grant({
                    subject_type: "user",
                    subject_id: subject.trim(),
                    role: selectedRole.key,
                    expires_at: new Date(expires).toISOString(),
                  });
                  setSubject("");
                });
              }}
            >
              <div className="grid gap-4 sm:grid-cols-3">
                <div>
                  <Label htmlFor="iam-subject">ID do usuário</Label>
                  <Input
                    id="iam-subject"
                    value={subject}
                    onChange={(e) => setSubject(e.target.value)}
                    list="iam-subjects"
                    required
                  />
                  <datalist id="iam-subjects">
                    {subjects.data?.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.username} · {s.email}
                      </option>
                    ))}
                  </datalist>
                </div>
                <div>
                  <Label htmlFor="iam-role">Papel</Label>
                  <select
                    id="iam-role"
                    className={selectClass}
                    value={selectedRole?.key ?? ""}
                    onChange={(e) => setRole(e.target.value)}
                  >
                    {roles.map((r) => (
                      <option key={r.key} value={r.key}>
                        {r.key}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <Label htmlFor="iam-expiry">
                    Válido até (horário local, convertido em UTC)
                  </Label>
                  <Input
                    id="iam-expiry"
                    type="datetime-local"
                    required
                    min={localInput(new Date())}
                    max={localInput(daysFromNow(MAX_DAYS))}
                    value={expires}
                    onChange={(e) => setExpires(e.target.value)}
                  />
                </div>
              </div>
              {selectedRole && (
                <div className="text-sm space-y-1">
                  <p>{selectedRole.description}</p>
                  <p className="text-xs text-muted-foreground">
                    {selectedRole.permissions.join(", ")}
                  </p>
                </div>
              )}
              <Button
                type="submit"
                disabled={busy || !selectedRole || !subject.trim() || !expires}
              >
                Conceder papel
              </Button>
            </form>
          </CardContent>
        </Card>
      )}
      <Card>
        <CardHeader>
          <CardTitle>Concessões e revogação</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={showInactive}
              onChange={(e) => setShowInactive(e.target.checked)}
            />
            Incluir revogadas e expiradas
          </label>
          {bindings.error ? (
            <QueryError
              error={bindings.error}
              what="as concessões"
              onRetry={() => bindings.refetch()}
            />
          ) : bindings.data && bindings.data.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Nenhuma concessão de plataforma.
            </p>
          ) : (
            bindings.data?.map((b) => (
              <BindingRow
                key={b.id}
                binding={b}
                name={names.get(b.subject_id)}
                busy={busy}
                canRevoke={canManage}
                revoke={() => perform(() => iamApi.revoke(b))}
              />
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function BindingRow({
  binding: b,
  name,
  busy,
  canRevoke,
  revoke,
}: {
  binding: IamBinding;
  name?: string;
  busy: boolean;
  canRevoke: boolean;
  revoke: () => void;
}) {
  const state = b.revoked_at
    ? `Revogada em ${utc(b.revoked_at)}`
    : b.active
      ? "Ativa"
      : "Expirada";
  return (
    <div className="rounded-md border p-3 space-y-2">
      <strong>{b.role}</strong>
      <p className="text-sm break-all">
        {b.subject_type === "user" ? "Usuário" : "Service principal"}{" "}
        {b.subject_id}
        {name ? ` (${name})` : ""}
      </p>
      <p className="text-sm">
        Até {utc(b.expires_at)} · {state}
        {b.granted_by ? ` · concedida por ${b.granted_by}` : ""}
      </p>
      {canRevoke && b.active && (
        <Button variant="outline" disabled={busy} onClick={revoke}>
          Revogar
        </Button>
      )}
    </div>
  );
}
