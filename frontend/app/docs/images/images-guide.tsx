import { DOCS_API_URL as API_URL } from "../config";
import { CodeBlock } from "../code-block";
import { P, Section, Subheading, Table } from "../docs-content-primitives";
import type { DocsLang } from "../topics";
import openapi from "@/docs/doc2md_openapi.json";
import { IMAGE_COPY } from "./images-copy";
import { GenerationGuide } from "./generation-guide";
import { FullAnalysisGuide } from "./full-analysis-guide";

export function ImagesGuide({ lang }: { lang: DocsLang }) {
  const pt = lang === "pt";
  const t = {
    ...IMAGE_COPY[lang],
    example: pt ? "Exemplos de descrição e OCR" : "Caption and OCR examples",
  };
  const key = pt ? "SUA_CHAVE" : "YOUR_KEY";
  const project = pt ? "Imagens" : "Images";
  const block = (code: string) => (
    <CodeBlock code={code} copyLabel={pt ? "Copiar código" : "Copy code"} />
  );
  const curl = (path: string, fields: string[], method = "POST") =>
    [
      `curl -X ${method} "${API_URL}${path}"`,
      `  -H "X-API-Key: ${key}"`,
      ...fields,
    ].join(" \\\n");
  return (
    <Section
      id="imagens"
      title={
        pt
          ? "Imagens: análise completa, descrição e OCR"
          : "Images: full analysis, captions and OCR"
      }
    >
      <P>{t.imagesIntro}</P>
      <Table head={t.imagesHead} rows={t.imagesRows} />
      <P small>{t.imageOptions}</P>
      <P small>{t.imageTasks}</P>
      <FullAnalysisGuide lang={lang} />
      <Subheading>
        {lang === "pt"
          ? "Catálogo completo de tarefas"
          : "Complete task catalog"}
      </Subheading>
      <Table
        head={
          lang === "pt"
            ? ["Tarefa", "Entrada adicional", "Saída"]
            : ["Task", "Additional input", "Output"]
        }
        rows={openapi.components.schemas.ImageAnalyzeOptions.properties.task[
          "x-task-catalog"
        ].map((item) => [
          item.task,
          item.input === "text"
            ? "text_input"
            : item.input === "region"
              ? "region"
              : "—",
          item.output,
        ])}
      />
      <P small>
        {lang === "pt"
          ? "region é um array normalizado [x_min,y_min,x_max,y_max] entre 0 e 1. Grounding, detecção por vocabulário e segmentação por expressão exigem text_input; tarefas REGION_TO_* exigem region. Entradas extras incompatíveis são rejeitadas. O resultado preserva output e normaliza regions[] em pixels da imagem original, com label, bbox, quad_box e polygons."
          : "region is a normalized [x_min,y_min,x_max,y_max] array from 0 to 1. Grounding, open-vocabulary detection and referring-expression segmentation require text_input; REGION_TO_* tasks require region. Incompatible inputs are rejected. Results preserve output and normalize regions[] in original image pixels, with label, bbox, quad_box and polygons."}
      </P>
      <GenerationGuide lang={lang} />
      {block(
        curl("/images/analyze/upload", [
          '  -F "file=@photo.jpg"',
          `  -F "project=${project}"`,
          '  --form-string "task=<OPEN_VOCABULARY_DETECTION>"',
          "  --form-string 'text_input=a red car'",
          '  --form-string \'generation={"max_new_tokens":512,"num_beams":1}\'',
        ]),
      )}
      <Subheading>{t.example}</Subheading>
      {block(
        curl("/images/describe/upload", [
          '  -F "file=@photo.jpg"',
          `  -F "project=${project}"`,
          '  --form-string "task=<CAPTION>"',
        ]),
      )}
      {block(
        curl("/images/ocr/upload", [
          '  -F "file=@receipt.png"',
          `  -F "project=${project}"`,
          '  -F "tags=ocr"',
        ]),
      )}
      {block(
        `import base64\nimport requests\n\nwith open("receipt.png", "rb") as f:\n    image = base64.b64encode(f.read()).decode("ascii")\n\nr = requests.post(\n    "${API_URL}/images/ocr",\n    headers={"X-API-Key": "${key}"},\n    json={"image_base64": image, "filename": "receipt.png",\n          "project": "${project}", "tags": ["ocr"]},\n    timeout=75,\n)\nr.raise_for_status()\nprint(r.json()["text"])`,
      )}
      <P>{t.imageResponse}</P>
      <P small>{t.ocrNote}</P>
      {block(
        JSON.stringify(
          {
            text: "TOTAL 42.00",
            lines: [
              {
                text: "TOTAL 42.00",
                quad_box: [12, 20, 180, 20, 180, 40, 12, 40],
                bbox: [12, 20, 180, 40],
              },
            ],
          },
          null,
          2,
        ),
      )}
      <Subheading>{t.timeoutTitle}</Subheading>
      <P>{t.timeout}</P>
      {block(
        JSON.stringify(
          {
            detail: {
              error_code: "VISION_TIMEOUT",
              message: "O job continua processando.",
              job_id: "example-image-job",
              poll_url: `/jobs/${"example-image-job"}`,
              result_url: `/jobs/${"example-image-job"}/result`,
            },
          },
          null,
          2,
        ),
      )}
      <P small>{t.retention}</P>
      <P small>{t.imageErrors}</P>
      {block(curl("/images/capabilities", [], "GET"))}
    </Section>
  );
}
