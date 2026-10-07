import type { Metadata } from "next";
import { DOCS_GROUPS, DOCS_TOPICS, docsHref, type DocsLang } from "./topics";
import { DOCS_ORIGIN } from "./config";

export function docsMetadata(lang: DocsLang, slug?: string): Metadata {
  const topic = DOCS_TOPICS.find((item) => item.slug === slug);
  const group = DOCS_GROUPS.find((item) => item.id === topic?.group);
  const title = topic
    ? `${topic.title[lang]} | Ingestify Docs`
    : lang === "pt"
      ? "Documentação | Ingestify"
      : "Documentation | Ingestify";
  const description =
    topic && group
      ? `${topic.title[lang]}. ${group.description[lang]}`
      : lang === "pt"
        ? "Guias de uso da plataforma, integração pela API e administração do Ingestify: documentos, imagens, transcrições, jobs e datalakes."
        : "Ingestify platform usage guides, API integration and administration: documents, images, transcripts, jobs and datalakes.";
  const canonical = `${DOCS_ORIGIN}${docsHref(slug, lang)}`;
  return {
    title,
    description,
    alternates: {
      canonical,
      languages: {
        en: `${DOCS_ORIGIN}${docsHref(slug, "en")}`,
        "pt-BR": `${DOCS_ORIGIN}${docsHref(slug, "pt")}`,
        "x-default": `${DOCS_ORIGIN}${docsHref(slug, "en")}`,
      },
    },
    openGraph: {
      title,
      description,
      url: canonical,
      type: "article",
      locale: lang === "pt" ? "pt_BR" : "en_US",
    },
  };
}
