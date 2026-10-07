import { DOCS_API_URL as API_URL } from "../config";
import { CodeBlock } from "../code-block";
import { A, P, Subheading, Table } from "../docs-content-primitives";
import type { DocsLang } from "../topics";

export function FullAnalysisGuide({ lang }: { lang: DocsLang }) {
  const pt = lang === "pt";
  const key = pt ? "SUA_CHAVE" : "YOUR_KEY";
  const project = pt ? "Imagens" : "Images";
  const block = (code: string) => (
    <CodeBlock code={code} copyLabel={pt ? "Copiar código" : "Copy code"} />
  );
  const curl = (path: string, args: string[], method = "POST") =>
    [
      `curl -X ${method} "${API_URL}${path}"`,
      `  -H "X-API-Key: ${key}"`,
      ...args,
    ].join(" \\\n");
  const options = {
    queries: ["a red car", "license plate"],
    regions: [
      [0, 0, 1, 1],
      [0.1, 0.2, 0.8, 0.9],
    ],
    generation: { max_new_tokens: 1024, num_beams: 3 },
    deadline_seconds: 900,
  };
  return (
    <section
      id="full-analysis"
      className="scroll-mt-24 space-y-4 rounded-xl border bg-muted/20 p-4 md:p-6"
    >
      <Subheading>Full Analysis</Subheading>
      <P>
        {pt
          ? "Use mode=full para executar as 15 famílias de análise em um único job. Sem opções avançadas, o Ingestify deriva consultas e regiões da própria imagem. No front, selecione Full Analysis em /convert e explore descrições, texto, objetos e segmentações na página do job."
          : "Use mode=full to run all 15 analysis families in one job. Without advanced options, Ingestify derives queries and regions from the image. Select Full Analysis in /convert, then explore captions, text, objects and segmentation on the job page."}
      </P>
      <Table
        head={pt ? ["Campo", "Contrato"] : ["Field", "Contract"]}
        rows={[
          [
            "mode",
            pt
              ? "full obrigatório para esta opção; single é o padrão das rotas analyze."
              : "full is required for this option; analyze routes default to single.",
          ],
          [
            "Idempotency-Key",
            pt
              ? "Header obrigatório, 1–128 caracteres. Preserve a chave ao repetir a mesma solicitação após erro de rede."
              : "Required header, 1–128 characters. Keep the key when retrying the same request after a network error.",
          ],
          [
            "full_options.queries",
            pt
              ? "Opcional: 1–3 textos não vazios; até 2000 caracteres no total, incluindo o separador '. '. Omitir ou null deriva consultas; [] é inválido."
              : "Optional: 1–3 nonempty strings; up to 2000 total characters, including the '. ' separator. Omit or use null to derive queries; [] is invalid.",
          ],
          [
            "full_options.regions",
            pt
              ? "Opcional: 1–4 arrays [x_min,y_min,x_max,y_max], com 0 ≤ x_min < x_max ≤ 1 e 0 ≤ y_min < y_max ≤ 1. Omitir ou null deriva regiões; [] é inválido."
              : "Optional: 1–4 arrays [x_min,y_min,x_max,y_max], with 0 ≤ x_min < x_max ≤ 1 and 0 ≤ y_min < y_max ≤ 1. Omit or use null to derive regions; [] is invalid.",
          ],
          [
            "full_options.generation",
            pt
              ? "Parâmetros VisionGenerationOptions compartilhados por todas as etapas. Omitidos max_new_tokens e num_beams usam os defaults do worker."
              : "VisionGenerationOptions shared by all steps. Omitted max_new_tokens and num_beams use worker defaults.",
          ],
          [
            "full_options.deadline_seconds",
            pt
              ? "Inteiro entre 1 e 900; padrão 900. Inclui fila, carga do modelo, inferência e persistência. O limite do servidor pode ser menor."
              : "Integer from 1 to 900; defaults to 900. Includes queueing, model load, inference and persistence. The server limit may be lower.",
          ],
          [
            "wait",
            pt
              ? "false por padrão: 202 com URLs de acompanhamento. true espera até o timeout HTTP; 504 preserva o mesmo job."
              : "Defaults to false: 202 with polling URLs. true waits until the HTTP timeout; 504 preserves the same job.",
          ],
          [
            "datalake",
            pt
              ? "Destino opcional com connection_id, bucket, prefix, partitioning e partition_values. analytics é parte de partitioning. JSON no multipart; objeto no JSON. Disponível em mode=full."
              : "Optional destination with connection_id, bucket, prefix, partitioning and partition_values. analytics belongs inside partitioning. JSON string in multipart; object in JSON. Available in mode=full.",
          ],
        ]}
      />
      <P small>
        {pt
          ? "Full não aceita task, text_input, region ou generation na raiz, mesmo vazios. Use queries, regions e generation dentro de full_options. Mesma chave, imagem, filename, opções, localização, tags e destino retornam o mesmo job. Alterar o payload com a mesma chave retorna 409; job excluído retorna 410. Use uma nova chave para uma nova análise."
          : "Full rejects root-level task, text_input, region and generation, even when empty. Put queries, regions and generation inside full_options. The same key, image, filename, options, location, tags and destination replay the same job. Changing the payload with that key returns 409; a deleted job returns 410. Use a new key for a new analysis."}
      </P>
      <Subheading>
        {pt
          ? "Envio automático por multipart"
          : "Automatic multipart submission"}
      </Subheading>
      {block(
        curl("/images/analyze/upload", [
          '  -H "Idempotency-Key: image-auto-001"',
          '  -F "file=@photo.jpg"',
          `  -F "project=${project}"`,
          "  --form-string 'mode=full'",
          "  --form-string 'wait=false'",
        ]),
      )}
      <Subheading>
        {pt ? "Consultas e regiões explícitas" : "Explicit queries and regions"}
      </Subheading>
      {block(
        curl("/images/analyze/upload", [
          '  -H "Idempotency-Key: image-advanced-001"',
          '  -F "file=@photo.jpg"',
          `  -F "project=${project}"`,
          "  --form-string 'mode=full'",
          `  --form-string 'full_options=${JSON.stringify(options)}'`,
        ]),
      )}
      <Subheading>
        {pt ? "Envio JSON / Python" : "JSON / Python submission"}
      </Subheading>
      {block(
        `import base64\nimport requests\n\nwith open("photo.jpg", "rb") as source:\n    image_base64 = base64.b64encode(source.read()).decode("ascii")\n\nresponse = requests.post(\n    "${API_URL}/images/analyze",\n    headers={"X-API-Key": "${key}", "Idempotency-Key": "image-json-001"},\n    json={"mode": "full", "image_base64": image_base64,\n          "filename": "photo.jpg", "project": "${project}", "wait": False,\n          "full_options": {"queries": ["a red car"],\n                           "regions": [[0, 0, 1, 1]],\n                           "deadline_seconds": 900}},\n    timeout=75,\n)\nresponse.raise_for_status()\nprint(response.json()["job_id"])`,
      )}
      <Subheading>
        {pt ? "Acompanhamento e resultados" : "Polling and results"}
      </Subheading>
      {block(
        JSON.stringify(
          {
            job_id: "example-image-job",
            status: "queued",
            created_at: "2026-10-06T00:00:00Z",
            message: "Full Analysis enfileirada",
            poll_url: "/jobs/example-image-job",
            result_url: "/jobs/example-image-job/result",
          },
          null,
          2,
        ),
      )}
      {block(curl("/jobs/example-image-job", [], "GET"))}
      <P>
        {pt
          ? "GET /jobs/{job_id} inclui image_analysis com status, steps_total, steps_completed, calls_started, cancel_requested e deadline_at. GET /jobs/{job_id}/result responde 202 enquanto a análise está em andamento. Ao terminar, a resposta padrão contém job_id, status e result={markdown,metadata,image}. Mesmo failed e cancelled podem fornecer um relatório diagnóstico."
          : "GET /jobs/{job_id} includes image_analysis with status, steps_total, steps_completed, calls_started, cancel_requested and deadline_at. GET /jobs/{job_id}/result returns 202 while analysis runs. The terminal default response contains job_id, status and result={markdown,metadata,image}. Even failed and cancelled runs can provide a diagnostic report."}
      </P>
      {block(curl("/jobs/example-image-job/result", [], "GET"))}
      <P small>
        {pt
          ? "image.operation=full_analysis identifica o relatório. coverage separa famílias e instâncias; uma família pode ter várias consultas/regiões. resolved_inputs registra entradas automáticas ou explícitas e candidatos omitidos. results[] contém step_id, task, input, status, reason_code, text, output nativo, regions, lines, attempts, duration_ms, truncated e generation_metadata. Limite: 31 chamadas iniciais e 32 incluindo recuperação."
          : "image.operation=full_analysis identifies the report. coverage separates families and instances; one family may have several query/region instances. resolved_inputs records automatic or explicit inputs and omitted candidates. results[] includes step_id, task, input, status, reason_code, text, native output, regions, lines, attempts, duration_ms, truncated and generation_metadata. Limit: 31 initial calls and 32 including recovery."}
      </P>
      <Table
        head={
          pt ? ["Estado final", "Significado"] : ["Final status", "Meaning"]
        }
        rows={[
          [
            "completed",
            pt
              ? "Cobertura integral, sem truncamento, com relatório persistido."
              : "Complete coverage without truncation and with a persisted report.",
          ],
          [
            "partial",
            pt
              ? "Há resultados disponíveis e pelo menos uma etapa incompleta, falha ou truncada."
              : "Results are available, with at least one incomplete, failed or truncated step.",
          ],
          [
            "failed",
            pt
              ? "Nenhuma etapa produziu resultado utilizável; consulte os motivos do relatório."
              : "No step produced a usable result; inspect report reasons.",
          ],
          [
            "cancelled",
            pt
              ? "Cancelamento solicitado; checkpoints já concluídos permanecem no relatório."
              : "Cancellation was requested; completed checkpoints remain in the report.",
          ],
        ]}
      />
      <P small>
        {pt
          ? "?format=json devolve o relatório bruto {markdown,metadata,image}, sem o envelope externo do job; ?format=markdown mantém o envelope padrão. Outros formatos retornam 422. As coordenadas de regions/lines são pixels do PNG canônico retornado, sem rotação EXIF posterior. GIF/TIFF usa o primeiro frame. O status SQL e o resultado privado no MinIO sobrevivem à expiração do cache Redis."
          : "?format=json returns the raw report {markdown,metadata,image}, without the outer job envelope; ?format=markdown keeps the default envelope. Other formats return 422. regions/lines coordinates are pixels of the returned canonical PNG, without later EXIF rotation. GIF/TIFF uses the first frame. SQL status and private MinIO results survive Redis cache expiry."}
      </P>
      <Subheading>
        {pt ? "Cancelamento e exclusão" : "Cancellation and deletion"}
      </Subheading>
      {block(curl("/images/example-image-job/cancel", []))}
      <P>
        {pt
          ? "POST /images/{job_id}/cancel é idempotente: responde 202 com cancel_requested=true durante a execução; 200 se já terminou. A resposta contém job_id, status e cancel_requested. Consulte o job até o estado terminal. Somente Full Analysis do dono pode ser cancelada; job de outra pessoa, inexistente ou single retorna 404. DELETE /jobs/{job_id} remove o job e seus objetos privados, inclusive se houver escrita tardia de um worker."
          : "POST /images/{job_id}/cancel is idempotent: 202 with cancel_requested=true while running; 200 when already terminal. It returns job_id, status and cancel_requested. Poll until terminal. Only the owner's Full Analysis can be cancelled; another user's, missing or single-mode job returns 404. DELETE /jobs/{job_id} removes the job and private objects, including late worker writes."}
      </P>
      <Subheading>
        {pt ? "Entrega ao datalake" : "Datalake delivery"}
      </Subheading>
      {block(
        JSON.stringify(
          {
            datalake: {
              connection_id: "YOUR_CONNECTION_ID",
              bucket: "image-reports",
              prefix: "analyses",
              partition_values: { customer_id: "customer-123" },
            },
          },
          null,
          2,
        ),
      )}
      <P small>
        {pt
          ? "Inclua datalake no corpo JSON ou como campo JSON no multipart; configure a estratégia de partitioning conforme o guia de datalakes. A configuração é congelada na criação. Resultados partial também podem ser entregues. O status da entrega é separado do processamento; acompanhe GET /jobs/{job_id}/datalake e repita somente a entrega quando necessário."
          : "Include datalake in the JSON body or as a JSON multipart field; configure partitioning following the datalake guide. Settings are frozen at creation. Partial results can also be delivered. Delivery has its own status; follow GET /jobs/{job_id}/datalake and retry only delivery when needed."}{" "}
        <A href={pt ? "/pt/docs/datalakes" : "/docs/datalakes"}>
          {pt
            ? "Guia de datalakes e particionamento"
            : "Datalake and partitioning guide"}
        </A>
        .
      </P>
      <P small>
        {pt
          ? "409/410 indicam conflito ou exclusão da chave idempotente; 422 indica opções/chave inválidas; 503 na consulta indica relatório temporariamente indisponível: consulte o mesmo job novamente. 504 VISION_TIMEOUT do envio com wait=true não cancela a análise. Veja também os erros comuns de imagens abaixo."
          : "409/410 indicate an idempotency conflict or deleted job; 422 indicates invalid options/key; 503 on result reads means the report is temporarily unavailable: retry the same job. A 504 VISION_TIMEOUT from wait=true submission does not cancel analysis. See common image errors below."}
      </P>
    </section>
  );
}
