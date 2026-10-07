import type {
  ImageFullAnalysisResult,
  ImageFullStepResult,
  VisionTask,
} from "@/types/api";

export type AnalysisFamily =
  ImageFullAnalysisResult["coverage"]["families"][number];

export const FAMILY_GROUPS = [
  {
    label: "Descrição",
    tasks: ["<CAPTION>", "<DETAILED_CAPTION>", "<MORE_DETAILED_CAPTION>"],
  },
  { label: "Texto", tasks: ["<OCR>", "<OCR_WITH_REGION>", "<REGION_TO_OCR>"] },
  {
    label: "Objetos e localização",
    tasks: [
      "<OD>",
      "<DENSE_REGION_CAPTION>",
      "<REGION_PROPOSAL>",
      "<CAPTION_TO_PHRASE_GROUNDING>",
      "<OPEN_VOCABULARY_DETECTION>",
    ],
  },
  {
    label: "Regiões e segmentação",
    tasks: [
      "<REFERRING_EXPRESSION_SEGMENTATION>",
      "<REGION_TO_SEGMENTATION>",
      "<REGION_TO_CATEGORY>",
      "<REGION_TO_DESCRIPTION>",
    ],
  },
];

const REASONS: Record<string, string> = {
  inference_failed: "Não foi possível concluir esta tarefa.",
  dependency_failed: "Uma tarefa anterior não produziu a entrada necessária.",
  no_queries: "Não há uma consulta disponível para esta tarefa.",
  no_regions: "Não há uma região disponível para esta tarefa.",
  cancelled:
    "A análise foi cancelada. Os resultados concluídos foram preservados.",
  deadline_exceeded: "O tempo disponível para a análise terminou.",
  call_limit: "O limite de chamadas desta análise foi atingido.",
  checkpoint_unavailable: "O resultado desta etapa está indisponível.",
  checkpoint_invalid: "Não foi possível ler o resultado desta etapa.",
  checkpoint_checksum_mismatch:
    "Não foi possível verificar a integridade desta etapa.",
  uncertain_attempt:
    "A execução foi interrompida antes de confirmar o resultado.",
};

export function reasonText(code?: string | null) {
  return code
    ? (REASONS[code] ?? "Esta etapa não produziu um resultado disponível.")
    : null;
}

export function instanceLabel(step: ImageFullStepResult, index: number) {
  if (step.input.text_input) return step.input.text_input;
  if (step.input.origin === "full_image") return "Imagem inteira";
  return step.input.region ? `Região ${index + 1}` : "Imagem inteira";
}

export function defaultStep(image: ImageFullAnalysisResult) {
  return (
    image.results.find(
      (step) => step.task === "<OD>" && step.status === "succeeded",
    ) ??
    image.results.find((step) => step.status === "succeeded") ??
    image.results[0]
  );
}

export function familySteps(image: ImageFullAnalysisResult, task: VisionTask) {
  return image.results.filter((step) => step.task === task);
}

export function analysisMarkdown(image: ImageFullAnalysisResult) {
  const labels = new Map(
    image.coverage.families.map((family) => [family.task, family.label]),
  );
  return [
    `# Full Analysis\n\n${image.description || ""}`,
    ...image.results.map(
      (step) =>
        `## ${labels.get(step.task) ?? step.task} · ${step.step_id}\n${step.status}\n${step.text || step.reason_code || "Nenhum resultado detectado."}`,
    ),
  ].join("\n\n");
}
