export const GITHUB = "https://github.com/geda-valentim/ingestify-to-ai";
export const chapters = [
  {
    name: "Files",
    eyebrow: "THE INPUT IS JUST THE BEGINNING",
    title: "Your files.\nAI-ready.",
    body: "Turn documents, images and recordings into information your applications can actually use.",
    action: "Explore the platform",
    href: "/login",
    note: "",
  },
  {
    name: "Documents",
    eyebrow: "01 / EXTRACT THE STRUCTURE",
    title: "Documents in.\nMarkdown out.",
    body: "Keep the text, tables and structure. Follow document processing down to the individual PDF page.",
    action: "Explore documents",
    href: "/docs?lang=en#documentos",
    note: "",
  },
  {
    name: "Audio",
    eyebrow: "02 / FOLLOW THE CONVERSATION",
    title: "Give audio\na text layer.",
    body: "Transcripts, timestamps and captions. Make your recordings part of a searchable, reusable workflow.",
    action: "Explore transcription",
    href: "/docs?lang=en#transcribe",
    note: "Video transcription processes the audio track.",
  },
  {
    name: "Images",
    eyebrow: "03 / READ BETWEEN THE PIXELS",
    title: "More than\nan image.",
    body: "Extract text and its regions with OCR. Generate image descriptions through the API.",
    action: "Explore image operations",
    href: "/docs?lang=en#imagens",
    note: "",
  },
  {
    name: "Compute",
    eyebrow: "04 / CHOOSE YOUR RESOURCES",
    title: "Your compute.\nYour call.",
    body: "Local workers and optional Modal transcription. Configure execution around capacity, priority and budget.",
    action: "Explore compute",
    href: "/docs?lang=en#compute",
    note: "Where data goes also depends on the provider you choose.",
  },
  {
    name: "Connect",
    eyebrow: "05 / PART OF YOUR WORKFLOW",
    title: "One operation.\nYour application.",
    body: "Keep results organized by project and tags. Bring the same operations into your own tools with the API.",
    action: "See the API in action",
    href: "#api",
    note: "",
  },
  {
    name: "Next",
    eyebrow: "PLANNED EVOLUTION",
    title: "Start local.\nThink beyond.",
    body: "Our direction: connect more machines and compose reusable operations in an open platform.",
    action: "Follow on GitHub",
    href: GITHUB,
    note: "General distributed execution and operation composition are planned capabilities.",
  },
  {
    name: "Build",
    eyebrow: "MAKE SOMETHING WITH IT",
    title: "Your next idea\nstarts here.",
    body: "Explore the project. Read the API. Put your information to work.",
    action: "Read the documentation",
    href: "/docs?lang=en",
    note: "",
  },
];
export const example = [
  'curl -X POST "https://dev.ingestify.ai/api/upload" \\',
  '  -H "X-API-Key: YOUR_API_KEY" \\',
  '  -F "file=@report.pdf" \\',
  '  -F "project=Documents" \\',
  '  -F "docling_preset=quality"',
].join("\n");
export const faq = [
  [
    "What can I transform?",
    "Documents into Markdown, recordings into transcripts and captions, and images into OCR text or descriptions through the API. See the docs for supported formats and limits.",
  ],
  [
    "Can everything run locally?",
    "Local workers are available. Processing and data destinations also depend on the selected engine and provider. External providers may send content to other services; check your configuration before processing sensitive files.",
  ],
  [
    "What runs in the cloud today?",
    "The Modal integration supports transcription with configured capacity, priority and budget rules. General distributed execution and operation composition are planned capabilities.",
  ],
  [
    "Does transcription analyze video scenes?",
    "No. Video transcription processes the audio track. Its output represents speech, not visual scene analysis.",
  ],
  [
    "How do I integrate it?",
    "Create an API key and use the documented endpoints. Documents and transcription use asynchronous jobs; image operations can return their result in the same request.",
  ],
  [
    "Where can I follow the project?",
    "The code is available on GitHub. Our vision is an open source platform built with the community. Check the repository for feature status, licensing and contribution information.",
  ],
];
