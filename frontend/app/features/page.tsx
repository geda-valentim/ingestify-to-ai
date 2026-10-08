import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowRight,
  ArrowUpRight,
  AudioLines,
  FileText,
  Image as ImageIcon,
} from "lucide-react";
import { FeatureExperience } from "./feature-experience";
import { FeatureArtwork, PlatformArtwork } from "./product-demo";
import { PRODUCT_STORIES } from "./product-stories";
import { DOCS_ORIGIN } from "../docs/config";
import { FEATURES } from "./content";
import { PublicFooter } from "./feature-page";
import styles from "./features.module.css";

const ICONS = {
  documents: FileText,
  "audio-video": AudioLines,
  images: ImageIcon,
};
const DESCRIPTION =
  "Ingestify turns documents into Markdown, recordings into timestamped transcripts and images into captions, text and regions — through one platform, one job model and one API.";

export const dynamic = "error";
export const metadata: Metadata = {
  title: "Features — Documents, Audio & Video, Images | Ingestify",
  description: DESCRIPTION,
  alternates: { canonical: `${DOCS_ORIGIN}/features` },
  openGraph: {
    title: "Ingestify features",
    description: DESCRIPTION,
    url: `${DOCS_ORIGIN}/features`,
    type: "website",
    locale: "en_US",
  },
};

export default function FeaturesIndexPage() {
  return (
    <FeatureExperience slug="index">
      <main id="feature-content">
        <section className={styles.hero} aria-labelledby="feature-title">
          <div className={styles.heroCopy}>
            <p className={styles.eyebrow}>
              <span className={styles.eyebrowDot} aria-hidden="true" /> ONE
              PLATFORM. EVERY INPUT.
            </p>
            <h1 id="feature-title">
              Every file holds potential.
              <br />
              <span>Make it useful.</span>
            </h1>
            <p className={styles.heroDescription}>{DESCRIPTION}</p>
            <div className={styles.actions}>
              <Link href="/register" className={styles.button}>
                Get started <ArrowUpRight size={17} aria-hidden="true" />
              </Link>
              <Link href="/docs" className={styles.textLink}>
                Documentation <ArrowRight size={16} aria-hidden="true" />
              </Link>
            </div>
          </div>
          <PlatformArtwork />
        </section>
        <section className={styles.section} aria-label="Feature areas">
          <div className={styles.sectionLabel}>
            <span>EXPLORE THE PRODUCTS</span>
            <span>DOCUMENTS · AUDIO & VIDEO · IMAGES</span>
          </div>
          <div className={styles.overview}>
            {FEATURES.map((feature) => {
              const Icon = ICONS[feature.slug];
              return (
                <article key={feature.slug} data-product={feature.slug}>
                  <Link
                    href={`/features/${feature.slug}`}
                    className={styles.overviewArtwork}
                    aria-label={`Explore ${feature.name}`}
                  >
                    <FeatureArtwork slug={feature.slug} />
                  </Link>
                  <Icon
                    size={32}
                    strokeWidth={1.5}
                    color={feature.accent}
                    aria-hidden="true"
                  />
                  <h2>{feature.name}</h2>
                  <p>{PRODUCT_STORIES[feature.slug].promise}</p>
                  <ul>
                    {feature.highlights.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                  <Link
                    href={`/features/${feature.slug}`}
                    className={styles.textLink}
                  >
                    Explore {feature.name}
                    <ArrowUpRight size={16} aria-hidden="true" />
                  </Link>
                </article>
              );
            })}
          </div>
        </section>
        <section
          className={`${styles.section} ${styles.soft}`}
          aria-labelledby="shared-title"
        >
          <div className={styles.sectionLabel}>
            <span>SHARED BY EVERY FEATURE</span>
            <span>JOBS · PROJECTS · API KEYS</span>
          </div>
          <div className={styles.sectionIntro}>
            <h2 id="shared-title">
              Same jobs.
              <br />
              <span>Same projects.</span>
            </h2>
            <p>
              Every request belongs to a project and folder, can carry tags and
              returns a job you can track. Authenticate with an API key
              (X-API-Key) or a session token, and set purge_source=true to
              delete the uploaded file once the job is final.
            </p>
          </div>
        </section>
        <section className={styles.closing} aria-labelledby="closing-title">
          <div className={styles.closingGlow} aria-hidden="true" />
          <p className={styles.eyebrow}>BUILT FOR YOUR NEXT WORKFLOW</p>
          <h2 id="closing-title">
            Bring your files.
            <br />
            <span>Build something useful.</span>
          </h2>
          <p>
            Start with one conversion. Connect the results to your next idea.
          </p>
          <div className={styles.actions}>
            <Link href="/register" className={styles.button}>
              Get started <ArrowUpRight size={17} aria-hidden="true" />
            </Link>
            <Link href="/docs" className={styles.textLink}>
              Explore the docs <ArrowRight size={16} aria-hidden="true" />
            </Link>
          </div>
        </section>
      </main>
      <PublicFooter />
    </FeatureExperience>
  );
}
