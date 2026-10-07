"use client";

import { useState } from "react";
import { Eye, EyeOff, ImageOff, Maximize2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { ImageJobResult, ImageRegion } from "@/types/api";
import { cn } from "@/lib/utils";

export const regionColor = (index: number) =>
  `hsl(${210 + index * 57}, 75%, 50%)`;
const points = (values: number[]) =>
  values
    .reduce<
      string[]
    >((pairs, value, i) => (i % 2 === 0 ? [...pairs, `${value},${values[i + 1]}`] : pairs), [])
    .join(" ");

type CanvasImage = Pick<
  ImageJobResult,
  "image_base64" | "image_mime_type" | "width" | "height"
>;
type Props = {
  image: CanvasImage;
  regions?: ImageRegion[];
  lines?: ImageJobResult["lines"];
  activeRegion?: number | null;
  onSelectRegion?: (index: number) => void;
  controls?: boolean;
  visible?: boolean;
};

function ImageSurface({
  image,
  regions = [],
  lines = [],
  activeRegion,
  onSelectRegion,
  visible,
  bounded = false,
}: Props & { bounded?: boolean }) {
  const [failed, setFailed] = useState(false);
  if (!image.image_base64 || !image.image_mime_type || failed)
    return (
      <div className="flex min-h-48 flex-col items-center justify-center gap-2 text-muted-foreground">
        <ImageOff className="h-8 w-8" />
        <p className="text-sm">A imagem de referência está indisponível.</p>
      </div>
    );
  return (
    <div className="relative mx-auto w-fit max-w-full">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={`data:${image.image_mime_type};base64,${image.image_base64}`}
        alt="Imagem enviada"
        onError={() => setFailed(true)}
        className={cn(
          "block h-auto max-w-full",
          bounded && "max-h-[420px] w-auto",
        )}
      />
      {visible &&
        (regions.length > 0 || lines.length > 0) &&
        image.width > 0 &&
        image.height > 0 && (
          <svg
            className="absolute inset-0 h-full w-full"
            viewBox={`0 0 ${image.width} ${image.height}`}
            aria-label="Regiões detectadas"
          >
            {regions.length
              ? regions.map((region, index) => (
                  <g
                    key={index}
                    fill={regionColor(index)}
                    fillOpacity={
                      activeRegion == null || activeRegion === index
                        ? 0.15
                        : 0.03
                    }
                    stroke={regionColor(index)}
                    strokeWidth={activeRegion === index ? 3 : 1.5}
                    opacity={
                      activeRegion == null || activeRegion === index ? 1 : 0.4
                    }
                    onClick={() => onSelectRegion?.(index)}
                    className={onSelectRegion ? "cursor-pointer" : undefined}
                  >
                    <title>
                      {region.label || `Região ${index + 1}`}
                      {region.score != null
                        ? ` · ${(region.score * 100).toFixed(1)}%`
                        : ""}
                    </title>
                    {region.quad_box?.length === 8 ? (
                      <polygon
                        vectorEffect="non-scaling-stroke"
                        points={points(region.quad_box)}
                      />
                    ) : (
                      region.bbox?.length === 4 && (
                        <rect
                          x={region.bbox[0]}
                          y={region.bbox[1]}
                          width={Math.max(0, region.bbox[2] - region.bbox[0])}
                          height={Math.max(0, region.bbox[3] - region.bbox[1])}
                          vectorEffect="non-scaling-stroke"
                        />
                      )
                    )}
                    {(region.polygons ?? []).map((polygon, i) => (
                      <polygon
                        key={i}
                        vectorEffect="non-scaling-stroke"
                        points={points(polygon)}
                      />
                    ))}
                  </g>
                ))
              : lines.map((line, index) => (
                  <polygon
                    key={index}
                    points={points(line.quad_box)}
                    fill="rgba(59,130,246,0.15)"
                    stroke="rgb(59,130,246)"
                    strokeWidth="1.5"
                    vectorEffect="non-scaling-stroke"
                  >
                    <title>{line.text}</title>
                  </polygon>
                ))}
          </svg>
        )}
    </div>
  );
}

export function ImageCanvas({
  controls = false,
  visible = true,
  ...props
}: Props) {
  const [show, setShow] = useState(true);
  const [expanded, setExpanded] = useState(false);
  const [zoom, setZoom] = useState(1);
  const hasRegions =
    (props.regions?.length ?? 0) + (props.lines?.length ?? 0) > 0;
  const surface = { ...props, visible: controls ? show : visible };
  return (
    <div className="overflow-hidden rounded-xl border bg-muted/20">
      {controls && (
        <div className="flex flex-wrap items-center justify-between gap-2 border-b bg-background px-3 py-2">
          <span className="text-xs text-muted-foreground">
            Imagem de referência
            {hasRegions &&
              ` · ${props.regions?.length || props.lines?.length} regiões`}
          </span>
          <div className="flex items-center gap-1">
            {hasRegions && (
              <Button
                size="sm"
                variant="ghost"
                className="h-8 text-xs"
                aria-pressed={show}
                onClick={() => setShow(!show)}
              >
                {show ? (
                  <EyeOff className="mr-1.5 h-3.5 w-3.5" />
                ) : (
                  <Eye className="mr-1.5 h-3.5 w-3.5" />
                )}
                {show ? "Ocultar regiões" : "Mostrar regiões"}
              </Button>
            )}
            <Button
              size="sm"
              variant="ghost"
              className="h-8 px-2"
              aria-label="Ampliar imagem"
              disabled={!props.image.image_base64}
              onClick={() => {
                setZoom(1);
                setExpanded(true);
              }}
            >
              <Maximize2 className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
      <div
        className={cn(
          controls && "flex min-h-48 items-center justify-center p-3",
        )}
      >
        <ImageSurface {...surface} bounded={controls} />
      </div>
      <Dialog open={expanded} onOpenChange={setExpanded}>
        <DialogContent className="w-[95vw] max-w-5xl">
          <DialogHeader>
            <DialogTitle>Imagem de referência</DialogTitle>
          </DialogHeader>
          <label className="flex items-center gap-3 text-sm">
            Zoom{" "}
            <input
              aria-label="Zoom da imagem"
              type="range"
              min="1"
              max="3"
              step="0.25"
              value={zoom}
              onChange={(event) => setZoom(Number(event.target.value))}
              className="min-w-0 flex-1 accent-primary"
            />
            <span className="w-12 tabular-nums">{zoom * 100}%</span>
          </label>
          <div className="max-h-[70vh] overflow-auto rounded-lg bg-muted/30">
            <div style={{ width: `${zoom * 100}%` }}>
              <ImageSurface {...surface} />
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
