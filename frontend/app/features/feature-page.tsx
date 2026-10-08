import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  AudioLines,
  FileText,
  Image as ImageIcon,
  Layers,
  Mic,
  ScanText,
  Video,
} from "lucide-react";
import { Brand } from "@/components/brand";
import { PublicHeader } from "@/components/public-header";
import { GITHUB } from "@/components/landing/content";
import { DOCS_API_URL, DOCS_ORIGIN } from "../docs/config";
import { DOCS_TOPICS, docsHref } from "../docs/topics";
import { FEATURES, type Feature, type IconName } from "./content";
import styles from "./features.module.css";

const ICONS = {
  document: FileText,
  scan: ScanText,
  audio: AudioLines,
  mic: Mic,
  video: Video,
  image: ImageIcon,
} satisfies Record<IconName, unknown>;

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

function HeroFigure({ feature }: { feature: Feature }) {
  const { figure } = feature;
  return (
    <figure
      className={styles.figure}
      aria-labelledby={`${feature.slug}-figure-caption`}
      style={{ ["--accent" as string]: feature.accent }}
    >
      <div className={styles.figureHeading}>
        <span>{figure.heading}</span>
        <span>Illustrative example</span>
      </div>
      <div className={styles.figureInputs}>
        {figure.inputs.map(({ icon, label }) => {
          const Icon = ICONS[icon];
          return (
            <div key={label}>
              <Icon size={19} aria-hidden="true" />
              <span>{label}</span>
            </div>
          );
        })}
      </div>
      <div className={styles.connector} aria-hidden="true">
        <ArrowDown size={21} />
      </div>
      <div className={styles.processor}>
        <div>
          <Layers size={23} aria-hidden="true" />
          <strong>Ingestify</strong>
          <span>{figure.engine}</span>
        </div>
        <ol>
          {figure.steps.map((step, index) => (
            <li key={step}>
              <span>{String(index + 1).padStart(2, "0")}</span> {step}
            </li>
          ))}
        </ol>
      </div>
      <div className={styles.connector} aria-hidden="true">
        <ArrowDown size={21} />
      </div>
      <div className={styles.outputs} aria-label="Outputs">
        {figure.outputs.map((output) => (
          <span key={output}>{output}</span>
        ))}
      </div>
      <figcaption id={`${feature.slug}-figure-caption`}>
        {figure.caption}
      </figcaption>
    </figure>
  );
}

export function FeaturePage({ feature }: { feature: Feature }) {
  const others = FEATURES.filter((item) => item.slug !== feature.slug);
  const code = feature.example.code.replaceAll("$API", DOCS_API_URL);
  let sectionNumber = 0;
  const label = () => String(++sectionNumber).padStart(2, "0");

  return (
    <div className={styles.page} lang="en" data-feature={feature.slug}>
      <a href="#feature-content" className={styles.skip}>
        Skip to content
      </a>
      <PublicHeader />
      <main id="feature-content">
        <section className={styles.hero} aria-labelledby="feature-title">
          <div className={styles.heroCopy}>
            <p className={styles.eyebrow}>
              <Link href="/features">Features</Link> / {feature.name}
            </p>
            <h1 id="feature-title">
              {feature.title[0]}
              <br />
              <span>{feature.title[1]}</span>
            </h1>
            <p className={styles.heroDescription}>{feature.valueProp}</p>
            <div className={styles.actions}>
              <Link href="/register" className={styles.button}>
                Create an account <ArrowUpRight size={17} aria-hidden="true" />
              </Link>
              <Link href={docsHref(feature.docs[0].slug, "en")} className={styles.textLink}>
                Read the docs <ArrowRight size={16} aria-hidden="true" />
              </Link>
            </div>
            <p className={styles.heroNote}>{feature.heroNote}</p>
          </div>
          <HeroFigure feature={feature} />
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
                {section.cards.map((card) => (
                  <article key={card.title}>
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
              <pre tabIndex={0} aria-label={`curl example: ${feature.example.title}`}>
                <code>{code}</code>
              </pre>
              <figcaption>Replace $INGESTIFY_API_KEY with your API key.</figcaption>
            </figure>
          </div>
        </section>

        <section className={styles.section} id="docs" aria-labelledby="docs-title">
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

        <section className={styles.closing} aria-labelledby="closing-title">
          <p className={styles.eyebrow}>MORE FEATURES</p>
          <h2 id="closing-title">
            Bring a real file.
            <br />
            <span>See what comes back.</span>
          </h2>
          <p>
            Ingestify also handles{" "}
            {others.map((item, index) => (
              <span key={item.slug}>
                {index > 0 && " and "}
                <Link href={`/features/${item.slug}`} className={styles.inlineLink}>
                  {item.name.toLowerCase()}
                </Link>
              </span>
            ))}{" "}
            through the same jobs, projects and API keys.
          </p>
          <div className={styles.actions}>
            <Link href="/register" className={styles.button}>
              Create an account <ArrowRight size={17} aria-hidden="true" />
            </Link>
            <Link href="/docs" className={styles.textLink}>
              Documentation <ArrowUpRight size={16} aria-hidden="true" />
            </Link>
          </div>
        </section>
      </main>
      <PublicFooter />
    </div>
  );
}
