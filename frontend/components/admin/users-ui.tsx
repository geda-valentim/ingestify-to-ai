"use client";

import { formatDistanceToNow } from "date-fns";
import { ptBR } from "date-fns/locale";
import { Crown, ShieldCheck, UserX } from "lucide-react";
import { ApiError } from "@/lib/api";
import { parseApiDate } from "@/lib/utils";
import { AdminError } from "@/components/admin/admin-error";
import { ForbiddenCard, Pill } from "@/components/admin/compute-ui";

/** Admin → Usuários (spec 0024): small pieces shared by the list and the detail. */

export function formatWhen(iso: string | null | undefined, never = "nunca"): string {
  if (!iso) return never;
  try {
    return formatDistanceToNow(parseApiDate(iso), { addSuffix: true, locale: ptBR });
  } catch {
    return iso;
  }
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return parseApiDate(iso).toLocaleDateString("pt-BR");
  } catch {
    return iso;
  }
}

export function formatCount(n: number): string {
  return n.toLocaleString("pt-BR");
}

export const STATUS_LABELS: Record<string, string> = {
  completed: "concluídos",
  failed: "com falha",
  partial: "parciais",
  processing: "processando",
  queued: "na fila",
  cancelled: "cancelados",
};

export function UserBadges({
  user,
}: {
  user: { is_root: boolean; is_admin: boolean; is_active: boolean };
}) {
  return (
    <span className="inline-flex flex-wrap gap-1">
      {user.is_root && (
        <Pill tone="info" icon={Crown}>
          root
        </Pill>
      )}
      {user.is_admin && !user.is_root && (
        <Pill tone="info" icon={ShieldCheck}>
          admin
        </Pill>
      )}
      {!user.is_active && (
        <Pill tone="warn" icon={UserX}>
          inativo
        </Pill>
      )}
    </span>
  );
}

/** 403 → the same forbidden card as the other sections; anything else → the guided error. */
export function UsersError({
  error,
  what,
  onRetry,
}: {
  error: unknown;
  what: string;
  onRetry?: () => void;
}) {
  if (error instanceof ApiError && error.status === 403) return <ForbiddenCard />;
  return (
    <AdminError
      error={error}
      title={`Não foi possível carregar ${what}`}
      fallback="Erro desconhecido"
      actions={onRetry ? { retry: onRetry } : {}}
    />
  );
}
