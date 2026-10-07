"use client";
import { AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  NEXT_STEP_LABELS,
  guidedError,
  type GuidedError,
} from "@/lib/admin-errors";

/**
 * An admin error banner: the human message first, then the next steps (buttons
 * when the page can perform them, plain items otherwise), and the code small for
 * support. Never shows only a code (spec 0009 CA1).
 */
export function AdminError({
  error,
  guided,
  title,
  actions = {},
  fallback,
  tone = "error",
}: {
  error?: unknown;
  guided?: GuidedError | null;
  title?: string;
  actions?: Partial<Record<string, () => void>>;
  fallback?: string;
  tone?: "error" | "info";
}) {
  const g = guided ?? (error != null ? guidedError(error, fallback) : null);
  if (!g) return null;
  const border =
    tone === "error"
      ? "border-destructive/50 bg-destructive/5"
      : "border-amber-500/50 bg-amber-500/5";
  const reference = [g.code, g.cause].filter(Boolean).join(" → ");
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={`rounded-lg border p-3 text-sm flex items-start gap-3 ${border}`}
    >
      <AlertCircle
        className={`h-5 w-5 shrink-0 mt-0.5 ${tone === "error" ? "text-destructive" : "text-amber-600"}`}
        aria-hidden
      />
      <div className="flex-1 min-w-0 space-y-2">
        {title && <p className="font-medium">{title}</p>}
        <p className="break-words">{g.message}</p>
        {g.technical && (
          <p className="text-xs text-muted-foreground break-words">
            Detalhe: {g.technical}
          </p>
        )}
        {g.nextSteps.length > 0 && (
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground">
              Próximos passos
            </p>
            <div className="flex flex-wrap gap-2">
              {g.nextSteps.map((step) => {
                const label = NEXT_STEP_LABELS[step] || step;
                const run = actions[step];
                return run ? (
                  <Button key={step} size="sm" variant="outline" onClick={run}>
                    {label}
                  </Button>
                ) : (
                  <span
                    key={step}
                    className="rounded border px-2 py-1 text-xs text-muted-foreground"
                  >
                    {label}
                  </span>
                );
              })}
            </div>
          </div>
        )}
        {reference && (
          <p className="text-[11px] text-muted-foreground font-mono">
            Código: {reference}
          </p>
        )}
      </div>
    </div>
  );
}
