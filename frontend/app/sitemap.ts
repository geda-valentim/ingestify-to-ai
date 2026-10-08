import type { MetadataRoute } from "next";
import { DOCS_ORIGIN } from "./docs/config";
import { DOCS_TOPICS, docsHref } from "./docs/topics";
import { FEATURES } from "./features/content";
export default function sitemap(): MetadataRoute.Sitemap {
  return [
    { url: DOCS_ORIGIN },
    { url: `${DOCS_ORIGIN}/agents` },
    { url: `${DOCS_ORIGIN}/business` },
    { url: `${DOCS_ORIGIN}/features` },
    ...FEATURES.map((feature) => ({
      url: `${DOCS_ORIGIN}/features/${feature.slug}`,
    })),
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
