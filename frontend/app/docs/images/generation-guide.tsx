import openapi from "@/docs/doc2md_openapi.json";
import { P, Subheading, Table } from "../docs-content-primitives";
import type { DocsLang } from "../topics";

function constraints(schema: Record<string, unknown>): string {
  if (Array.isArray(schema.anyOf))
    return schema.anyOf.map((choice) => constraints(choice)).join(" | ");
  const result = [String(schema.type ?? "")];
  if (schema.enum) result.push(JSON.stringify(schema.enum));
  if (schema.const !== undefined) result.push(JSON.stringify(schema.const));
  for (const [key, symbol] of [
    ["minimum", "≥"],
    ["exclusiveMinimum", ">"],
    ["maximum", "≤"],
    ["exclusiveMaximum", "<"],
  ]) {
    if (schema[key] !== undefined) result.push(`${symbol} ${schema[key]}`);
  }
  return result.join(" ");
}

export function GenerationGuide({ lang }: { lang: DocsLang }) {
  const pt = lang === "pt";
  return (
    <div className="space-y-4">
      <Subheading>
        {pt ? "Parâmetros de geração" : "Generation parameters"}
      </Subheading>
      <P small>
        {pt
          ? "Em single, envie generation na raiz; em Full Analysis, use full_options.generation. No multipart, ambos são strings JSON. Tipos, limites e padrões abaixo vêm do schema publicado da API. null em max_new_tokens/num_beams usa o valor configurado no worker, divulgado por generation_defaults em /images/capabilities."
          : "In single mode, send root-level generation; in Full Analysis use full_options.generation. Both are JSON strings in multipart. The types, limits and defaults below come from the published API schema. null for max_new_tokens/num_beams uses the worker setting advertised in generation_defaults by /images/capabilities."}
      </P>
      <Table
        head={
          pt
            ? ["Parâmetro", "Tipo / limite", "Padrão"]
            : ["Parameter", "Type / limit", "Default"]
        }
        rows={Object.entries(
          openapi.components.schemas.VisionGenerationOptions.properties,
        ).map(([key, schema]) => [
          key,
          constraints(schema),
          "default" in schema ? JSON.stringify(schema.default) : "worker",
        ])}
      />
      <P small>
        {pt
          ? "temperature, top_p e top_k diferentes do padrão exigem do_sample=true. length_penalty ou early_stopping personalizados exigem num_beams>1. Opções incompatíveis ou desconhecidas retornam 422. O limite de tokens é por etapa e uma saída truncada pode tornar Full Analysis partial."
          : "Nondefault temperature, top_p and top_k require do_sample=true. Custom length_penalty or early_stopping require num_beams>1. Incompatible or unknown options return 422. Token limits apply per step; truncated output can make Full Analysis partial."}
      </P>
    </div>
  );
}
