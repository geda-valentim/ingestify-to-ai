/**
 * Copy for the public feature pages. Every claim here is taken from the API
 * routes, worker code or docs/features/*.md; keep it in sync when they change.
 * Pure data (no React) so tests can load it without a bundler.
 */
export type IconName = "document" | "scan" | "audio" | "mic" | "video" | "image";

export type FeatureSection = {
  id: string;
  label: string;
  title: [string, string];
  intro?: string;
  tone?: "dark" | "soft";
  cards?: { label?: string; title: string; body: string; items?: string[] }[];
  table?: { caption: string; head: string[]; rows: string[][] };
};

export type Feature = {
  slug: "documents" | "audio-video" | "images";
  name: string;
  accent: string;
  metaTitle: string;
  metaDescription: string;
  title: [string, string];
  valueProp: string;
  heroNote: string;
  summary: string;
  highlights: string[];
  figure: {
    heading: string;
    inputs: { icon: IconName; label: string }[];
    engine: string;
    steps: string[];
    outputs: string[];
    caption: string;
  };
  sections: FeatureSection[];
  endpoints: { method: string; path: string; purpose: string }[];
  example: { title: string; headline: string; description: string; code: string };
  docs: { slug: string; note: string }[];
  availability: string;
};

const documents: Feature = {
  slug: "documents",
  name: "Documents",
  accent: "#677da9",
  metaTitle: "Document conversion to Markdown — Ingestify",
  metaDescription:
    "Convert PDF, DOCX, PPTX, XLSX and HTML to Markdown with Docling. Multi-page PDFs are split into page jobs processed in parallel, with per-page results, page retry, extracted images and page renders.",
  title: ["Documents in.", "Markdown out."],
  valueProp:
    "Convert PDFs and office documents into Markdown with Docling — page by page, with tables, optional OCR and the images inside.",
  heroNote:
    "Upload in the platform or through the API. Every job belongs to a project and returns a job ID you can track.",
  summary: "Docling conversion to Markdown, with per-page jobs for PDFs.",
  highlights: [
    "PDF, DOCX, PPTX, XLSX, HTML, ODT and Markdown",
    "fast, balanced and quality presets",
    "Parallel page jobs with page retry",
    "Extracted images and page renders as assets",
  ],
  figure: {
    heading: "One document job",
    inputs: [
      { icon: "document", label: "contract.pdf · 12 pages" },
      { icon: "scan", label: "scan.pdf · preset quality" },
    ],
    engine: "Docling",
    steps: ["Split the PDF into pages", "Convert pages in parallel", "Merge into one result"],
    outputs: ["markdown", "metadata", "assets[]", "page results"],
    caption: "Main job, page jobs and a merge job — each page can be read or retried on its own.",
  },
  sections: [
    {
      id: "formats",
      label: "What you can send",
      title: ["PDFs and office files.", "Converted by Docling."],
      intro:
        "Use POST /upload for files, or POST /convert with source_type=url to fetch a public URL. The default upload limit is 50 MB.",
      cards: [
        {
          label: "Formats",
          title: "Formats Docling reads",
          body: "Ingestify recognizes these extensions and hands them to Docling:",
          items: [".pdf", ".docx · .pptx · .xlsx", ".html · .htm · .odt · .md"],
        },
        {
          label: "Legacy files",
          title: "Older formats",
          body: "Legacy .doc, .ppt, .xls and .rtf files are passed to Docling too, but they often fail. Save them as the modern format when you can.",
        },
        {
          label: "URLs",
          title: "Convert from a link",
          body: "POST /convert with source_type=url downloads the file for you, with redirects limited and private network addresses blocked.",
        },
      ],
    },
    {
      id: "presets",
      label: "Docling presets",
      tone: "dark",
      title: ["Choose speed or depth.", "Per upload."],
      intro:
        "Set docling_preset on POST /upload. The presets control OCR, picture images and table structure for PDFs; quality is the slowest.",
      table: {
        caption: "Docling presets and what they enable",
        head: ["Preset", "OCR", "Picture images", "Table structure"],
        rows: [
          ["fast (default)", "Off", "Off", "On"],
          ["balanced", "Off", "On", "On"],
          ["quality", "On — for scanned pages", "On", "On"],
        ],
      },
    },
    {
      id: "pages",
      label: "Multi-page PDFs",
      title: ["Every page is a job.", "Recover only what failed."],
      intro:
        "A PDF with two or more pages is split. Each page is converted as its own job, in parallel, and a merge job joins them into the final Markdown.",
      cards: [
        {
          label: "Progress",
          title: "Track page by page",
          body: "GET /jobs/{job_id}/pages lists every page job with its status. If some pages fail, the document finishes as partial instead of failing entirely.",
        },
        {
          label: "Per page",
          title: "Read or download one page",
          body: "Fetch the Markdown of a single page, or a short-lived link to that page as its own PDF.",
        },
        {
          label: "Retry",
          title: "Retry a failed page",
          body: "POST /jobs/{job_id}/pages/{n}/retry requeues one failed page (up to 3 retries) without converting the rest again.",
        },
      ],
    },
    {
      id: "images",
      label: "Images in documents",
      tone: "soft",
      title: ["Keep the figures.", "Render the pages."],
      intro:
        "Both options are off by default, so the Markdown stays text-only unless you ask for images.",
      cards: [
        {
          label: "image_mode=referenced",
          title: "Extracted figures",
          body: "Each figure Docling finds is stored as a PNG and linked from the Markdown at /jobs/{job_id}/assets/{name}.",
        },
        {
          label: "page_images=true",
          title: "Page renders",
          body: "Each PDF page is also rendered as a PNG. Renders are listed as assets but not embedded in the Markdown.",
        },
        {
          label: "assets[]",
          title: "A manifest per job",
          body: "The result lists every asset with its kind, page, bounding box, SHA-256, size and URL, plus a count of anything skipped by the job limits.",
        },
      ],
    },
    {
      id: "operations",
      label: "Organize and retain",
      title: ["Projects, duplicates", "and source files."],
      cards: [
        {
          label: "Projects",
          title: "Projects, folders and tags",
          body: "Send project (or project_id), an optional folder and comma-separated tags. An API key can be bound to a project.",
        },
        {
          label: "Deduplication",
          title: "No double work",
          body: "Sending the same file with the same options to the same project returns the existing job with duplicate: true. Failed jobs are never reused.",
        },
        {
          label: "purge_source",
          title: "Delete the original",
          body: "Set purge_source=true to delete the uploaded file and per-page PDFs when the job is final. The Markdown is kept; extracted images expire after a retention period.",
        },
      ],
    },
  ],
  endpoints: [
    { method: "POST", path: "/upload", purpose: "Upload a document (preset, images, project)." },
    { method: "POST", path: "/convert", purpose: "Convert a file or a URL." },
    { method: "GET", path: "/jobs/{job_id}/pages", purpose: "List page jobs and their status." },
    { method: "GET", path: "/jobs/{job_id}/result", purpose: "Markdown, metadata and assets[]." },
    { method: "POST", path: "/jobs/{job_id}/pages/{n}/retry", purpose: "Retry one failed page." },
  ],
  example: {
    title: "Convert a PDF with images",
    headline: "Markdown back.",
    description:
      "The upload returns a job_id immediately. When the job is completed, the result holds the Markdown, metadata and the assets manifest.",
    code: `curl -X POST "$API/upload" \\
  -H "X-API-Key: $INGESTIFY_API_KEY" \\
  -F "file=@report.pdf" \\
  -F "project=Reports" \\
  -F "docling_preset=balanced" \\
  -F "image_mode=referenced" \\
  -F "page_images=true"

# Then, per page or for the whole document:
curl "$API/jobs/$JOB_ID/pages" -H "X-API-Key: $INGESTIFY_API_KEY"
curl "$API/jobs/$JOB_ID/result" -H "X-API-Key: $INGESTIFY_API_KEY"`,
  },
  docs: [
    { slug: "documents", note: "POST /upload and /convert fields, presets and images." },
    { slug: "pdf-pages", note: "Page jobs, page PDFs and page retry." },
    { slug: "results", note: "Result shape and assets." },
    { slug: "projects", note: "Projects, folders and tags." },
    { slug: "platform-documents", note: "Convert and review documents in the platform." },
    { slug: "authentication", note: "API keys and tokens." },
  ],
  availability:
    "Documents are delivered as Markdown with metadata through the platform and API. Automatic storage delivery is available for image analyses, not for document conversion.",
};

