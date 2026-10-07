"use client";

import { useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  AlertTriangle,
  Ban,
  Check,
  CheckCircle2,
  CircleDollarSign,
  Copy,
  HelpCircle,
  Loader2,
  PauseCircle,
  RefreshCw,
  ShieldAlert,
  Terminal,
} from "lucide-react";
import { ApiError } from "@/lib/api";
import { canOpenAdminSection } from "@/lib/admin-nav";
import { useAuthStore } from "@/lib/store/auth";
import { cn, parseApiDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type {
  DeployState,
  EngineHealth,
  EngineStatus,
  Feature,
} from "@/types/compute";
import { FEATURE_TITLES } from "@/types/compute";
import { formatDistanceToNow } from "date-fns";

/** Where the engines CLI runs (backend/scripts/engines.py is baked into the api image). */
export const ENGINES_CLI = "docker compose exec api python scripts/engines.py";
/** The CLI commands that need the private key (test, modal-deploy) run in worker-remote. */
export const ENGINES_CLI_REMOTE =
  "docker compose --profile engines run --rm worker-remote python scripts/engines.py";

type Tone = "ok" | "info" | "warn" | "bad" | "muted";

const TONE_CLASSES: Record<Tone, string> = {
  ok: "border-green-600/30 bg-green-500/10 text-green-700 dark:text-green-400",
  info: "border-blue-600/30 bg-blue-500/10 text-blue-700 dark:text-blue-400",
  warn: "border-amber-600/30 bg-amber-500/10 text-amber-700 dark:text-amber-400",
  bad: "border-red-600/30 bg-red-500/10 text-red-700 dark:text-red-400",
  muted: "border-border bg-muted text-muted-foreground",
};

/** Status is never colour-only: every pill carries an icon and a word. */
export function Pill({
  tone,
  icon: Icon,
  children,
  title,
}: {
  tone: Tone;
  icon?: React.ComponentType<{ className?: string }>;
  children: React.ReactNode;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap",
        TONE_CLASSES[tone],
      )}
    >
      {Icon && <Icon className="h-3 w-3 shrink-0" aria-hidden />}
      {children}
    </span>
  );
}

const HEALTH: Record<
  EngineHealth,
  {
    tone: Tone;
    label: string;
    icon: React.ComponentType<{ className?: string }>;
  }
> = {
  healthy: { tone: "ok", label: "Healthy", icon: CheckCircle2 },
  unknown: { tone: "muted", label: "Not checked yet", icon: HelpCircle },
  degraded: { tone: "warn", label: "Degraded", icon: AlertTriangle },
  unhealthy: { tone: "bad", label: "Unhealthy", icon: AlertCircle },
  exhausted: { tone: "bad", label: "Budget reached", icon: CircleDollarSign },
};

export function HealthBadge({
  health,
  reason,
}: {
  health: EngineHealth;
  reason?: string | null;
}) {
  const h = HEALTH[health] ?? HEALTH.unknown;
  return (
    <Pill tone={h.tone} icon={h.icon} title={reason ?? undefined}>
      <span className="sr-only">Health: </span>
      {h.label}
    </Pill>
  );
}

export function StatusBadge({ status }: { status: EngineStatus }) {
  if (status === "active")
    return (
      <Pill tone="info" icon={CheckCircle2}>
        Active
      </Pill>
    );
  if (status === "paused")
    return (
      <Pill tone="muted" icon={PauseCircle}>
        Paused
      </Pill>
    );
  return (
    <Pill tone="muted" icon={Ban}>
      Disabled
    </Pill>
  );
}

export function DeployStateBadge({ state }: { state: DeployState }) {
  if (state === "local") return null;
  if (state === "deployed")
    return (
      <Pill tone="ok" icon={CheckCircle2}>
        Deployed
      </Pill>
    );
  if (state === "needs_redeploy")
    return (
      <Pill tone="warn" icon={AlertTriangle}>
        Needs redeploy
      </Pill>
    );
  return (
    <Pill tone="muted" icon={AlertCircle}>
      Not deployed
    </Pill>
  );
}

export function featureTitle(feature: string): string {
  return FEATURE_TITLES[feature as Feature] ?? feature;
}

export function formatUsd(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(n)) return String(value);
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: n !== 0 && Math.abs(n) < 0.01 ? 4 : 2,
  }).format(n);
}

export function formatAgo(iso: string | null | undefined): string {
  if (!iso) return "never";
  try {
    return formatDistanceToNow(parseApiDate(iso), { addSuffix: true });
  } catch {
    return iso;
  }
}

