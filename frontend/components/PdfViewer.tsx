"use client";

import { useEffect } from "react";
import { Document, Page as PDFPage, pdfjs } from "react-pdf";
import { Loader2 } from "lucide-react";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

// Configure PDF.js worker on client side only
if (typeof window !== 'undefined') {
  pdfjs.GlobalWorkerOptions.workerSrc = `//cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjs.version}/pdf.worker.min.js`;
}

interface PdfViewerProps {
  file: string;
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
