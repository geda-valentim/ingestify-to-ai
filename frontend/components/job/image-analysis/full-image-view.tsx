"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import type { ImageFullAnalysisResult, VisionTask } from "@/types/api";
import { defaultStep, familySteps, instanceLabel } from "./analysis-model";
import { AnalysisSummary } from "./analysis-summary";
import { AnalysisStatus } from "./analysis-status";
import { FamilyNavigation } from "./family-navigation";
import { ImageCanvas } from "./image-canvas";
import { StepDetails } from "./step-details";

export function FullImageView({
  image,
  fileName,
}: {
  image: ImageFullAnalysisResult;
  fileName: string;
}) {
  const [stepId, setStepId] = useState(defaultStep(image)?.step_id);
  const [activeRegion, setActiveRegion] = useState<number | null>(null);
  const selected =
    image.results.find((step) => step.step_id === stepId) ?? defaultStep(image);
  const family = image.coverage.families.find(
    (item) => item.task === selected?.task,
  );
  const instances = selected ? familySteps(image, selected.task) : [];
  const selectStep = (id: string) => {
    setStepId(id);
    setActiveRegion(null);
  };
  const selectFamily = (task: VisionTask) => {
    const steps = familySteps(image, task);
    const step = steps.find((item) => item.status === "succeeded") ?? steps[0];
    if (step) selectStep(step.step_id);
  };
  return (
    <div className="min-w-0 space-y-5">
      <AnalysisSummary image={image} fileName={fileName} />
      <div className="grid min-w-0 gap-5 lg:grid-cols-[200px_minmax(0,1fr)] xl:grid-cols-[220px_minmax(0,1fr)]">
        <FamilyNavigation
          families={image.coverage.families}
          selected={selected?.task}
          onSelect={selectFamily}
        />
        {selected ? (
          <section
            aria-label="Resultado selecionado"
            className="min-w-0 space-y-4 rounded-xl border bg-card p-3 md:p-4"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="min-w-0">
                <h3 className="font-semibold">
                  {family?.label ?? selected.task}
                </h3>
                <p className="mt-1 text-xs text-muted-foreground">
                  {instances.length > 1
                    ? `${instances.length} resultados nesta família`
                    : "Resultado da imagem inteira"}
                </p>
              </div>
              <AnalysisStatus status={selected.status} />
            </div>
            {instances.length > 1 && (
              <div
                className="flex flex-wrap gap-2"
                role="group"
                aria-label="Resultados da família"
              >
                {instances.map((step, index) => (
                  <button
                    key={step.step_id}
                    type="button"
                    title={instanceLabel(step, index)}
                    aria-pressed={selected.step_id === step.step_id}
                    onClick={() => selectStep(step.step_id)}
                    className={cn(
                      "max-w-full rounded-lg border px-3 py-2 text-xs transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      selected.step_id === step.step_id &&
                        "border-primary/40 bg-primary/10 text-primary",
                    )}
                  >
                    <span className="block max-w-52 truncate">
                      {instanceLabel(step, index)}
                    </span>
                    {step.status !== "succeeded" && (
                      <span className="mt-1 block text-[10px] text-muted-foreground">
                        {step.status === "failed" ? "Falhou" : "Sem resultado"}
                      </span>
                    )}
                  </button>
                ))}
              </div>
            )}
            <ImageCanvas
              key={selected.step_id}
              image={image}
              regions={selected.regions}
              lines={selected.lines}
              controls
              activeRegion={activeRegion}
              onSelectRegion={(index) =>
                setActiveRegion(activeRegion === index ? null : index)
              }
            />
            <StepDetails
              key={selected.step_id + "-details"}
              step={selected}
              activeRegion={activeRegion}
              onSelectRegion={(index) =>
                setActiveRegion(activeRegion === index ? null : index)
              }
            />
          </section>
        ) : (
          <p className="rounded-xl border p-6 text-sm text-muted-foreground">
            Nenhuma etapa está disponível para consulta.
          </p>
        )}
      </div>
      <details className="rounded-xl border bg-card p-4 text-sm">
        <summary className="cursor-pointer font-medium">
          Sobre esta análise
        </summary>
        <dl className="mt-4 grid gap-4 text-xs sm:grid-cols-2">
          <div>
            <dt className="text-muted-foreground">Modelo</dt>
            <dd className="mt-1 break-all">{image.model.model_id}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">
              Consultas e regiões selecionadas
            </dt>
            <dd className="mt-1">
              {image.resolved_inputs.queries?.length ?? 0} consultas ·{" "}
              {image.resolved_inputs.regions?.length ?? 0} regiões
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Chamadas executadas</dt>
            <dd className="mt-1">{image.calls_started}/32</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Candidatos omitidos</dt>
            <dd className="mt-1">
              {image.resolved_inputs.omitted_candidates?.length ?? 0}
            </dd>
          </div>
        </dl>
        <p className="mt-4 text-xs text-muted-foreground">
          As camadas usam as coordenadas da imagem de referência. Para GIF e
          TIFF, a análise usa o primeiro frame.
        </p>
        <details className="mt-4">
          <summary className="cursor-pointer text-xs">
            Entradas resolvidas
          </summary>
          <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap break-all rounded-lg bg-muted/40 p-3 text-xs">
            {JSON.stringify(image.resolved_inputs, null, 2)}
          </pre>
        </details>
      </details>
    </div>
  );
}
