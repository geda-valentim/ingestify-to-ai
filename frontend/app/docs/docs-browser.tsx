import Link from "next/link";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { AppHeader } from "@/components/app-header";
import { DOCS_API_URL as API_URL } from "./config";
import { DOCS_GROUPS, DOCS_TOPICS, docsHref, type DocsLang } from "./topics";
import { TopicContent } from "./topic-content";
import { DocsEnhancements } from "./docs-enhancements";

export function DocsBrowser({
  topic,
  lang = "en",
}: {
  topic?: string;
  lang?: DocsLang;
}) {
  const currentIndex = DOCS_TOPICS.findIndex((item) => item.slug === topic);
  const current = DOCS_TOPICS[currentIndex];
  const group = DOCS_GROUPS.find((item) => item.id === current?.group);
  const pt = lang === "pt";

  const navigation = (
    <nav
      aria-label={pt ? "Tópicos da documentação" : "Documentation topics"}
      className="space-y-5 text-sm"
    >
      <Link
        href={docsHref(undefined, lang)}
        aria-current={!topic ? "page" : undefined}
        className={`block rounded-md px-3 py-2 font-medium ${!topic ? "bg-primary/10 text-primary" : "hover:bg-muted"}`}
      >
        {pt ? "Visão geral" : "Overview"}
      </Link>
      {DOCS_GROUPS.map((section) => (
        <div key={section.id}>
          <p className="px-3 pb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {section.title[lang]}
          </p>
          <ul className="space-y-1 border-l ml-3">
            {DOCS_TOPICS.filter((item) => item.group === section.id).map(
              (item) => (
                <li key={item.slug}>
                  <Link
                    href={docsHref(item.slug, lang)}
                    aria-current={item.slug === topic ? "page" : undefined}
                    className={`ml-2 block rounded-md px-3 py-2 ${item.slug === topic ? "bg-primary/10 font-medium text-primary" : "text-muted-foreground hover:bg-muted hover:text-foreground"}`}
                  >
                    {item.title[lang]}
                  </Link>
                </li>
              ),
            )}
          </ul>
        </div>
      ))}
      <Link
        href="/agents"
        className="block px-3 text-primary underline underline-offset-4"
      >
        {pt ? "Ingestify para agentes" : "Ingestify for agents"}
      </Link>
      <a
        href={`${API_URL}/openapi.json`}
        className="block px-3 text-primary underline underline-offset-4"
      >
        OpenAPI JSON
      </a>
      <a
        href={`${API_URL}/docs`}
        target="_blank"
        rel="noreferrer"
        className="block px-3 text-primary underline underline-offset-4"
      >
        Swagger ↗
      </a>
    </nav>
  );

  return (
    <div className="min-h-screen bg-background" lang={pt ? "pt-BR" : "en"}>
      <DocsEnhancements topic={topic} lang={lang} />
      <AppHeader className="sticky top-0 z-20" />
      <div className="container mx-auto px-4 py-6 lg:py-8">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-3 border-b pb-4">
          <Link
            href={docsHref(undefined, lang)}
            className="text-lg font-semibold"
          >
            {pt ? "Documentação" : "Documentation"}
          </Link>
          <div
            className="flex gap-1"
            role="group"
            aria-label="Idioma / Language"
          >
            {(
              [
                ["pt", "Português"],
                ["en", "English"],
              ] as const
            ).map(([value, label]) => (
              <Link
                key={value}
                href={docsHref(topic, value)}
                hrefLang={value === "pt" ? "pt-BR" : "en"}
                aria-current={lang === value ? "page" : undefined}
                className={`rounded-md px-3 py-2 text-sm font-medium hover:bg-muted ${lang === value ? "bg-secondary" : ""}`}
              >
                {label}
              </Link>
            ))}
          </div>
        </div>
        <div className="flex flex-col gap-8 lg:flex-row lg:gap-12">
          <aside className="lg:w-64 lg:shrink-0">
            <details className="rounded-lg border p-4 lg:hidden">
              <summary className="cursor-pointer text-sm font-medium">
                {pt ? "Explorar tópicos" : "Browse topics"}
                {current ? ` · ${current.title[lang]}` : ""}
              </summary>
              <div className="pt-5">{navigation}</div>
            </details>
            <div className="hidden lg:block lg:sticky lg:top-24 lg:max-h-[calc(100vh-7rem)] lg:overflow-y-auto lg:pb-4">
              {navigation}
            </div>
          </aside>
          <main id="docs-content" className="min-w-0 flex-1 max-w-4xl">
            {current ? (
              <>
                <nav
                  aria-label={pt ? "Localização" : "Breadcrumb"}
                  className="mb-5 flex flex-wrap gap-2 text-sm text-muted-foreground"
                >
                  <Link
                    href={docsHref(undefined, lang)}
                    className="hover:underline"
                  >
                    Docs
                  </Link>
                  <span aria-hidden="true">/</span>
                  <span>{group?.title[lang]}</span>
                  <span aria-hidden="true">/</span>
                  <span aria-current="page">{current.title[lang]}</span>
                </nav>
                <TopicContent topic={current.slug} lang={lang} />
                <nav
                  aria-label={pt ? "Outros tópicos" : "Other topics"}
                  className="mt-10 grid grid-cols-1 gap-3 border-t pt-6 sm:grid-cols-2"
                >
                  {[
                    DOCS_TOPICS[currentIndex - 1],
                    DOCS_TOPICS[currentIndex + 1],
                  ].map((item, index) =>
                    item ? (
                      <Link
                        key={item.slug}
                        href={docsHref(item.slug, lang)}
                        className={`flex items-center gap-3 rounded-lg border p-4 hover:bg-muted ${index === 1 ? "sm:col-start-2 sm:justify-end sm:text-right" : ""}`}
                      >
                        {index === 0 && (
                          <ArrowLeft
                            aria-hidden="true"
                            className="h-4 w-4 shrink-0"
                          />
                        )}
                        <span>
                          <span className="block text-xs text-muted-foreground">
                            {index === 0
                              ? pt
                                ? "Anterior"
                                : "Previous"
                              : pt
                                ? "Próximo"
                                : "Next"}
                          </span>
                          {item.title[lang]}
                        </span>
                        {index === 1 && (
                          <ArrowRight
                            aria-hidden="true"
                            className="h-4 w-4 shrink-0"
                          />
                        )}
                      </Link>
                    ) : null,
                  )}
                </nav>
              </>
            ) : (
              <>
                <h1 className="text-3xl font-semibold tracking-tight">
                  {pt ? "O que você quer fazer?" : "What would you like to do?"}
                </h1>
                <p className="mt-3 text-muted-foreground">
                  {pt
                    ? "Guias e exemplos de API organizados por assunto. Escolha um tópico para começar."
                    : "Guides and API examples organized by topic. Choose a topic to get started."}
                </p>
                <div className="mt-8 grid gap-5 md:grid-cols-2">
                  {DOCS_GROUPS.map((section) => (
                    <section key={section.id} className="rounded-xl border p-5">
                      <h2 className="text-lg font-semibold">
                        {section.title[lang]}
                      </h2>
                      <p className="mt-2 text-sm text-muted-foreground">
                        {section.description[lang]}
                      </p>
                      <ul className="mt-4 space-y-1">
                        {DOCS_TOPICS.filter(
                          (item) => item.group === section.id,
                        ).map((item) => (
                          <li key={item.slug}>
                            <Link
                              href={docsHref(item.slug, lang)}
                              className="flex items-center justify-between gap-2 rounded-md py-2 text-sm text-primary hover:underline"
                            >
                              {item.title[lang]}
                              <ArrowRight
                                aria-hidden="true"
                                className="h-4 w-4 shrink-0"
                              />
                            </Link>
                          </li>
                        ))}
                      </ul>
                    </section>
                  ))}
                </div>
              </>
            )}
          </main>
        </div>
      </div>
    </div>
  );
}
