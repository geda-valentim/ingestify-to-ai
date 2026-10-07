import {
  AlertCircle,
  CheckCircle2,
  CircleDashed,
  Loader2,
  MinusCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";

const STATES = {
  completed: {
    label: "Concluída",
    icon: CheckCircle2,
    color: "text-emerald-700 bg-emerald-500/10 dark:text-emerald-400",
  },
  succeeded: {
    label: "Concluída",
    icon: CheckCircle2,
    color: "text-emerald-700 bg-emerald-500/10 dark:text-emerald-400",
  },
  partial: {
    label: "Parcial",
    icon: AlertCircle,
    color: "text-amber-700 bg-amber-500/10 dark:text-amber-400",
  },
  failed: {
    label: "Falhou",
    icon: AlertCircle,
    color: "text-destructive bg-destructive/10",
  },
  cancelled: {
    label: "Cancelada",
    icon: MinusCircle,
    color: "text-muted-foreground bg-muted",
  },
  skipped: {
    label: "Não executada",
    icon: MinusCircle,
    color: "text-muted-foreground bg-muted",
  },
  not_applicable: {
    label: "Não se aplica",
    icon: MinusCircle,
    color: "text-muted-foreground bg-muted",
  },
  pending: {
    label: "Aguardando",
    icon: CircleDashed,
    color: "text-muted-foreground bg-muted",
  },
  queued: {
    label: "Na fila",
    icon: CircleDashed,
    color: "text-muted-foreground bg-muted",
  },
  processing: {
    label: "Em análise",
    icon: Loader2,
    color: "text-primary bg-primary/10",
  },
  running: {
    label: "Em análise",
    icon: Loader2,
    color: "text-primary bg-primary/10",
  },
};

export function AnalysisStatus({ status }: { status: string }) {
  const state = STATES[status as keyof typeof STATES] ?? STATES.pending;
  const Icon = state.icon;
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium",
        state.color,
      )}
    >
      <Icon
        className={cn(
          "h-3.5 w-3.5",
          ["processing", "running"].includes(status) && "animate-spin",
        )}
      />
      {state.label}
    </span>
  );
}
