import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowRight,
  ArrowUpRight,
  AudioLines,
  BookOpen,
  Check,
  FileText,
  Image as ImageIcon,
  Layers,
  Workflow,
} from "lucide-react";
import { Brand } from "@/components/brand";
import { GITHUB } from "@/components/landing/content";
import { DOCS_API_URL, DOCS_ORIGIN } from "../docs/config";
import { DOCS_TOPICS, docsHref } from "../docs/topics";
import { FEATURES, type Feature } from "./content";
import styles from "./features.module.css";

import { FeatureExperience } from "./feature-experience";
import { FeatureArtwork, ProductDemo } from "./product-demo";
import { PRODUCT_STORIES } from "./product-stories";

const PRODUCT_ICONS = {
  documents: FileText,
  "audio-video": AudioLines,
  images: ImageIcon,
};
const BENEFIT_ICONS = {
  knowledge: BookOpen,
  structure: Layers,
  workflow: Workflow,
};

export function featureMetadata(feature: Feature): Metadata {
  const url = `${DOCS_ORIGIN}/features/${feature.slug}`;
  return {
    title: feature.metaTitle,
    description: feature.metaDescription,
    alternates: { canonical: url },
    openGraph: {
      title: `${feature.name} | Ingestify`,
      description: feature.metaDescription,
      url,
      type: "website",
      locale: "en_US",
    },
  };
}

function docsTitle(slug: string) {
  const topic = DOCS_TOPICS.find((item) => item.slug === slug);
  if (!topic) throw new Error(`Unknown docs topic: ${slug}`);
  return topic.title.en;
}

export function PublicFooter() {
  return (
    <footer className={styles.footer}>
      <Link href="/" aria-label="Ingestify home">
        <Brand />
      </Link>
      <p>Data Engineering + AI-ready conversion.</p>
      <nav aria-label="Footer links">
        <Link href="/features">Features</Link>
        <Link href="/business">Business</Link>
        <Link href="/agents">For agents</Link>
        <Link href="/docs">Docs</Link>
        <a href={GITHUB}>GitHub</a>
      </nav>
    </footer>
  );
}

