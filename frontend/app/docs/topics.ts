export type DocsLang = "pt" | "en";
type Localized = Record<DocsLang, string>;

export const DOCS_GROUPS: {
  id: string;
  title: Localized;
  description: Localized;
}[] = [
  {
    id: "platform",
    title: { pt: "Usar a plataforma", en: "Use the platform" },
    description: {
      pt: "Passos nas telas: processe arquivos, explore resultados e organize a entrega dos dados.",
      en: "Screen-by-screen guides to process files, explore results and organize data delivery.",
    },
  },
  {
    id: "api",
    title: { pt: "Integrar pela API", en: "Integrate with the API" },
    description: {
      pt: "Autenticação, contratos HTTP e exemplos para integrar o Ingestify à sua aplicação.",
      en: "Authentication, HTTP contracts and examples to integrate Ingestify into your application.",
    },
  },
  {
    id: "administration",
    title: { pt: "Administrar", en: "Administer" },
    description: {
      pt: "Configure engines, perfis, rotas, acesso e capacidade da instalação.",
      en: "Configure engines, profiles, routing, access and installation capacity.",
    },
  },
];

export const DOCS_TOPICS: {
  slug: string;
  anchor: string;
  group: string;
  title: Localized;
}[] = [
  {
    slug: "platform-start",
    anchor: "platform-start",
    group: "platform",
    title: { pt: "Primeiro processamento", en: "Your first processing job" },
  },
  {
    slug: "platform-projects-jobs",
    anchor: "platform-projects-jobs",
    group: "platform",
    title: {
      pt: "Organizar projetos e acompanhar jobs",
      en: "Organize projects and track jobs",
    },
  },
  {
    slug: "platform-documents",
    anchor: "platform-documents",
    group: "platform",
    title: {
      pt: "Converter e revisar documentos",
      en: "Convert and review documents",
    },
  },
  {
    slug: "platform-transcription",
    anchor: "platform-transcription",
    group: "platform",
    title: {
      pt: "Usar transcrições e captura ao vivo",
      en: "Use transcripts and live capture",
    },
  },
  {
    slug: "platform-images",
    anchor: "platform-images",
    group: "platform",
    title: {
      pt: "Explorar imagens com Full Analysis",
      en: "Explore images with Full Analysis",
    },
  },
  {
    slug: "platform-datalakes",
    anchor: "platform-datalakes",
    group: "platform",
    title: {
      pt: "Conectar buckets e conferir entregas",
      en: "Connect buckets and verify delivery",
    },
  },
  {
    slug: "platform-partitioning",
    anchor: "platform-partitioning",
    group: "platform",
    title: {
      pt: "Organizar dados por cliente",
      en: "Organize data by customer",
    },
  },
  {
    slug: "introduction",
    anchor: "introducao",
    group: "api",
    title: { pt: "Introdução", en: "Introduction" },
  },
  {
    slug: "authentication",
    anchor: "autenticacao",
    group: "api",
    title: { pt: "Autenticação", en: "Authentication" },
  },
  {
    slug: "projects",
    anchor: "projetos",
    group: "api",
    title: { pt: "Projetos e pastas", en: "Projects and folders" },
  },
  {
    slug: "documents",
    anchor: "documentos",
    group: "api",
    title: { pt: "PDF e documentos", en: "PDF and documents" },
  },
  {
    slug: "pdf-pages",
    anchor: "paginas-pdf",
    group: "api",
    title: { pt: "Páginas de PDF", en: "PDF pages" },
  },
  {
    slug: "images",
    anchor: "imagens",
    group: "api",
    title: {
      pt: "Imagens: descrição e OCR",
      en: "Images: description and OCR",
    },
  },
  {
    slug: "transcription",
    anchor: "transcribe",
    group: "api",
    title: {
      pt: "Transcrição de áudio e vídeo",
      en: "Audio and video transcription",
    },
  },
  {
    slug: "file-captions",
    anchor: "transcribe-live",
    group: "api",
    title: { pt: "Legendas de arquivos", en: "File captions" },
  },
  {
    slug: "live",
    anchor: "microfone-live",
    group: "api",
    title: { pt: "Captura ao vivo", en: "Live capture" },
  },
  {
    slug: "job-status",
    anchor: "transcribe-status",
    group: "api",
    title: { pt: "Acompanhar o job", en: "Track the job" },
  },
  {
    slug: "results",
    anchor: "transcribe-result",
    group: "api",
    title: { pt: "Baixar o resultado", en: "Download the result" },
  },
  {
    slug: "datalakes",
    anchor: "datalakes",
    group: "api",
    title: { pt: "Datalakes e buckets", en: "Datalakes and buckets" },
  },
  {
    slug: "errors",
    anchor: "transcribe-erros",
    group: "api",
    title: { pt: "Erros", en: "Errors" },
  },
  {
    slug: "platform-settings",
    anchor: "platform-settings",
    group: "administration",
    title: { pt: "Configurações da plataforma", en: "Platform settings" },
  },
  {
    slug: "administration-overview",
    anchor: "administration-overview",
    group: "administration",
    title: {
      pt: "Administrar a instalação",
      en: "Administer the installation",
    },
  },
  {
    slug: "compute",
    anchor: "compute",
    group: "administration",
    title: { pt: "Compute e motores", en: "Compute and engines" },
  },
  {
    slug: "engines",
    anchor: "engines",
    group: "administration",
    title: { pt: "Recursos das engines", en: "Engine features" },
  },
  {
    slug: "engine-operations",
    anchor: "engine-operations",
    group: "administration",
    title: { pt: "Operações de engines", en: "Engine operations" },
  },
  {
    slug: "execution-profiles",
    anchor: "execution-profiles",
    group: "administration",
    title: { pt: "Perfis de execução", en: "Execution profiles" },
  },
  {
    slug: "engine-access",
    anchor: "engine-access",
    group: "administration",
    title: {
      pt: "Acesso e permissões (IAM)",
      en: "Access and permissions (IAM)",
    },
  },
];

export function docsHref(slug: string | undefined, lang: DocsLang) {
  return `${lang === "pt" ? "/pt" : ""}/docs${slug ? `/${slug}` : ""}`;
}

/** Related workflows connect screen instructions to preserved API contracts. */
export const DOCS_RELATED: Record<string, string[]> = {
  "platform-start": ["documents", "authentication"],
  "platform-projects-jobs": ["projects", "job-status", "results"],
  "platform-documents": ["documents", "pdf-pages", "results"],
  "platform-transcription": ["transcription", "file-captions", "live"],
  "platform-images": ["images"],
  "platform-datalakes": ["datalakes", "platform-partitioning"],
  "platform-partitioning": ["datalakes", "projects", "platform-datalakes"],
  "administration-overview": [
    "compute",
    "engines",
    "engine-operations",
    "execution-profiles",
    "engine-access",
    "platform-settings",
  ],
};

export function relatedDocs(slug: string) {
  const direct = DOCS_RELATED[slug] ?? [];
  const inverse = Object.entries(DOCS_RELATED)
    .filter(([, related]) => related.includes(slug))
    .map(([guide]) => guide);
  return [...new Set([...direct, ...inverse])]
    .map((related) => DOCS_TOPICS.find((topic) => topic.slug === related))
    .filter((topic): topic is (typeof DOCS_TOPICS)[number] => !!topic);
}
