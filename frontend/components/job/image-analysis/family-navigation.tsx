import { CheckCircle2, CircleDashed } from "lucide-react";
import { cn } from "@/lib/utils";
import type { VisionTask } from "@/types/api";
import { FAMILY_GROUPS, type AnalysisFamily } from "./analysis-model";

export function FamilyNavigation({
  families,
  selected,
  onSelect,
}: {
  families: AnalysisFamily[];
  selected?: VisionTask;
  onSelect: (task: VisionTask) => void;
}) {
  const known = new Set(FAMILY_GROUPS.flatMap((group) => group.tasks));
  const groups = [
    ...FAMILY_GROUPS,
    {
      label: "Outras análises",
      tasks: families
        .filter((family) => !known.has(family.task))
        .map((family) => family.task),
    },
  ];
  return (
    <nav aria-label="Cobertura das tarefas" className="min-w-0">
      <label className="block text-sm font-medium lg:hidden">
        Família de análise
        <select
          aria-label="Camada da análise"
          value={selected ?? ""}
          onChange={(event) => onSelect(event.target.value as VisionTask)}
          className="mt-2 h-10 w-full min-w-0 rounded-lg border bg-background px-3 text-sm"
        >
          {families.map((family) => (
            <option key={family.task} value={family.task}>
              {family.label} · {family.succeeded}/{family.instances}
            </option>
          ))}
        </select>
      </label>
      <div className="hidden space-y-5 lg:block">
        <div>
          <h3 className="font-semibold">Explorar análise</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            Selecione uma família
          </p>
        </div>
        {groups.map((group) => {
          const items = families.filter((family) =>
            group.tasks.includes(family.task),
          );
          return (
            items.length > 0 && (
              <div key={group.label}>
                <h4 className="mb-2 px-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                  {group.label}
                </h4>
                <div className="space-y-1">
                  {items.map((family) => (
                    <button
                      key={family.task}
                      type="button"
                      aria-pressed={selected === family.task}
                      onClick={() => onSelect(family.task)}
                      className={cn(
                        "flex w-full items-center gap-2 rounded-lg border border-transparent px-2 py-2.5 text-left text-xs transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                        selected === family.task &&
                          "border-primary/20 bg-primary/10 text-primary",
                      )}
                    >
                      {family.completed ? (
                        <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-600 dark:text-emerald-400" />
                      ) : (
                        <CircleDashed className="h-3.5 w-3.5 shrink-0 text-amber-600 dark:text-amber-400" />
                      )}
                      <span className="flex-1">{family.label}</span>
                      <span className="shrink-0 tabular-nums text-muted-foreground">
                        {family.succeeded}/{family.instances}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )
          );
        })}
      </div>
    </nav>
  );
}
