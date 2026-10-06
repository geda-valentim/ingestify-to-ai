import type { MetadataRoute } from "next";
import { DOCS_ORIGIN } from "./docs/config";
import { DOCS_TOPICS, docsHref } from "./docs/topics";
export default function sitemap(): MetadataRoute.Sitemap {
  return [
    { url: DOCS_ORIGIN },
    ...[undefined, ...DOCS_TOPICS.map((topic) => topic.slug)].flatMap((slug) =>
      (["en", "pt"] as const).map((lang) => ({
        url: `${DOCS_ORIGIN}${docsHref(slug, lang)}`,
        alternates: {
          languages: {
            en: `${DOCS_ORIGIN}${docsHref(slug, "en")}`,
            "pt-BR": `${DOCS_ORIGIN}${docsHref(slug, "pt")}`,
          },
        },
      })),
    ),
  ];
}