const images: Feature = {
  slug: "images",
  name: "Images",
  accent: "#789481",
  metaTitle: "Image captions, OCR and detection — Ingestify",
  metaDescription:
    "Describe images, extract text with regions, detect objects and segment regions with Florence-2. Run Full Analysis across every task, add optional face analysis and deliver results to S3, MinIO, GCS or Azure.",
  title: ["Images in.", "Text, boxes and regions out."],
  valueProp:
    "Describe an image, read its text and locate what is in it with Florence-2 — one task at a time or all of them with Full Analysis.",
  heroNote:
    "Use the platform or the API. Accepts PNG, JPEG, WEBP, BMP, GIF and TIFF up to 10 MB.",
  summary: "Florence-2 captions, OCR, detection and segmentation, plus Full Analysis.",
  highlights: [
    "15 Florence-2 tasks, listed by GET /images/capabilities",
    "OCR with regions, grounding and segmentation",
    "Full Analysis with per-step progress",
    "Optional face analysis and storage delivery",
  ],
  figure: {
    heading: "One image analysis",
    inputs: [
      { icon: "image", label: "receipt.png" },
      { icon: "scan", label: "task <OCR_WITH_REGION>" },
    ],
    engine: "Florence-2 base",
    steps: ["Validate the image", "Run the vision task", "Return text, boxes or polygons"],
    outputs: ["text", "boxes", "polygons", "markdown"],
    caption: "Each task returns its native output; Full Analysis runs the families together.",
  },
  sections: [
    {
      id: "tasks",
      label: "Florence-2 tasks",
      title: ["Fifteen tasks.", "One catalog."],
      intro:
        "GET /images/capabilities lists each task with its output and the input it needs. Some tasks need text or a region given as normalized [x_min, y_min, x_max, y_max].",
      table: {
        caption: "Florence-2 tasks exposed by GET /images/capabilities",
        head: ["Task", "What it does", "Output", "Input"],
        rows: [
          ["<CAPTION>", "Short description", "text", "—"],
          ["<DETAILED_CAPTION>", "Detailed description", "text", "—"],
          ["<MORE_DETAILED_CAPTION>", "Very detailed description", "text", "—"],
          ["<OCR>", "Extract text", "text", "—"],
          ["<OCR_WITH_REGION>", "Extract text with regions", "ocr", "—"],
          ["<OD>", "Detect objects", "boxes", "—"],
          ["<DENSE_REGION_CAPTION>", "Describe regions", "boxes", "—"],
          ["<REGION_PROPOSAL>", "Propose regions", "boxes", "—"],
          ["<CAPTION_TO_PHRASE_GROUNDING>", "Locate phrases in the image", "boxes", "text"],
          ["<REFERRING_EXPRESSION_SEGMENTATION>", "Segment by description", "polygons", "text"],
          ["<OPEN_VOCABULARY_DETECTION>", "Detect objects by text", "mixed", "text"],
          ["<REGION_TO_SEGMENTATION>", "Segment a region", "polygons", "region"],
          ["<REGION_TO_CATEGORY>", "Classify a region", "text", "region"],
          ["<REGION_TO_DESCRIPTION>", "Describe a region", "text", "region"],
          ["<REGION_TO_OCR>", "Extract text from a region", "text", "region"],
        ],
      },
    },
    {
      id: "modes",
      label: "Ways to run",
      tone: "dark",
      title: ["Quick answers.", "Or a tracked job."],
      cards: [
        {
          label: "Describe and OCR",
          title: "Synchronous shortcuts",
          body: "POST /images/describe returns a caption and POST /images/ocr returns text with regions in the same response.",
        },
        {
          label: "Analyze",
          title: "Any task, sync or async",
          body: "POST /images/analyze runs any task. By default it returns 202 with a job_id to poll; send wait=true to get the result in the response, with a timeout.",
        },
        {
          label: "Full Analysis",
          title: "Every family, one job",
          body: "mode=full runs the task families together, derives queries and regions or takes yours, and reports progress per step. Results can be completed, partial, failed or cancelled.",
        },
      ],
    },
    {
      id: "faces",
      label: "Face analysis",
      tone: "soft",
      title: ["Faces, landmarks", "and expressions."],
      intro:
        "Optional and disabled by default; an administrator enables it and downloads the models.",
      cards: [
        {
          label: "Detection",
          title: "Faces and landmarks",
          body: "MediaPipe detects faces with boxes, confidence and keypoints, plus landmarks and blendshapes.",
        },
        {
          label: "Expressions",
          title: "Eight expression classes",
          body: "EmotiEffLib scores anger, contempt, disgust, fear, happiness, neutral, sadness and surprise. Scores are not calibrated and do not determine a person’s emotional state.",
        },
        {
          label: "No identification",
          title: "No identity recognition",
          body: "Face IDs are local to the job. Ingestify does not recognize or match identities, and stores coordinates and labels, not face crops.",
        },
      ],
    },
    {
      id: "delivery",
      label: "Results and storage",
      title: ["Your bucket.", "Your retention rules."],
      cards: [
        {
          label: "Storage delivery",
          title: "S3, MinIO, GCS and Azure",
          body: "Full Analysis and face results can be delivered to Amazon S3, MinIO, Google Cloud Storage or Azure Blob Storage, with date, project or custom partitioning and optional JSONL rows.",
        },
        {
          label: "purge_source",
          title: "Keep only the results",
          body: "Set purge_source=true to delete the image and its previews when the job finishes. Storage deliveries never receive the image.",
        },
        {
          label: "Projects",
          title: "Organized like every job",
          body: "Send a project (or use an API key bound to one), an optional folder and tags.",
        },
      ],
    },
  ],
  endpoints: [
    { method: "GET", path: "/images/capabilities", purpose: "Tasks, limits and model status." },
    { method: "POST", path: "/images/describe/upload", purpose: "Caption an image." },
    { method: "POST", path: "/images/ocr/upload", purpose: "Text with regions." },
    { method: "POST", path: "/images/analyze/upload", purpose: "Any task, or mode=full." },
    { method: "POST", path: "/images/faces/upload", purpose: "Face analysis, when enabled." },
  ],
  example: {
    title: "Ground a phrase in an image",
    headline: "Boxes back.",
    description:
      "Use --form-string for task tokens such as <OD>. With wait=true the response carries the result; without it you get a job_id to poll.",
    code: `curl -X POST "$API/images/analyze/upload" \\
  -H "X-API-Key: $INGESTIFY_API_KEY" \\
  -F "file=@shelf.jpg" \\
  -F "project=Catalog" \\
  --form-string "task=<CAPTION_TO_PHRASE_GROUNDING>" \\
  -F "text_input=red bottle" \\
  -F "wait=true"

# Text with regions, returned synchronously:
curl -X POST "$API/images/ocr/upload" \\
  -H "X-API-Key: $INGESTIFY_API_KEY" \\
  -F "file=@receipt.png" -F "project=Catalog"`,
  },
  docs: [
    { slug: "images", note: "Describe, OCR, analyze and capabilities." },
    { slug: "platform-images", note: "Full Analysis in the platform." },
    { slug: "datalakes", note: "Storage connections for image results." },
    { slug: "platform-partitioning", note: "Partition results by customer." },
    { slug: "job-status", note: "Poll asynchronous jobs." },
  ],
  availability:
    "Image analysis and face analysis are enabled per installation. The default model is Florence-2 base; tasks are fixed, not free-form prompts.",
};

