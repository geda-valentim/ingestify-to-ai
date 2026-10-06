export const GITHUB = "https://github.com/geda-valentim/ingestify-to-ai";
export const chapters = [
  {
    name: "Files",
    eyebrow: "DATA ENGINEERING + AI-READY CONVERSION",
    title: "Your files.\nAI-ready data.",
    body: "Self-hosted conversion into Markdown, text and transcripts for AI. Use a single operation or build it into your Data Engineering pipelines.",
    action: "Explore conversions",
    href: "#operacoes",
    note: "",
  },
  {
    name: "Documents",
    eyebrow: "01 / EXTRACT THE STRUCTURE",
    title: "Documents in.\nMarkdown out.",
    body: "Extract text and tables. Track each PDF page and retrieve the result for your downstream processing.",
    action: "Explore documents",
    href: "/docs?lang=en#documentos",
    note: "",
  },
  {
    name: "Audio",
    eyebrow: "02 / TURN SPEECH INTO DATA",
    title: "Recordings in.\nTranscripts out.",
    body: "Convert speech into text, timestamps and JSON segments. Transcribe audio files or the audio track of a video.",
    action: "Explore transcription",
    href: "/docs?lang=en#transcribe",
    note: "",
  },
  {
    name: "Images",
    eyebrow: "03 / EXTRACT TEXT FROM PIXELS",
    title: "Images in.\nText out.",
    body: "Extract text and image regions with OCR, or request image descriptions through the API.",
    action: "Explore image operations",
    href: "/docs?lang=en#imagens",
    note: "",
  },
  {
    name: "Compute",
    eyebrow: "04 / RUN ON YOUR INFRASTRUCTURE",
    title: "Your compute.\nYour workflow.",
    body: "Run conversion workers locally. Add optional Modal transcription and configure execution around capacity and budget.",
    action: "Explore compute",
    href: "/docs?lang=en#compute",
    note: "",
  },
  {
    name: "Connect",
    eyebrow: "05 / CONNECT THE DATA FLOW",
    title: "One API.\nYour workflow.",
    body: "Group inputs by project, folder and tags. Use conversion results in an AI application or retrieve them from your data pipeline.",
    action: "See the API in action",
    href: "#api",
    note: "",
  },
  {
    name: "Next",
    eyebrow: "PLANNED / DATA LAKE DELIVERY",
    title: "Next stop.\nYour data lake.",
    body: "The next step: deliver converted data directly to your data lake, connecting file ingestion to the rest of your data platform.",
    action: "Explore the roadmap",
    href: "#data-lake",
    note: "",
  },
  {
    name: "Build",
    eyebrow: "ONE CONVERSION. OR A WHOLE PIPELINE.",
    title: "Your data.\nYour next step.",
    body: "Convert a file into usable AI input, or connect the same operations to your Data Engineering workflow. Explore the code and API.",
    action: "Read the documentation",
    href: "/docs?lang=en",
    note: "",
  },
];
export const example = [
  'curl -X POST "https://dev.ingestify.ai/api/upload" \\',
  '  -H "X-API-Key: YOUR_API_KEY" \\',
  '  -F "file=@report.pdf" \\',
  '  -F "project=Research" \\',
  '  -F "tags=reports,source-pdf"',
].join("\n");
/** Example values using the current document-result response contract. */
export const resultExample = JSON.stringify(
  {
    job_id: "3e2c5325-a0f6-4d11-b851-c84f9ec03a21",
    type: "main",
    status: "completed",
    result: {
      markdown: "# Report\n\nTotal: 42.00",
      metadata: { pages: 1, words: 4, format: "pdf", size_bytes: 2048 },
    },
    completed_at: "2026-10-06T12:00:00Z",
  },
  null,
  2,
);
export const faq = [
  [
    "Do I need a data pipeline to use Ingestify?",
    "No. Convert individual files in the workspace or through the API, then use the Markdown, text or transcripts in your AI workflow. The same operations can also become steps in a Data Engineering pipeline.",
  ],
  [
    "What can I transform?",
    "Documents such as PDF, DOCX, HTML, PPTX and XLSX into Markdown; recordings into transcripts and captions; images into OCR text or descriptions. The operation selector lists common formats and default size limits. See the docs for engine compatibility and deployment settings.",
  ],
  [
    "Why use Ingestify around a conversion engine?",
    "Ingestify adds an operational layer: API access, asynchronous jobs, projects and folders, document deduplication within a project, PDF page tracking and retries. Conversion results become inputs your own data workflows can retrieve and process.",
  ],
  [
    "Can it deliver directly to my data lake?",
    "Direct Data Lake delivery is the next planned capability. Today, retrieve conversion results through the API and connect them to your own pipeline. Native delivery destinations and table formats have not been announced.",
  ],
  [
    "Does it already create RAG chunks or lakehouse tables?",
    "No. Document conversion returns Markdown and metadata, including per-page results for multi-page PDFs. Chunking, embeddings, data quality checks and lakehouse table modeling belong in your downstream pipeline today.",
  ],
  [
    "Can I run it on my own infrastructure?",
    "Yes. The repository includes Docker Compose deployment and local workers. Modal is an optional transcription route. Data handling also depends on the engines and providers you configure; the docs explain those choices.",
  ],
  [
    "What are the limits?",
    "Defaults are 50 MB for document uploads, 50 MB for audio and 500 MB for video on the transcription endpoint, and 10 MB of decoded image data for image operations. Image operations also default to 50 million pixels. Deployment settings can change these limits; PDF processing limits depend on the configured engine.",
  ],
  [
    "Where are the code and license?",
    "The code is on GitHub. The repository README declares the MIT license. The project is evolving toward an open source platform for Data Engineering and AI Engineering; follow its implementation and roadmap in the repository.",
  ],
];
