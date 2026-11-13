"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Search } from "lucide-react";
import { adminUsersApi } from "@/lib/admin-users-api";
import { useAuthStore } from "@/lib/store/auth";
import { formatBytes } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { LoadingCards, adminRetry } from "@/components/admin/compute-ui";
import { UserBadges, UsersError, formatCount, formatWhen } from "@/components/admin/users-ui";
import type { AdminUserSort } from "@/types/admin-users";

const PAGE_SIZE = 50;

const SORTS: { value: AdminUserSort; label: string }[] = [
  { value: "last_job_at", label: "Último job" },
  { value: "jobs_total", label: "Jobs" },
  { value: "bytes_uploaded", label: "Volume enviado" },
  { value: "created_at", label: "Cadastro" },
];

/**
 * Admin → Usuários (spec 0024): every user with a usage summary. Read-only; the
 * API authorizes each call with `platform.users.read`.
 */
export default function UsersPage() {
  const token = useAuthStore((s) => s.token);
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<AdminUserSort>("last_job_at");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [offset, setOffset] = useState(0);

  // Debounced search: one request after typing stops, back to the first page.
  useEffect(() => {
    const t = setTimeout(() => {
      setQ(search.trim());
      setOffset(0);
    }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const query = useQuery({
    queryKey: ["admin", "users", token, q, sort, order, offset],
    queryFn: () => adminUsersApi.list({ q, sort, order, limit: PAGE_SIZE, offset }),
    enabled: !!token,
    retry: adminRetry,
    placeholderData: keepPreviousData,
  });

  if (query.isLoading) return <LoadingCards count={1} label="Carregando usuários" />;
  if (query.error && !query.data) {
    return <UsersError error={query.error} what="os usuários" onRetry={() => query.refetch()} />;
  }
  const data = query.data!;
  const last = Math.min(offset + PAGE_SIZE, data.total);

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Usuários</CardTitle>
        <CardDescription>
          Todos os usuários, ativos e inativos, com o uso de cada um. Só leitura.
          {data.orphan_jobs > 0 &&
            ` ${formatCount(data.orphan_jobs)} jobs são de usuários apagados e não aparecem aqui.`}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" aria-hidden />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Buscar por e-mail ou username"
              aria-label="Buscar usuários"
              className="pl-8"
            />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">Ordenar por</span>
            <select
              value={sort}
              onChange={(e) => {
                setSort(e.target.value as AdminUserSort);
                setOffset(0);
              }}
              className="h-9 rounded-md border bg-background px-2 text-sm"
            >
              {SORTS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setOrder(order === "desc" ? "asc" : "desc");
              setOffset(0);
            }}
            aria-label={order === "desc" ? "Ordem decrescente; inverter" : "Ordem crescente; inverter"}
          >
            {order === "desc" ? "Maior primeiro" : "Menor primeiro"}
          </Button>
        </div>

        {query.error ? <UsersError error={query.error} what="a lista atualizada" /> : null}

        {data.items.length === 0 ? (
          <p className="text-sm text-muted-foreground py-6 text-center">
            {q ? `Nenhum usuário encontrado para "${q}".` : "Nenhum usuário cadastrado."}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <caption className="sr-only">Usuários e uso</caption>
              <thead>
                <tr className="text-left text-xs text-muted-foreground">
                  <th className="font-medium py-1 pr-2">Usuário</th>
                  <th className="font-medium py-1 px-2 text-right">Jobs</th>
                  <th className="font-medium py-1 px-2 text-right">Falhas</th>
                  <th className="font-medium py-1 px-2 text-right">Enviado</th>
                  <th className="font-medium py-1 px-2 text-right">Páginas</th>
                  <th className="font-medium py-1 px-2 text-right">Chaves</th>
                  <th className="font-medium py-1 px-2 text-right">Projetos</th>
                  <th className="font-medium py-1 pl-2">Último job</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((u) => (
                  <tr key={u.id} className="border-t align-top">
                    <td className="py-2 pr-2">
                      <Link
                        href={`/admin/users/${encodeURIComponent(u.id)}`}
                        className="font-medium hover:underline"
                      >
                        {u.username}
                      </Link>{" "}
                      <UserBadges user={u} />
                      <div className="text-xs text-muted-foreground break-all">{u.email}</div>
                    </td>
                    <td className="py-2 px-2 text-right tabular-nums">{formatCount(u.jobs_total)}</td>
                    <td className="py-2 px-2 text-right tabular-nums">
                      {formatCount(u.jobs_by_status.failed ?? 0)}
                    </td>
                    <td className="py-2 px-2 text-right tabular-nums whitespace-nowrap">
                      {formatBytes(u.bytes_uploaded)}
                    </td>
                    <td className="py-2 px-2 text-right tabular-nums">{formatCount(u.pages_total)}</td>
                    <td className="py-2 px-2 text-right tabular-nums">{u.api_keys_active}</td>
                    <td className="py-2 px-2 text-right tabular-nums">{u.projects_total}</td>
                    <td className="py-2 pl-2 whitespace-nowrap">{formatWhen(u.last_job_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
          <span className="text-muted-foreground">
            {data.total === 0 ? "0 usuários" : `${offset + 1}–${last} de ${formatCount(data.total)}`}
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              <ChevronLeft className="h-4 w-4" aria-hidden /> Anterior
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={last >= data.total}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Próxima <ChevronRight className="h-4 w-4" aria-hidden />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
