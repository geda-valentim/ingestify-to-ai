"use client";

import { useState } from "react";
import { Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { downloadText } from "@/lib/utils";
import type { ImageJobResult, ImageFullAnalysisResult } from "@/types/api";
import { CopyButton, Panel } from "./result-primitives";
import { FullImageView } from "./image-analysis/full-image-view";
import { ImageCanvas } from "./image-analysis/image-canvas";
import type { FaceAnalysisResult, ImageFullV2Result } from "@/types/faces";
import { FaceView } from "./image-analysis/face-view";
import { FullV2View } from "./image-analysis/full-v2-view";

export function ImageView({
  image,
  fileName,
}: {
  image: ImageJobResult | ImageFullAnalysisResult | ImageFullV2Result | FaceAnalysisResult;
  fileName: string;
}) {
  if (image.operation === "face_analysis")
    return <FaceView analysis={image} imageBase64={image.image_base64} mime={image.image_mime_type} width={image.width} height={image.height} fileName={fileName} />;
  if (image.operation === "full_analysis" && "faces" in image)
    return <FullV2View image={image} fileName={fileName} />;
  if (image.operation === "full_analysis")
    return <FullImageView image={image} fileName={fileName} />;
  return <SingleImageView image={image} fileName={fileName} />;
}

function SingleImageView({
  image,
  fileName,
}: {
  image: ImageJobResult;
  fileName: string;
}) {
  const [regions, setRegions] = useState(true);
  const isOcr = image.operation === "ocr";
  const text =
    (image.operation === "describe" ? image.description : image.text) ?? "";
  const geometry = image.regions ?? [];
  const hasRegions = geometry.length > 0 || image.lines.length > 0;
  const descriptionLevel: Record<string, string> = {
    "<CAPTION>": "Breve",
    "<DETAILED_CAPTION>": "Detalhada",
    "<MORE_DETAILED_CAPTION>": "Muito detalhada",
  };
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        {image.task_label ||
          (isOcr
            ? "OCR com regiões"
            : `Descrição: ${descriptionLevel[image.task] || image.task}`)}{" "}
        · {image.width} × {image.height} px · {image.model.model_id}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <CopyButton text={text} label="Copiar texto" />
        <Button
          size="sm"
          onClick={() => downloadText(`${fileName}.txt`, text, "text/plain")}
        >
          <Download className="mr-2 h-4 w-4" />
          Baixar texto
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() =>
            downloadText(
              `${fileName}.json`,
              JSON.stringify(image, null, 2),
              "application/json",
            )
          }
        >
          Baixar JSON
        </Button>
        {hasRegions && (
          <Button
            size="sm"
            variant="outline"
            aria-pressed={regions}
            onClick={() => setRegions(!regions)}
          >
            {regions ? "Ocultar regiões" : "Mostrar regiões"}
          </Button>
        )}
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <ImageCanvas
          image={image}
          regions={geometry}
          lines={image.lines}
          visible={regions}
        />
        <Panel>
          <h3 className="mb-3 font-semibold">
            {image.operation === "analyze"
              ? image.task_label || "Resultado da análise"
              : isOcr
                ? "Texto extraído"
                : "Descrição da imagem"}
          </h3>
          <p className="whitespace-pre-wrap text-sm leading-relaxed">
            {text ||
              (hasRegions
                ? `${geometry.length || image.lines.length} regiões detectadas.`
                : "Nenhum resultado detectado.")}
          </p>
          {geometry.length > 0 && (
            <ol className="mt-4 space-y-2 border-t pt-4">
              {geometry.map((region, i) => (
                <li key={i} className="text-sm">
                  <span className="mr-2 text-muted-foreground">{i + 1}.</span>
                  {region.label || "Região"}
                  {region.bbox && (
                    <span className="ml-2 text-xs text-muted-foreground">
                      [{region.bbox.map((v) => Math.round(v)).join(", ")}]
                    </span>
                  )}
                </li>
              ))}
            </ol>
          )}
          {image.request?.text_input && (
            <p className="mt-4 text-xs text-muted-foreground">
              Texto solicitado: {image.request.text_input}
            </p>
          )}
          {isOcr && image.lines.length > 0 && (
            <ol className="mt-4 space-y-2 border-t pt-4">
              {image.lines.map((line, i) => (
                <li key={i} className="text-sm">
                  <span className="mr-2 text-muted-foreground">{i + 1}.</span>
                  {line.text}
                </li>
              ))}
            </ol>
          )}
        </Panel>
      </div>
    </div>
  );
}
