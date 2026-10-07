"use client";

import { useEffect, useRef, useState } from "react";

export function ImageRegionPicker({ file, region, onChange, disabled = false }: {
  file: File; region: number[] | null; onChange: (region: number[] | null) => void; disabled?: boolean;
}) {
  const [url, setUrl] = useState("");
  const start = useRef<number[] | null>(null);
  useEffect(() => {
    const next = URL.createObjectURL(file);
    setUrl(next);
    return () => URL.revokeObjectURL(next);
  }, [file]);
  const point = (event: React.PointerEvent<SVGSVGElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    return [Math.max(0, Math.min(1, (event.clientX - box.left) / box.width)),
            Math.max(0, Math.min(1, (event.clientY - box.top) / box.height))];
  };
  return <div className="space-y-2">
    <p className="text-sm">Arraste na imagem para selecionar a região.</p>
    <div className="relative max-w-lg overflow-hidden rounded border">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      {url && <img src={url} alt="Selecionar região da imagem" className="block h-auto w-full" />}
      <svg aria-label="Selecionar região" viewBox="0 0 1 1" preserveAspectRatio="none" className="absolute inset-0 h-full w-full touch-none"
        onPointerDown={(event) => { if (disabled) return; start.current = point(event); event.currentTarget.setPointerCapture(event.pointerId); onChange(null); }}
        onPointerMove={(event) => { if (!start.current) return; const end = point(event); onChange([Math.min(start.current[0], end[0]), Math.min(start.current[1], end[1]), Math.max(start.current[0], end[0]), Math.max(start.current[1], end[1])]); }}
        onPointerUp={(event) => { start.current = null; event.currentTarget.releasePointerCapture(event.pointerId); if (region && (region[0] === region[2] || region[1] === region[3])) onChange(null); }}
        onPointerCancel={() => { start.current = null; }}>
        {region && <rect x={region[0]} y={region[1]} width={region[2] - region[0]} height={region[3] - region[1]} fill="rgba(59,130,246,0.15)" stroke="#3b82f6" strokeWidth="2" vectorEffect="non-scaling-stroke" />}
      </svg>
    </div>
    {region && <p className="text-xs text-muted-foreground">Região selecionada: {region.map((coordinate) => `${Math.round(coordinate * 100)}%`).join(", ")}</p>}
  </div>;
}