const audioVideo: Feature = {
  slug: "audio-video",
  name: "Audio & Video",
  accent: "#8b6d97",
  metaTitle: "Audio & Video transcription — Ingestify",
  metaDescription:
    "Transcribe audio and video files with Whisper (faster-whisper) and get Markdown, SRT, VTT, plain text or JSON with segment and optional word timestamps. Optional live capture and speaker labels.",
  title: ["Recordings in.", "Timestamped text out."],
  valueProp:
    "Send an audio or video file and get a transcript with timestamps — as Markdown, SRT or VTT captions, plain text or JSON.",
  heroNote:
    "File transcription runs through the API. Live microphone capture and speaker labels are optional features that an administrator enables.",
  summary:
    "Whisper transcription for audio and video files, with captions and timestamps.",
  highlights: [
    "faster-whisper with the turbo model by default",
    "Markdown, SRT, VTT, TXT and JSON from one job",
    "Language auto-detection and optional word timestamps",
    "Optional live capture on the Live screen",
  ],
  figure: {
    heading: "One transcription job",
    inputs: [
      { icon: "audio", label: "meeting.mp3" },
      { icon: "video", label: "webinar.mp4 · audio track" },
    ],
    engine: "faster-whisper · turbo",
    steps: ["Detect or use the language", "Transcribe with timestamps", "Write every format"],
    outputs: ["markdown", "srt", "vtt", "txt", "json"],
    caption: "Each job keeps all five formats; pick one with ?format= when you fetch the result.",
  },
  sections: [
    {
      id: "inputs",
      label: "What you can send",
      title: ["Audio and video.", "One endpoint."],
      intro:
        "Upload the file to POST /transcribe. For video, Ingestify transcribes the audio track. Media sent to /upload or /convert is routed to transcription too.",
      cards: [
        {
          label: "Audio",
          title: "Common audio formats",
          body: "Accepted extensions:",
          items: [".mp3 .wav .m4a .flac", ".ogg .oga .opus .spx", ".webm .wma .aac"],
        },
        {
          label: "Video",
          title: "Video, transcribed by its audio",
          body: "Accepted extensions:",
          items: [".mp4 .m4v .mkv .mov", ".avi .webm .wmv .flv", ".mpeg .mpg .ts .3gp"],
        },
        {
          label: "Limits",
          title: "Sizes the operator controls",
          body: "Default upload limits are 50 MB for audio and 500 MB for video. Each job belongs to a project, and re-sending an identical file to the same project returns the existing job.",
        },
      ],
    },
    {
      id: "transcription",
      label: "How it transcribes",
      tone: "dark",
      title: ["Whisper on your workers.", "Options per request."],
      intro:
        "The engine and model are chosen by the installation, not per request. Each request chooses the language, timestamps and default output.",
      cards: [
        {
          label: "Engine",
          title: "faster-whisper by default",
          body: "The default provider is faster-whisper with the turbo model (large-v3-turbo weights). Operators can switch to openai-whisper or to the OpenAI API — the latter sends audio to OpenAI.",
        },
        {
          label: "Language",
          title: "Auto-detect or choose",
          body: "Leave language empty to detect it, or pass an ISO 639-1 code such as en or pt.",
        },
        {
          label: "Timestamps",
          title: "Segments and words",
          body: "Segment timestamps are on by default. Set include_word_timestamps=true to add a words list with start and end times to each segment.",
        },
        {
          label: "Speakers",
          title: "Speaker labels, when enabled",
          body: "With the WhisperX provider and diarization enabled by an administrator, set diarize=true (optionally min_speakers / max_speakers, up to 20). It is off by default.",
        },
        {
          label: "Source files",
          title: "Keep or delete the media",
          body: "Send purge_source=true to delete the uploaded audio or video when the job finishes. Only the transcripts are kept.",
        },
        {
          label: "Organization",
          title: "Projects, folders and tags",
          body: "Name a project (and optionally a folder) on the request, or use an API key bound to a project. Add tags to find jobs later.",
        },
      ],
    },
    {
      id: "outputs",
      label: "Output formats",
      title: ["Every format.", "From the same job."],
      intro:
        "output_format sets the default returned by /jobs/{job_id}/result; ?format= picks any of the others.",
      table: {
        caption: "Transcript output formats",
        head: ["Format", "What you get"],
        rows: [
          ["markdown", "Readable transcript with time markers (the default)."],
          ["srt", "SubRip captions for video players and editors."],
          ["vtt", "WebVTT captions for the web."],
          ["txt", "Plain text."],
          ["json", "Segments with start and end times, plus words when requested."],
        ],
      },
    },
    {
      id: "live",
      label: "While it runs",
      tone: "soft",
      title: ["Text as it arrives.", "Files and microphone."],
      cards: [
        {
          label: "File captions",
          title: "Partial transcript of a running job",
          body: "GET /jobs/{job_id}/transcript/partial?since=N returns the segments transcribed so far while an uploaded file is still processing (with faster-whisper).",
        },
        {
          label: "Live capture",
          title: "Streaming captions from a microphone",
          body: "On the Live screen, audio streams over a WebSocket and comes back as revisable partial and confirmed final captions, saved as TXT, JSON, VTT or SRT. The original audio is not stored.",
        },
        {
          label: "Availability",
          title: "Live is opt-in",
          body: "Live capture is disabled by default, needs a GPU on the server and currently transcribes Portuguese. Browsers require HTTPS or localhost for the microphone.",
        },
      ],
    },
    {
      id: "compute",
      label: "Where it runs",
      title: ["Local workers first.", "Remote GPU if you route it."],
      intro:
        "Transcription runs on your own workers. Administrators can add a Modal GPU engine and route jobs to it.",
      cards: [
        {
          label: "Routing",
          title: "Remote steps by route",
          body: "Nothing goes remote unless a route includes a remote step — for example, wait for a local worker first and fall back to Modal.",
        },
        {
          label: "Budget",
          title: "Spending limits",
          body: "A Modal engine is activated only with a passing test and a USD limit. The engine is marked exhausted when the budget runs out.",
        },
        {
          label: "Size",
          title: "Large media stays local",
          body: "Media over 512 MB or 4 hours is not sent to Modal. Partial transcripts stream from remote jobs too.",
        },
      ],
    },
  ],
  endpoints: [
    { method: "POST", path: "/transcribe", purpose: "Submit an audio or video file." },
    { method: "GET", path: "/jobs/{job_id}", purpose: "Track status and progress." },
    { method: "GET", path: "/jobs/{job_id}/transcript/partial", purpose: "Read segments while it runs." },
    { method: "GET", path: "/jobs/{job_id}/result?format=srt", purpose: "Download the transcript." },
  ],
  example: {
    title: "Transcribe a recording",
    headline: "Captions back.",
    description:
      "The request returns a job_id right away. Poll the job until it is completed, then download the result in the format you need.",
    code: `curl -X POST "$API/transcribe" \\
  -H "X-API-Key: $INGESTIFY_API_KEY" \\
  -F "file=@meeting.mp3" \\
  -F "project=Meetings" \\
  -F "language=en" \\
  -F "include_word_timestamps=true" \\
  -F "output_format=srt"

# When GET /jobs/$JOB_ID reports completed:
curl "$API/jobs/$JOB_ID/result?format=vtt" \\
  -H "X-API-Key: $INGESTIFY_API_KEY"`,
  },
  docs: [
    { slug: "transcription", note: "POST /transcribe fields, formats and limits." },
    { slug: "file-captions", note: "Partial transcript while a file is processed." },
    { slug: "live", note: "Live sessions, WebSocket stream and events." },
    { slug: "results", note: "Download the result in each format." },
    { slug: "platform-transcription", note: "Use transcripts and the Live screen." },
    { slug: "compute", note: "Engines, Modal routing and budgets." },
  ],
  availability:
    "Engines, live capture, speaker labels and remote GPUs depend on how your installation is configured and on your account permissions.",
};

export const FEATURES: Feature[] = [documents, audioVideo, images];

export function featureBySlug(slug: Feature["slug"]) {
  const feature = FEATURES.find((item) => item.slug === slug);
  if (!feature) throw new Error(`Unknown feature: ${slug}`);
  return feature;
}
