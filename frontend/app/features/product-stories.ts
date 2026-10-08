import type { Feature } from "./content";

export const PRODUCT_STORIES = {
  documents: {
    eyebrow: "DOCUMENT INTELLIGENCE",
    promise: "Your documents. Ready for what’s next.",
    intro:
      "Give your AI workflows readable, structured content. Turn the files your team already has into Markdown you can search, review and build with.",
    stats: [
      ["7+", "document formats"],
      ["3", "conversion presets"],
      ["1", "job for every PDF page"],
    ],
    formats: ["PDF", "DOCX", "PPTX", "XLSX", "HTML", "ODT", "MD"],
    benefits: [
      {
        title: "Give your knowledge a new life.",
        body: "Turn reports, manuals and contracts into Markdown for knowledge bases and AI retrieval workflows.",
        icon: "knowledge",
      },
      {
        title: "Keep the context that matters.",
        body: "Preserve table structure. Add extracted figures and page renders when your workflow needs more than text.",
        icon: "structure",
      },
      {
        title: "Keep your pipeline moving.",
        body: "Track PDF pages independently and retry a failed page without reprocessing the entire document.",
        icon: "workflow",
      },
    ],
    cta: "Make your documents work harder.",
    ctaBody:
      "Start with a PDF. Get Markdown, metadata and a foundation for your next workflow.",
  },
  "audio-video": {
    eyebrow: "AUDIO & VIDEO INTELLIGENCE",
    promise: "Every conversation has more to give.",
    intro:
      "Make recordings useful beyond the play button. Turn spoken knowledge into searchable transcripts, reusable text and captions for your content.",
    stats: [
      ["5", "transcript formats"],
      ["Word-level", "optional timestamps"],
      ["Audio + video", "one workflow"],
    ],
    formats: ["MP3", "WAV", "M4A", "FLAC", "MP4", "MOV", "WEBM"],
    benefits: [
      {
        title: "Find the moment that matters.",
        body: "Use timestamped transcripts to navigate interviews, meetings and training recordings without replaying everything.",
        icon: "knowledge",
      },
      {
        title: "Give your content a wider reach.",
        body: "Create SRT and VTT captions from the same transcription job for video editors and web players.",
        icon: "structure",
      },
      {
        title: "Build on spoken knowledge.",
        body: "Bring plain text, Markdown or structured JSON into your own search, content and AI workflows.",
        icon: "workflow",
      },
    ],
    cta: "Let your recordings do more.",
    ctaBody:
      "Start with a recording. Get text you can find, captions you can publish and data you can build on.",
  },
  images: {
    eyebrow: "VISUAL INTELLIGENCE",
    promise: "See the image. Use the information.",
    intro:
      "Bring visual content into your data workflows. Extract readable text, describe what’s there and locate objects and regions with a dedicated vision task.",
    stats: [
      ["15", "vision tasks"],
      ["Text + regions", "OCR output"],
      ["4", "storage providers"],
    ],
    formats: ["PNG", "JPEG", "WEBP", "BMP", "GIF", "TIFF"],
    benefits: [
      {
        title: "Make visual content searchable.",
        body: "Generate captions for product imagery and other visual assets so your workflows can work with descriptions.",
        icon: "knowledge",
      },
      {
        title: "Turn pixels into useful text.",
        body: "Extract text from receipts, labels and screenshots, with regions that connect each result to the source image.",
        icon: "structure",
      },
      {
        title: "Move from seeing to processing.",
        body: "Run a focused task or Full Analysis. Deliver supported results to S3, MinIO, Google Cloud Storage or Azure.",
        icon: "workflow",
      },
    ],
    cta: "Put your images to work.",
    ctaBody:
      "Start with an image. Discover the text, descriptions and regions waiting inside.",
  },
} satisfies Record<
  Feature["slug"],
  {
    eyebrow: string;
    promise: string;
    intro: string;
    stats: string[][];
    formats: string[];
    benefits: {
      title: string;
      body: string;
      icon: "knowledge" | "structure" | "workflow";
    }[];
    cta: string;
    ctaBody: string;
  }
>;
