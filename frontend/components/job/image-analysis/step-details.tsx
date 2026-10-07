import { CopyButton } from "../result-primitives";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import type { ImageFullStepResult } from "@/types/api";
import { reasonText } from "./analysis-model";
import { regionColor } from "./image-canvas";

export function StepDetails({
  step,
  activeRegion,
  onSelectRegion,
}: {
  step: ImageFullStepResult;
  activeRegion: number | null;
  onSelectRegion: (index: number) => void;
}) {
  const regions = step.regions ?? [];
  const lines = step.lines ?? [];
  const text = step.text || lines.map((line) => line.text).join("\n");
  const reason = reasonText(step.reason_code);
  return (
    <div className="space-y-4">
      {(reason || step.truncated) && (
        <div
          className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 text-sm"
          role="status"
        >
          {reason && <p>{reason}</p>}
          {step.truncated && (
            <p>
              O limite de tokens interrompeu a saída. O conteúdo disponível foi
              preservado.
            </p>
          )}
        </div>
      )}
      <Tabs defaultValue="result" className="min-w-0">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="result">Resultado</TabsTrigger>
          <TabsTrigger value="regions">
            Regiões ({regions.length || lines.length})
          </TabsTrigger>
          <TabsTrigger value="details">Detalhes</TabsTrigger>
        </TabsList>
        <TabsContent value="result" className="mt-4 space-y-3">
          {text ? (
            <>
              <div className="flex justify-end">
                <CopyButton text={text} label="Copiar texto" />
              </div>
              <p className="max-h-80 overflow-y-auto whitespace-pre-wrap break-words text-sm leading-relaxed">
                {text}
              </p>
            </>
          ) : (
            <p className="rounded-lg bg-muted/30 p-4 text-sm text-muted-foreground">
              {step.status !== "succeeded"
                ? "Esta etapa não tem conteúdo disponível."
                : regions.length > 0
                  ? `${regions.length} regiões identificadas. Consulte a imagem ou a aba Regiões.`
                  : "Nenhum texto ou região foi detectado nesta tarefa."}
            </p>
          )}
        </TabsContent>
        <TabsContent value="regions" className="mt-4">
          {regions.length > 0 ? (
            <ol className="max-h-72 space-y-1 overflow-y-auto">
              {regions.map((region, index) => (
                <li key={index}>
                  <button
                    type="button"
                    aria-pressed={activeRegion === index}
                    onClick={() => onSelectRegion(index)}
                    className={cn(
                      "flex w-full items-start gap-3 rounded-lg border border-transparent p-3 text-left text-sm hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      activeRegion === index &&
                        "border-primary/20 bg-primary/5",
                    )}
                  >
                    <span
                      className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded text-[11px] font-semibold text-white"
                      style={{ backgroundColor: regionColor(index) }}
                    >
                      {index + 1}
                    </span>
                    <span className="min-w-0 flex-1 break-words">
                      {region.label || `Região ${index + 1}`}
                      {region.bbox && (
                        <span className="mt-1 block text-xs text-muted-foreground">
                          {region.bbox
                            .map((value) => Math.round(value))
                            .join(", ")}{" "}
                          px
                        </span>
                      )}
                    </span>
                    {region.score != null && (
                      <span className="text-xs tabular-nums text-muted-foreground">
                        {(region.score * 100).toFixed(1)}%
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ol>
          ) : lines.length > 0 ? (
            <ol className="max-h-72 space-y-2 overflow-auto text-sm">
              {lines.map((line, index) => (
                <li key={index} className="break-words">
                  <span className="mr-2 text-muted-foreground">
                    {index + 1}.
                  </span>
                  {line.text}
                </li>
              ))}
            </ol>
          ) : (
            <p className="p-4 text-sm text-muted-foreground">
              Esta tarefa não produziu regiões.
            </p>
          )}
        </TabsContent>
        <TabsContent value="details" className="mt-4 space-y-4">
          <dl className="grid grid-cols-2 gap-3 text-xs">
            <div>
              <dt className="text-muted-foreground">Tarefa</dt>
              <dd className="mt-1 break-all font-mono">{step.task}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Processamento</dt>
              <dd className="mt-1">
                {step.duration_ms == null
                  ? "Não disponível"
                  : `${(step.duration_ms / 1000).toLocaleString("pt-BR")} s`}
              </dd>
            </div>
            {step.reason_code && (
              <div className="col-span-2">
                <dt className="text-muted-foreground">Código do resultado</dt>
                <dd className="mt-1 break-all font-mono">{step.reason_code}</dd>
              </div>
            )}
          </dl>
          <details>
            <summary className="cursor-pointer text-sm font-medium">
              Entrada da tarefa
            </summary>
            <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-all rounded-lg bg-muted/40 p-3 text-xs">
              {JSON.stringify(step.input, null, 2)}
            </pre>
          </details>
          <details>
            <summary className="cursor-pointer text-sm font-medium">
              Saída estruturada do modelo
            </summary>
            <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap break-all rounded-lg bg-muted/40 p-3 text-xs">
              {JSON.stringify(step.output ?? {}, null, 2)}
            </pre>
          </details>
        </TabsContent>
      </Tabs>
    </div>
  );
}
