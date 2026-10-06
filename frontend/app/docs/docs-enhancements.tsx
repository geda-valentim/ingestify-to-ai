"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { DOCS_TOPICS, docsHref, type DocsLang } from "./topics";

/** Legacy section links keep working; all readable content is server-rendered. */
export function DocsEnhancements({
  topic,
  lang,
}: {
  topic?: string;
  lang: DocsLang;
}) {
  const router = useRouter();
  useEffect(() => {
    const previous = document.documentElement.lang;
    document.documentElement.lang = lang === "pt" ? "pt-BR" : "en";
    const redirectAnchor = () => {
      const target = DOCS_TOPICS.find(
        (item) => `#${item.anchor}` === location.hash,
      );
      if (target && target.slug !== topic) {
        router.replace(`${docsHref(target.slug, lang)}#${target.anchor}`);
      }
    };
    redirectAnchor();
    addEventListener("hashchange", redirectAnchor);
    return () => {
      document.documentElement.lang = previous;
      removeEventListener("hashchange", redirectAnchor);
    };
  }, [topic, lang, router]);
  return null;
}