export function FeaturePage({ feature }: { feature: Feature }) {
  const story = PRODUCT_STORIES[feature.slug];
  const others = FEATURES.filter((item) => item.slug !== feature.slug);
  const code = feature.example.code.replaceAll("$API", DOCS_API_URL);
  let sectionNumber = 0;
  const label = () => String(++sectionNumber).padStart(2, "0");

  return (
    <FeatureExperience slug={feature.slug} accent={feature.accent}>
      <main id="feature-content">
        <section className={styles.hero} aria-labelledby="feature-title">
          <div className={styles.heroCopy}>
            <p className={styles.eyebrow}>
              <span className={styles.eyebrowDot} aria-hidden="true" />
              {story.eyebrow}
            </p>
            <h1 id="feature-title">
              {feature.title[0]}
              <br />
              <span>{feature.title[1]}</span>
            </h1>
            <p className={styles.heroDescription}>{feature.valueProp}</p>
            <div className={styles.actions}>
              <Link href="/register" className={styles.button}>
                Get started <ArrowUpRight size={17} aria-hidden="true" />
              </Link>
              <Link
                href={docsHref(feature.docs[0].slug, "en")}
                className={styles.textLink}
              >
                Read the docs <ArrowRight size={16} aria-hidden="true" />
              </Link>
            </div>
            <div className={styles.heroTrust}>
              <span>
                <Check size={13} aria-hidden="true" />
                {feature.slug === "audio-video"
                  ? "API transcription"
                  : "Platform + API"}
              </span>
              <span>
                <Check size={13} aria-hidden="true" /> Structured results
              </span>
            </div>
            <p className={styles.heroNote}>{feature.heroNote}</p>
          </div>
          <ProductDemo feature={feature} />
        </section>

        <nav className={styles.productNav} aria-label="Product features">
          {FEATURES.map((item) => {
            const Icon = PRODUCT_ICONS[item.slug];
            return (
              <Link
                key={item.slug}
                href={`/features/${item.slug}`}
                aria-current={item.slug === feature.slug ? "page" : undefined}
              >
                <Icon size={16} aria-hidden="true" />
                {item.name}
                <ArrowUpRight size={14} aria-hidden="true" />
              </Link>
            );
          })}
        </nav>
        <section className={styles.valueSection} aria-labelledby="value-title">
          <div className={styles.stats}>
            {story.stats.map(([value, description]) => (
              <div key={value}>
                <strong>{value}</strong>
                <span>{description}</span>
              </div>
            ))}
            <div className={styles.formatStack}>
              <span>WORKS WITH YOUR FILES</span>
              <div>
                {story.formats.map((format) => (
                  <code key={format}>{format}</code>
                ))}
              </div>
            </div>
          </div>
          <div className={styles.valueIntro}>
            <p className={styles.eyebrow}>
              FROM RAW FILES TO REAL POSSIBILITIES
            </p>
            <h2 id="value-title">{story.promise}</h2>
            <p>{story.intro}</p>
          </div>
          <div className={styles.benefits}>
            {story.benefits.map((benefit, index) => {
              const Icon = BENEFIT_ICONS[benefit.icon];
              return (
                <article key={benefit.title}>
                  <div className={styles.benefitVisual}>
                    <Icon size={36} strokeWidth={1.2} aria-hidden="true" />
                    <span className={styles.benefitOrbit} />
                    <span className={styles.benefitIndex}>0{index + 1}</span>
                  </div>
                  <h3>{benefit.title}</h3>
                  <p>{benefit.body}</p>
                </article>
              );
            })}
          </div>
        </section>

        {feature.sections.map((section) => (
          <section
            key={section.id}
            id={section.id}
            className={`${styles.section} ${section.tone ? styles[section.tone] : ""}`}
            aria-labelledby={`${section.id}-title`}
          >
            <div className={styles.sectionLabel}>
              <span>
                {label()} / {section.label}
              </span>
              <span>{feature.name}</span>
            </div>
            <div className={styles.sectionIntro}>
              <h2 id={`${section.id}-title`}>
                {section.title[0]}
                <br />
                <span>{section.title[1]}</span>
              </h2>
              {section.intro && <p>{section.intro}</p>}
            </div>
            {section.table && (
              <div
                className={styles.tableWrap}
                tabIndex={0}
                role="region"
                aria-label={section.table.caption}
              >
                <table className={styles.table}>
                  <caption className="sr-only">{section.table.caption}</caption>
                  <thead>
                    <tr>
                      {section.table.head.map((cell) => (
                        <th key={cell} scope="col">
                          {cell}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {section.table.rows.map((row) => (
                      <tr key={row[0]}>
                        {row.map((cell, index) =>
                          index === 0 ? (
                            <th key={index} scope="row">
                              <code>{cell}</code>
                            </th>
                          ) : (
                            <td key={index}>{cell}</td>
                          ),
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {section.cards && (
              <div className={styles.cards}>
                {section.cards.map((card, index) => (
                  <article key={card.title}>
                    <span className={styles.cardIcon} aria-hidden="true">
                      {index % 3 === 0 ? (
                        <Layers size={20} strokeWidth={1.5} />
                      ) : index % 3 === 1 ? (
                        <FileText size={20} strokeWidth={1.5} />
                      ) : (
                        <Workflow size={20} strokeWidth={1.5} />
                      )}
                    </span>
                    {card.label && (
                      <span className={styles.cardLabel}>{card.label}</span>
                    )}
                    <h3>{card.title}</h3>
                    <p>{card.body}</p>
                    {card.items && (
                      <ul>
                        {card.items.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    )}
                  </article>
                ))}
              </div>
            )}
          </section>
        ))}

        <section
          className={`${styles.section} ${styles.soft}`}
          id="api"
          aria-labelledby="api-title"
        >
          <div className={styles.sectionLabel}>
            <span>{label()} / API</span>
            <span>X-API-KEY OR BEARER TOKEN</span>
          </div>
          <div className={styles.apiGrid}>
            <div>
              <h2 id="api-title">
                One request.
                <br />
                <span>{feature.example.headline}</span>
              </h2>
              <p>{feature.example.description}</p>
              <ul className={styles.endpoints} aria-label="Endpoints">
                {feature.endpoints.map((endpoint) => (
                  <li key={`${endpoint.method} ${endpoint.path}`}>
                    <code>{endpoint.method}</code>
                    <code>{endpoint.path}</code>
                    <span>{endpoint.purpose}</span>
                  </li>
                ))}
              </ul>
              <Link href="/api-keys" className={styles.textLink}>
                Create an API key <ArrowUpRight size={16} aria-hidden="true" />
              </Link>
            </div>
            <figure className={styles.code}>
              <div className={styles.codeHeading}>
                <span>curl</span>
                <span>{feature.example.title}</span>
              </div>
              <pre
                tabIndex={0}
                aria-label={`curl example: ${feature.example.title}`}
              >
                <code>{code}</code>
              </pre>
              <figcaption>
                Replace $INGESTIFY_API_KEY with your API key.
              </figcaption>
            </figure>
          </div>
        </section>

        <section
          className={styles.section}
          id="docs"
          aria-labelledby="docs-title"
        >
          <div className={styles.sectionLabel}>
            <span>{label()} / DOCUMENTATION</span>
            <span>GUIDES AND API CONTRACTS</span>
          </div>
          <div className={styles.docsGrid}>
            <div>
              <h2 id="docs-title">
                Go deeper.
                <br />
                <span>In the docs.</span>
              </h2>
              <p className={styles.notes}>{feature.availability}</p>
            </div>
            <ul className={styles.docsList}>
              {feature.docs.map(({ slug, note }) => (
                <li key={slug}>
                  <Link href={docsHref(slug, "en")}>
                    <span>
                      {docsTitle(slug)}
                      <small>{note}</small>
                    </span>
                    <ArrowUpRight size={17} aria-hidden="true" />
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className={styles.related} aria-labelledby="related-title">
          <div className={styles.sectionLabel}>
            <span>KEEP EXPLORING</span>
            <span>ONE PLATFORM. MORE POSSIBILITIES.</span>
          </div>
          <h2 id="related-title">
            More inputs. <span>More potential.</span>
          </h2>
          <div className={styles.relatedGrid}>
            {others.map((item) => (
              <Link
                key={item.slug}
                href={`/features/${item.slug}`}
                className={styles.relatedCard}
                data-product={item.slug}
              >
                <div className={styles.relatedArtwork}>
                  <FeatureArtwork slug={item.slug} />
                </div>
                <div>
                  <h3>{item.name}</h3>
                  <p>{item.summary}</p>
                  <span className={styles.textLink}>
                    Explore {item.name}
                    <ArrowUpRight size={16} aria-hidden="true" />
                  </span>
                </div>
              </Link>
            ))}
          </div>
        </section>
        <section className={styles.closing} aria-labelledby="closing-title">
          <div className={styles.closingGlow} aria-hidden="true" />
          <p className={styles.eyebrow}>YOUR NEXT WORKFLOW STARTS HERE</p>
          <h2 id="closing-title">{story.cta}</h2>
          <p>{story.ctaBody}</p>
          <div className={styles.actions}>
            <Link href="/register" className={styles.button}>
              Get started <ArrowRight size={17} aria-hidden="true" />
            </Link>
            <Link href="/docs" className={styles.textLink}>
              Explore the docs <ArrowUpRight size={16} aria-hidden="true" />
            </Link>
          </div>
        </section>
      </main>
      <PublicFooter />
    </FeatureExperience>
  );
}
