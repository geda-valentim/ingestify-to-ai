import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, ArrowUpRight, AudioLines, FileText, Image as ImageIcon } from "lucide-react";
import { PublicHeader } from "@/components/public-header";
import { DOCS_ORIGIN } from "../docs/config";
import { FEATURES } from "./content";
import { PublicFooter } from "./feature-page";
import styles from "./features.module.css";

const ICONS = { documents: FileText, "audio-video": AudioLines, images: ImageIcon };
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
    <div className={styles.page} lang="en" data-feature="index">
      <a href="#feature-content" className={styles.skip}>
        Skip to content
      </a>
      <PublicHeader />
      <main id="feature-content">
        <section className={styles.hero} aria-labelledby="feature-title">
          <div className={styles.heroCopy}>
            <p className={styles.eyebrow}>FEATURES</p>
            <h1 id="feature-title">
              Three kinds of files.
              <br />
              <span>One processing platform.</span>
            </h1>
            <p className={styles.heroDescription}>{DESCRIPTION}</p>
            <div className={styles.actions}>
              <Link href="/register" className={styles.button}>
                Create an account <ArrowUpRight size={17} aria-hidden="true" />
              </Link>
              <Link href="/docs" className={styles.textLink}>
                Documentation <ArrowRight size={16} aria-hidden="true" />
              </Link>
            </div>
          </div>
        </section>
        <section className={styles.section} aria-label="Feature areas">
          <div className={styles.overview}>
            {FEATURES.map((feature) => {
              const Icon = ICONS[feature.slug];
              return (
                <article key={feature.slug}>
                  <Icon size={32} strokeWidth={1.5} color={feature.accent} aria-hidden="true" />
                  <h2>{feature.name}</h2>
                  <p>{feature.summary}</p>
                  <ul>
                    {feature.highlights.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                  <Link href={`/features/${feature.slug}`} className={styles.textLink}>
                    Explore {feature.name}
                    <ArrowUpRight size={16} aria-hidden="true" />
                  </Link>
                </article>
              );
            })}
          </div>
        </section>
        <section className={`${styles.section} ${styles.soft}`} aria-labelledby="shared-title">
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
              (X-API-Key) or a session token, and set purge_source=true to delete
              the uploaded file once the job is final.
            </p>
          </div>
        </section>
      </main>
      <PublicFooter />
    </div>
  );
}