export function formatSeconds(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 60) return `${seconds} s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  return `${(seconds / 3600).toFixed(1)} h`;
}

/**
 * A labelled bar with its value in text (role="meter"). `tone` follows the share used;
 * values above `max` are clamped visually but stated in the text.
 */
export function Meter({
  value,
  max,
  label,
  valueText,
  className,
}: {
  value: number;
  max: number;
  label: string;
  valueText: string;
  className?: string;
}) {
  const pct = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
  const ratio = max > 0 ? value / max : 0;
  const bar =
    ratio > 1 ? "bg-red-500" : ratio >= 0.85 ? "bg-amber-500" : "bg-primary";
  return (
    <div className={cn("space-y-1", className)}>
      <div className="flex justify-between gap-2 text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-medium tabular-nums">{valueText}</span>
      </div>
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={value}
        aria-valuetext={valueText}
        className="h-2 w-full overflow-hidden rounded-full bg-secondary"
      >
        <div
          className={cn("h-full rounded-full transition-all", bar)}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

/** A shell command with a copy button: how to change what the screen shows (spec 0003, 4.6.8). */
export function CommandHint({
  title = "To change this",
  commands,
  note,
  className,
}: {
  title?: string;
  commands: string[];
  note?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn("rounded-md border bg-muted/40 p-3 space-y-2", className)}
    >
      <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <Terminal className="h-3.5 w-3.5" aria-hidden />
        {title}
      </p>
      {commands.map((command) => (
        <CommandLine key={command} command={command} />
      ))}
      {note && <p className="text-xs text-muted-foreground">{note}</p>}
    </div>
  );
}

function CommandLine({ command }: { command: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard blocked (insecure origin): the text stays selectable.
    }
  };
  return (
    <div className="flex items-start gap-2">
      <code className="flex-1 min-w-0 overflow-x-auto whitespace-pre rounded bg-background px-2 py-1.5 font-mono text-xs border">
        {command}
      </code>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="h-7 w-7 p-0 shrink-0"
        onClick={copy}
        aria-label={copied ? "Copied" : "Copy command"}
      >
        {copied ? (
          <Check className="h-3.5 w-3.5" />
        ) : (
          <Copy className="h-3.5 w-3.5" />
        )}
      </Button>
    </div>
  );
}

/**
 * A link into /admin/engines, or plain text for a viewer who cannot open that
 * section (e.g. platform_operator on Routing/Status, spec 0014 §4.10).
 */
export function EngineLink({
  href,
  className,
  children,
}: {
  href: string;
  className?: string;
  children: React.ReactNode;
}) {
  const user = useAuthStore((s) => s.user);
  if (!canOpenAdminSection(user, "/admin/engines")) {
    return <span className={className}>{children}</span>;
  }
  return (
    <Link href={href} className={className}>
      {children}
    </Link>
  );
}

export function ForbiddenCard() {
  return (
    <Card className="max-w-xl mx-auto">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ShieldAlert className="h-5 w-5 text-muted-foreground" aria-hidden />
          Acesso não autorizado
        </CardTitle>
        <CardDescription>
          Solicite ao administrador de acesso um papel e uma política que
          permitam esta seção. As permissões são verificadas pela API.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">
          Acesso de bootstrap é administrado separadamente pela instalação.
        </p>
      </CardContent>
    </Card>
  );
}

export function LoadingCards({
  count = 2,
  label = "Loading",
}: {
  count?: number;
  label?: string;
}) {
  return (
    <div className="space-y-4" aria-busy="true" aria-live="polite">
      <span className="sr-only">{label}…</span>
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="h-32 rounded-lg border bg-card motion-safe:animate-pulse"
        />
      ))}
    </div>
  );
}

/** Error card for a failed admin query; a 403 becomes the admin-only card. */
export function QueryError({
  error,
  onRetry,
  what,
}: {
  error: unknown;
  onRetry?: () => void;
  what: string;
}) {
  if (error instanceof ApiError && error.status === 403)
    return <ForbiddenCard />;
  const message = error instanceof Error ? error.message : "Unknown error";
  return (
    <div
      role="alert"
      className="rounded-lg border border-destructive/50 bg-destructive/5 p-4 flex items-start gap-3"
    >
      <AlertCircle
        className="h-5 w-5 text-destructive shrink-0 mt-0.5"
        aria-hidden
      />
      <div className="flex-1 min-w-0">
        <p className="font-medium">Couldn&apos;t load {what}</p>
        <p className="text-sm text-muted-foreground break-words">{message}</p>
      </div>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RefreshCw className="h-4 w-4 mr-2" />
          Retry
        </Button>
      )}
    </div>
  );
}

/** "Updated 5 s ago" + a spinner while a background refetch runs. */
export function Freshness({
  updatedAt,
  fetching,
}: {
  updatedAt: number;
  fetching: boolean;
}) {
  if (!updatedAt) return null;
  return (
    <span
      className="inline-flex items-center gap-1 text-xs text-muted-foreground"
      aria-live="off"
    >
      {fetching && (
        <Loader2 className="h-3 w-3 motion-safe:animate-spin" aria-hidden />
      )}
      Updated {formatDistanceToNow(new Date(updatedAt), { addSuffix: true })}
    </span>
  );
}

/** TanStack `retry` for admin reads: a 4xx (403, 404) will not change by retrying. */
export function adminRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status < 500) return false;
  return failureCount < 2;
}
