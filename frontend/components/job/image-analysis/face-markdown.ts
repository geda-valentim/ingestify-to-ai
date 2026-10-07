import type { FacialBlock } from "@/types/faces";

export function faceMarkdown(analysis: FacialBlock): string {
  const lines = ["## Rostos e expressões", "", "Estimativa de expressão visível; não determina o estado emocional. Scores não calibrados.", "",
    `Cobertura: ${analysis.coverage.task_families_completed}/${analysis.coverage.task_families_total} famílias.`,
    `Detecção: ${analysis.detection.status}; ${analysis.detection.selected_count ?? 0} de ${analysis.detection.detected_count ?? 0} rostos selecionados; ${analysis.detection.omitted_count ?? 0} omitidos.`,
    `Motivo: ${analysis.detection.reason_code ?? "—"}`, "", "### Parâmetros e modelos", "", "```json", JSON.stringify({ request: analysis.request, models: analysis.models }, null, 2), "```"];
  for (const face of analysis.faces) {
    lines.push("", `### ${face.face_id}`, "", `Caixa: ${JSON.stringify(face.bbox)}; confiança de detecção: ${face.detection_confidence.toFixed(4)}.`,
      `Movimentos: ${face.movements.status}; motivo: ${face.movements.reason_code ?? "—"}; ${face.movements.landmarks?.length ?? 0} landmarks.`,
      `Expressão: ${face.expression.label ?? face.expression.decision ?? face.expression.status}; motivo: ${face.expression.reason_code ?? "—"}.`);
    for (const score of face.expression.scores ?? []) lines.push(`- ${score.label}: ${score.score.toFixed(4)}`);
    lines.push("", "Coeficientes de movimento:");
    for (const item of face.movements.blendshapes ?? []) lines.push(`- ${item.name}: ${item.score.toFixed(4)}`);
  }
  lines.push("", "### Etapas", "");
  for (const step of analysis.steps) lines.push(`- ${step.operation} ${step.face_id ?? ""}: ${step.status}; motivo: ${step.reason_code ?? "—"}`);
  return lines.join("\n") + "\n";
}
