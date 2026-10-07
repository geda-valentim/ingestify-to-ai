"use client";
import type { FaceOptions } from "@/types/faces";

export function FaceOptionsFields({ value, onChange, full = false, disabled = false }: {
  value: FaceOptions; onChange: (value: FaceOptions) => void; full?: boolean; disabled?: boolean;
}) {
  const mode = full ? "expressions" : value.mode ?? "expressions";
  const set = (key: keyof FaceOptions, next: number) => onChange({ ...value, [key]: next });
  return <fieldset disabled={disabled} className="space-y-3 rounded-lg border p-3">
    <legend className="px-1 text-sm font-medium">Rostos e expressões</legend>
    {!full && <label className="block space-y-1 text-sm">Análise facial
      <select aria-label="Análise facial" className="block h-10 w-full rounded border bg-background px-3" value={mode} onChange={event => {
        const next = { ...value, mode: event.target.value as FaceOptions["mode"] };
        if (next.mode === "detection") { delete next.min_face_presence_confidence; delete next.min_expression_score; }
        onChange(next);
      }}><option value="expressions">Detecção, movimentos e expressão estimada</option><option value="detection">Somente detecção de rostos</option></select>
    </label>}
    <div className="grid gap-3 sm:grid-cols-2">
      {([
        ["max_faces", "Máximo de rostos", 5, 1, full ? 5 : 10, 1],
        ["min_detection_confidence", "Confiança mínima de detecção", .5, 0, 1, .05],
        ["min_suppression_threshold", "Limiar de supressão", .3, 0, 1, .05],
        ...(mode === "expressions" ? [
          ["min_face_presence_confidence", "Presença mínima no modelo de movimentos", .5, 0, 1, .05],
          ["min_expression_score", "Score mínimo de expressão", .5, 0, 1, .05],
        ] : []),
        ...(!full ? [["deadline_seconds", "Prazo total (segundos)", 300, 1, 300, 1]] : []),
      ] as [keyof FaceOptions, string, number, number, number, number][]).map(([key, title, fallback, min, max, step]) =>
        <label key={key} className="block space-y-1 text-xs">{title}<input aria-label={title} type="number" required min={min} max={max} step={step}
          value={Number(value[key] ?? fallback)} onChange={e => set(key, e.currentTarget.valueAsNumber)} className="block h-10 w-full rounded border bg-background px-3 text-sm" /></label>)}
    </div>
    <p className="text-xs text-muted-foreground">Estimativa de expressão visível; não determina o estado emocional. O resultado mostra quais rostos foram selecionados.</p>
  </fieldset>;
}
