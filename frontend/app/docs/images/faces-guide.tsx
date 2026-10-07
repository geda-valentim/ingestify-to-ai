import { DOCS_API_URL } from "../config";
import { CodeBlock } from "../code-block";
import { P, Subheading, Table } from "../docs-content-primitives";
import type { DocsLang } from "../topics";

export function FacesGuide({ lang }: { lang: DocsLang }) {
  const pt = lang === "pt";
  return <div className="space-y-5">
    <Subheading>{pt ? "Rostos e expressões · operação específica e Full v2" : "Faces and expressions · dedicated operation and Full v2"}</Subheading>
    <P>{pt ? "Envie uma imagem para detectar rostos, obter landmarks e movimentos faciais ou estimar classes de expressão. MediaPipe e o checkpoint ONNX EmotiEffLib executam no worker, sem API externa. São estimativas de expressão visível; não determinam o estado emocional. Scores não são probabilidades calibradas." : "Upload an image to detect faces, obtain landmarks and facial movements, or estimate expression classes. MediaPipe and the EmotiEffLib ONNX checkpoint run in the worker without an external inference API. These are estimates of visible expression, not internal emotional state. Scores are not calibrated probabilities."}</P>
    <Table headers={[pt ? "Rota" : "Route", pt ? "Entrega" : "Output"]} rows={[
      ["GET /images/faces/capabilities", pt ? "Prontidão por etapa, modelos, schemas e limites" : "Readiness per stage, models, schemas and limits"],
      ["POST /images/faces", pt ? "JSON: image_base64, projeto e face_options" : "JSON: image_base64, project and face_options"],
      ["POST /images/faces/upload", pt ? "Multipart: file e face_options como JSON" : "Multipart: file and JSON face_options"],
      ["POST /images/analyze(/upload)", 'mode=full; full_options.profile=image-full-v2'],
      ["GET /jobs/{id}/result", pt ? "Resultado durável, inclusive partial; format=json exporta o envelope" : "Durable result, including partial; format=json exports the envelope"],
    ]} />
    <CodeBlock code={`curl "${DOCS_API_URL}/images/faces/upload" \\\n  -H "X-API-Key: ${pt ? "SUA_CHAVE" : "YOUR_KEY"}" \\\n  -H "Idempotency-Key: face-request-001" \\\n  -F "file=@photo.jpg" -F "project=Images" \\\n  -F 'face_options={"mode":"expressions","max_faces":5,"min_expression_score":0.5}'`} copyLabel={pt ? "Copiar código" : "Copy code"} />
    <CodeBlock code={`curl "${DOCS_API_URL}/images/analyze/upload" \\\n  -H "X-API-Key: ${pt ? "SUA_CHAVE" : "YOUR_KEY"}" \\\n  -H "Idempotency-Key: full-v2-request-001" \\\n  -F "file=@photo.jpg" -F "project=Images" -F "mode=full" \\\n  -F 'full_options={"profile":"image-full-v2","faces":{"max_faces":5}}'`} copyLabel={pt ? "Copiar código" : "Copy code"} />
    <P>{pt ? "A operação específica aceita até dez rostos e prazo total de até 300s. mode=detection executa somente o detector; parâmetros exclusivos de expressão são recusados nesse modo. Full v2 reúne 18 famílias, até cinco rostos e até 54 invocações incluindo recuperação, com prazo único de até 900s. Omissão do perfil mantém Full v1, com 15 famílias e limite 32. Não envie deadline_seconds dentro de faces no Full." : "The dedicated operation accepts up to ten faces and a total deadline of 300s. mode=detection runs only the detector and rejects expression-only parameters. Full v2 covers 18 families, up to five faces and up to 54 invocations including recovery within a single deadline of up to 900s. Omitting the profile retains Full v1 with 15 families and a limit of 32. Do not send deadline_seconds inside faces in Full."}</P>
    <P>{pt ? "Os POST exigem Idempotency-Key: repetir a mesma chave e payload retorna o mesmo job; divergência retorna 409. Um 504 de wait=true mantém o job em execução. Ausência de rostos é válida; falhas são registradas por etapa. O limite de rostos e as omissões aparecem no resultado. IDs de rostos valem somente dentro do job." : "POST requests require Idempotency-Key: replaying the same key and payload returns the same job; mismatches return 409. A wait=true HTTP 504 keeps the job running. No faces is a valid result; failures are recorded per stage. Face limits and omissions are visible. Face IDs are scoped to a job."}</P>
    <P>{pt ? "A disponibilidade depende do worker e dos artefatos fixados por checksum. Consulte capabilities antes do envio; não há troca automática de v2 para v1. /convert oferece a operação específica e a escolha do perfil Full. A página do job conserva parâmetros, modelos, camadas, scores e resultados parciais após recarregar." : "Availability depends on the worker and checksum-pinned artifacts. Check capabilities before submission; v2 never silently falls back to v1. /convert offers the dedicated operation and Full profile selection. Job pages retain parameters, models, layers, scores and partial results after reload."}</P>
  </div>;
}
