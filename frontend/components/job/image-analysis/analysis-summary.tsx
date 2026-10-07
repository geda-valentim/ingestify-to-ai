import { Download, ScanLine, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { downloadText } from "@/lib/utils";
import type { ImageFullAnalysisResult } from "@/types/api";
import { analysisMarkdown, reasonText } from "./analysis-model";
import { AnalysisStatus } from "./analysis-status";

export function AnalysisSummary({
  image,
  fileName,
}: {
  image: ImageFullAnalysisResult;
  fileName: string;
}) {
  const coverage = image.coverage;
  const percentage = Math.round(
    (100 * coverage.task_families_completed) /
      Math.max(1, coverage.task_families_total),
  );
  return (
    <section
      className="overflow-hidden rounded-xl border bg-card"
      aria-label="Resumo da análise"
    >
      <div className="flex flex-wrap items-start justify-between gap-4 p-4 md:p-5">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <Sparkles className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-xl font-semibold tracking-tight">
              Full Analysis
            </h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Descrição, texto, objetos e regiões em uma única análise
            </p>
          </div>
        </div>
        <AnalysisStatus status={image.analysis_status} />
      </div>
      <div className="grid grid-cols-3 divide-x border-y bg-muted/20 py-3">
        {[
          [
            String(coverage.task_families_completed) +
              "/" +
              coverage.task_families_total,
            "Famílias concluídas",
          ],
          [
            String(coverage.instances_completed) +
              "/" +
              coverage.instances_planned,
            "Resultados concluídos",
          ],
          [
            (image.duration_ms / 1000).toLocaleString("pt-BR", {
              maximumFractionDigits: 1,
            }) + " s",
            "Processamento",
          ],
        ].map(([value, label]) => (
          <div key={label} className="min-w-0 px-2 text-center md:px-4">
            <p className="text-lg font-semibold tabular-nums md:text-xl">
              {value}
            </p>
            <p className="mt-1 text-[11px] text-muted-foreground md:text-xs">
              {label}
            </p>
          </div>
        ))}
      </div>
      <div className="space-y-3 p-4 md:p-5">
        <p className="whitespace-pre-wrap break-words text-sm leading-relaxed">
          {image.description || "Sem descrição disponível."}
        </p>
        {image.analysis_status !== "completed" && (
          <p className="text-sm text-muted-foreground" role="status">
            {reasonText(image.reason_code) ||
              "Algumas tarefas não foram concluídas. Explore as famílias para consultar os resultados disponíveis."}
          </p>
        )}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
            <ScanLine className="h-3.5 w-3.5" />
            {image.width} × {image.height} px
          </span>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                downloadText(
                  `${fileName}.full.json`,
                  JSON.stringify(image, null, 2),
                  "application/json",
                )
              }
            >
              <Download className="mr-1.5 h-3.5 w-3.5" />
              Download JSON
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                downloadText(
                  `${fileName}.full.md`,
                  analysisMarkdown(image),
                  "text/markdown",
                )
              }
            >
              <Download className="mr-1.5 h-3.5 w-3.5" />
              Download Markdown
            </Button>
          </div>
        </div>
      </div>
      <div
        className="h-1 bg-muted"
        aria-label={`${percentage}% das famílias concluídas`}
      >
        <div
          className="h-full bg-primary"
          style={{ width: `${percentage}%` }}
        />
      </div>
    </section>
  );
}
