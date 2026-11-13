"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, KeyRound } from "lucide-react";
import { adminUsersApi } from "@/lib/admin-users-api";
import { useAuthStore } from "@/lib/store/auth";
import { formatBytes } from "@/lib/utils";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { LoadingCards, Pill, adminRetry } from "@/components/admin/compute-ui";
import {
  STATUS_LABELS,
  UserBadges,
  UsersError,
  formatCount,
  formatDate,
  formatWhen,
} from "@/components/admin/users-ui";
import type { AdminUserApiKey, AdminUserDetail } from "@/types/admin-users";

/** Admin → Usuários → one user (spec 0024): keys, projects, usage and IAM bindings. */
export default function UserDetailPage() {
  const { id } = useParams<{ id: string }>();
  const token = useAuthStore((s) => s.token);
  const query = useQuery({
    queryKey: ["admin", "user", token, id],
    queryFn: () => adminUsersApi.get(id),
    enabled: !!token && !!id,
    retry: adminRetry,
  });

  const back = (
    <Link href="/admin/users" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
      <ArrowLeft className="h-4 w-4" aria-hidden /> Usuários
    </Link>
  );

  if (query.isLoading) return <LoadingCards count={3} label="Carregando usuário" />;
  if (query.error && !query.data) {
    return (
      <div className="space-y-3">
        {back}
        <UsersError error={query.error} what="o usuário" onRetry={() => query.refetch()} />
      </div>
    );
  }
  const user = query.data!;

  return (
    <div className="space-y-4">
      {back}
      <SummaryCard user={user} />
      <KeysCard keys={user.api_keys} />
      <ProjectsCard user={user} />
      <BindingsCard user={user} />
    </div>
  );
}

