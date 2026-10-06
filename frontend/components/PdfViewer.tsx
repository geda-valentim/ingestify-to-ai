"use client";

import { Document, Page as PDFPage, pdfjs } from "react-pdf";
import { Loader2 } from "lucide-react";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

// Bundle the worker from the locked dependency; do not execute a CDN script.
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url,
).toString();

const PDF_OPTIONS = {
  wasmUrl: "/pdfjs/wasm/",
  cMapUrl: "/pdfjs/cmaps/",
  cMapPacked: true,
  standardFontDataUrl: "/pdfjs/standard_fonts/",
};

// A URL, or { url, httpHeaders } to send the Authorization header with the request
export type PdfSource = string | { url: string; httpHeaders?: Record<string, string> };

interface PdfViewerProps {
  file: PdfSource;
  onLoadSuccess?: ({ numPages }: { numPages: number }) => void;
  onLoadError?: (error: Error) => void;
  pageNumber?: number;
  width?: number;
  renderTextLayer?: boolean;
  renderAnnotationLayer?: boolean;
  className?: string;
}

export function PdfViewer({
  file,
  onLoadSuccess,
  onLoadError,
  pageNumber = 1,
  width,
  renderTextLayer = true,
  renderAnnotationLayer = true,
  className = "mx-auto"
}: PdfViewerProps) {
  return (
    <Document
      file={file}
      options={PDF_OPTIONS}
      onLoadSuccess={onLoadSuccess}
      onLoadError={onLoadError}
      loading={
        <div className="py-12 flex items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      }
    >
      <PDFPage
        pageNumber={pageNumber}
        renderTextLayer={renderTextLayer}
        renderAnnotationLayer={renderAnnotationLayer}
        className={className}
        width={width}
      />
    </Document>
  );
}
