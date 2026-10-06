export type DocsLang = "pt" | "en";
type Localized = Record<DocsLang, string>;

export const DOCS_GROUPS: {
  id: string;
  title: Localized;
  description: Localized;
}[] = [
  {
    id: "start",
    title: { pt: "Primeiros passos", en: "Getting started" },
    description: {
      pt: "Conheça a API, autentique suas chamadas e organize seus arquivos.",
      en: "Explore the API, authenticate requests and organize your files.",
    },
  },
  {
    id: "documents",
    title: { pt: "Documentos e imagens", en: "Documents and images" },
    description: {
      pt: "Converta documentos, consulte páginas de PDF e extraia texto de imagens.",
      en: "Convert documents, inspect PDF pages and extract text from images.",
    },
  },
  {
    id: "audio",
    title: { pt: "Áudio e vídeo", en: "Audio and video" },
    description: {
      pt: "Transcreva arquivos, acompanhe legendas e capture áudio ao vivo.",
      en: "Transcribe files, follow captions and capture live audio.",
    },
  },
  {
    id: "compute",
    title: {
      pt: "Engines, perfis e acesso",
      en: "Engines, profiles and access",
    },
    description: {
      pt: "Requisitos, configuração e aplicações de runtime, rotas e permissões.",
      en: "Requirements, configuration and use cases for runtime, routing and permissions.",
    },
  },
  {
    id: "operations",
    title: { pt: "Jobs e operação", en: "Jobs and operations" },
    description: {
      pt: "Acompanhe o processamento, baixe resultados e consulte erros e motores.",
      en: "Track processing, download results and understand errors and engines.",
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
    slug: "introduction",
    anchor: "introducao",
    group: "start",
    title: { pt: "Introdução", en: "Introduction" },
  },
  {
    slug: "authentication",
    anchor: "autenticacao",
    group: "start",
    title: { pt: "Autenticação", en: "Authentication" },
  },
  {
    slug: "projects",
    anchor: "projetos",
    group: "start",
    title: { pt: "Projetos e pastas", en: "Projects and folders" },
  },
  {
    slug: "documents",
    anchor: "documentos",
    group: "documents",
    title: { pt: "PDF e documentos", en: "PDF and documents" },
  },
  {
    slug: "pdf-pages",
    anchor: "paginas-pdf",
    group: "documents",
    title: { pt: "Páginas de PDF", en: "PDF pages" },
  },
  {
    slug: "images",
    anchor: "imagens",
    group: "documents",
    title: {
      pt: "Imagens: descrição e OCR",
      en: "Images: description and OCR",
    },
  },
  {
    slug: "transcription",
    anchor: "transcribe",
    group: "audio",
    title: {
      pt: "Transcrição de áudio e vídeo",
      en: "Audio and video transcription",
    },
  },
  {
    slug: "file-captions",
    anchor: "transcribe-live",
    group: "audio",
    title: { pt: "Legendas de arquivos", en: "File captions" },
  },
  {
    slug: "live",
    anchor: "microfone-live",
    group: "audio",
    title: { pt: "Captura ao vivo", en: "Live capture" },
  },
  {
    slug: "job-status",
    anchor: "transcribe-status",
    group: "operations",
    title: { pt: "Acompanhar o job", en: "Track the job" },
  },
  {
    slug: "results",
    anchor: "transcribe-result",
    group: "operations",
    title: { pt: "Baixar o resultado", en: "Download the result" },
  },
  {
    slug: "datalakes",
    anchor: "datalakes",
    group: "operations",
    title: { pt: "Datalakes e buckets", en: "Datalakes and buckets" },
  },
  {
    slug: "errors",
    anchor: "transcribe-erros",
    group: "operations",
    title: { pt: "Erros", en: "Errors" },
  },
  {
    slug: "platform-settings",
    anchor: "platform-settings",
    group: "operations",
    title: { pt: "Configurações da plataforma", en: "Platform settings" },
  },
  {
    slug: "compute",
    anchor: "compute",
    group: "compute",
    title: { pt: "Compute e motores", en: "Compute and engines" },
  },
  {
    slug: "engines",
    anchor: "engines",
    group: "compute",
    title: { pt: "Recursos das engines", en: "Engine features" },
  },
  {
    slug: "engine-operations",
    anchor: "engine-operations",
    group: "compute",
    title: { pt: "Operações de engines", en: "Engine operations" },
  },
  {
    slug: "execution-profiles",
    anchor: "execution-profiles",
    group: "compute",
    title: { pt: "Perfis de execução", en: "Execution profiles" },
  },
  {
    slug: "engine-access",
    anchor: "engine-access",
    group: "compute",
    title: { pt: "Acesso RBAC e ABAC", en: "RBAC and ABAC access" },
  },
];

export function docsHref(slug: string | undefined, lang: DocsLang) {
  return `${lang === "pt" ? "/pt" : ""}/docs${slug ? `/${slug}` : ""}`;
}