function SummaryCard({ user }: { user: AdminUserDetail }) {
  const statuses = Object.entries(user.jobs_by_status).sort((a, b) => b[1] - a[1]);
  const sources = Object.entries(user.usage.by_source_type).sort((a, b) => b[1] - a[1]);
  const recent = user.usage.last_30_days;
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex flex-wrap items-center gap-2">
          {user.username} <UserBadges user={user} />
        </CardTitle>
        <CardDescription className="break-all">
          {user.email} · cadastrado em {formatDate(user.created_at)}
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4 md:grid-cols-3 text-sm">
        <dl className="grid grid-cols-2 gap-y-1">
          <dt className="text-muted-foreground">Jobs</dt>
          <dd className="tabular-nums">{formatCount(user.jobs_total)}</dd>
          <dt className="text-muted-foreground">Enviado</dt>
          <dd className="tabular-nums">{formatBytes(user.bytes_uploaded)}</dd>
          <dt className="text-muted-foreground">Páginas</dt>
          <dd className="tabular-nums">{formatCount(user.pages_total)}</dd>
          <dt className="text-muted-foreground">Último job</dt>
          <dd>{formatWhen(user.last_job_at)}</dd>
          <dt className="text-muted-foreground">Último uso de chave</dt>
          <dd>{formatWhen(user.last_api_key_used_at)}</dd>
        </dl>
        <div>
          <p className="text-xs font-medium text-muted-foreground mb-1">Jobs por status</p>
          {statuses.length === 0 ? (
            <p className="text-muted-foreground">Nenhum job.</p>
          ) : (
            <ul className="space-y-0.5">
              {statuses.map(([status, n]) => (
                <li key={status} className="tabular-nums">
                  {formatCount(n)} {STATUS_LABELS[status] ?? status}
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <p className="text-xs font-medium text-muted-foreground mb-1">Por origem</p>
          {sources.length === 0 ? (
            <p className="text-muted-foreground">—</p>
          ) : (
            <ul className="space-y-0.5">
              {sources.map(([source, n]) => (
                <li key={source} className="tabular-nums">
                  {formatCount(n)} {source}
                </li>
              ))}
            </ul>
          )}
          <p className="text-xs font-medium text-muted-foreground mt-3 mb-1">Últimos 30 dias</p>
          <p className="tabular-nums">
            {formatCount(recent.jobs)} jobs · {formatBytes(recent.bytes)} · {formatCount(recent.pages)} páginas
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

function keyState(key: AdminUserApiKey) {
  if (!key.is_active) return <Pill tone="muted">revogada</Pill>;
  if (key.expired) return <Pill tone="warn">expirada</Pill>;
  return <Pill tone="ok">ativa</Pill>;
}

function KeysCard({ keys }: { keys: AdminUserApiKey[] }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          <KeyRound className="h-4 w-4" aria-hidden /> API keys
        </CardTitle>
        <CardDescription>Metadados apenas; o segredo nunca sai da API.</CardDescription>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        {keys.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nenhuma chave.</p>
        ) : (
          <table className="w-full text-sm">
            <caption className="sr-only">API keys do usuário</caption>
            <thead>
              <tr className="text-left text-xs text-muted-foreground">
                <th className="font-medium py-1 pr-2">Nome</th>
                <th className="font-medium py-1 px-2">Estado</th>
                <th className="font-medium py-1 px-2">Criada</th>
                <th className="font-medium py-1 px-2">Último uso</th>
                <th className="font-medium py-1 pl-2">Expira</th>
              </tr>
            </thead>
            <tbody>
              {keys.map((k) => (
                <tr key={k.id} className="border-t">
                  <td className="py-1.5 pr-2">{k.name || <span className="text-muted-foreground">sem nome</span>}</td>
                  <td className="py-1.5 px-2">{keyState(k)}</td>
                  <td className="py-1.5 px-2 whitespace-nowrap">{formatDate(k.created_at)}</td>
                  <td className="py-1.5 px-2 whitespace-nowrap">{formatWhen(k.last_used_at)}</td>
                  <td className="py-1.5 pl-2 whitespace-nowrap">{k.expires_at ? formatDate(k.expires_at) : "não expira"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  );
}

function ProjectsCard({ user }: { user: AdminUserDetail }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Projetos</CardTitle>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        {user.projects.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nenhum projeto.</p>
        ) : (
          <table className="w-full text-sm">
            <caption className="sr-only">Projetos do usuário</caption>
            <thead>
              <tr className="text-left text-xs text-muted-foreground">
                <th className="font-medium py-1 pr-2">Nome</th>
                <th className="font-medium py-1 px-2 text-right">Pastas</th>
                <th className="font-medium py-1 px-2 text-right">Jobs</th>
                <th className="font-medium py-1 pl-2">Criado</th>
              </tr>
            </thead>
            <tbody>
              {user.projects.map((p) => (
                <tr key={p.id} className="border-t">
                  <td className="py-1.5 pr-2">
                    {p.name} {p.archived && <Pill tone="muted">arquivado</Pill>}
                  </td>
                  <td className="py-1.5 px-2 text-right tabular-nums">{formatCount(p.folder_count)}</td>
                  <td className="py-1.5 px-2 text-right tabular-nums">{formatCount(p.jobs_total)}</td>
                  <td className="py-1.5 pl-2 whitespace-nowrap">{formatDate(p.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  );
}

function BindingsCard({ user }: { user: AdminUserDetail }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Papéis (IAM)</CardTitle>
        <CardDescription>
          Concessões ativas. Para conceder ou revogar, use{" "}
          <Link href="/admin/access" className="underline">Acesso</Link>.
          {user.is_root && " O root tem acesso de bootstrap, que não depende de concessão."}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {user.iam_bindings.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nenhuma concessão ativa.</p>
        ) : (
          <ul className="space-y-1 text-sm">
            {user.iam_bindings.map((b) => (
              <li key={b.id} className="flex flex-wrap items-center gap-2">
                <Pill tone="info">{b.role}</Pill>
                <span className="text-muted-foreground">
                  {b.family === "engines" ? "engines" : "plataforma"} · expira em {formatDate(b.expires_at)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
