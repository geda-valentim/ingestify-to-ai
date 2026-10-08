"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowUpRight, ArrowRight, Github, Check, Copy } from "lucide-react";
import { GITHUB, example, resultExample, faq } from "./content";
import { useOperationScroll } from "./use-operation-scroll";
import {
  OperationDiagram,
  ComputeDiagram,
  SpectralLines,
  LakeDeliveryDiagram,
} from "./landing-svg";

/** Progressive enhancement: content remains visible without JavaScript. */
export function useLandingMotion() {
  useEffect(() => {
    const root = document.querySelector<HTMLElement>(".landing");
    if (!root) return;
    const sections = Array.from(
      root.querySelectorAll<HTMLElement>("[data-reveal]"),
    );
    const observer = new IntersectionObserver(
      (entries) =>
        entries.forEach((entry) => {
          const el = entry.target as HTMLElement;
          el.classList.toggle("is-visible", entry.isIntersecting);
          if (entry.isIntersecting) el.classList.add("has-entered");
        }),
      { threshold: 0.08 },
    );
    const story = root.querySelector(".landing-story");
    const storyObserver = new IntersectionObserver(([entry]) => {
      entry.target.classList.toggle("is-offscreen", !entry.isIntersecting);
    });
    if (story) storyObserver.observe(story);
    root.classList.add("motion-ready");
    sections.forEach((el) => observer.observe(el));
    let raf = 0;
    const update = () => {
      raf = 0;
      sections.forEach((el) => {
        const rect = el.getBoundingClientRect();
        if (rect.bottom > 0 && rect.top < innerHeight)
          el.style.setProperty(
            "--section-progress",
            String(
              Math.max(
                0,
                Math.min(
                  1,
                  (innerHeight - rect.top) / (innerHeight + rect.height),
                ),
              ),
            ),
          );
      });
    };
    const schedule = () => {
      if (!raf) raf = requestAnimationFrame(update);
    };
    update();
    addEventListener("scroll", schedule, { passive: true });
    return () => {
      observer.disconnect();
      storyObserver.disconnect();
      cancelAnimationFrame(raf);
      removeEventListener("scroll", schedule);
      root.classList.remove("motion-ready");
    };
  }, []);
}
const operations = [
  {
    name: "Documents",
    index: "01",
    headline: "Structure, extracted.",
    description:
      "Turn documents into Markdown. Keep the text and tables, follow each PDF page, and carry the result into your next process.",
    format: "DOCUMENT → MARKDOWN + METADATA",
    formats: "PDF · DOCX · HTML · PPTX · XLSX",
    limits: "Default upload limit: 50 MB",
    href: "/docs/documents",
  },
  {
    name: "Audio & video",
    index: "02",
    headline: "Every word, reusable.",
    description:
      "Turn recordings into transcripts, timestamps and captions. Video transcription uses the audio track.",
    format: "AUDIO / VIDEO → TXT · JSON · VTT · SRT",
    formats: "MP3 · WAV · FLAC · M4A · MP4 · MOV · WEBM",
    limits: "Default transcription limits: audio 50 MB · video 500 MB",
    href: "/docs/transcription",
  },
  {
    name: "Images",
    index: "03",
    headline: "Read the pixels.",
    description:
      "Extract text and image regions with OCR, or generate image descriptions through the API.",
    format: "IMAGE → TEXT + REGIONS",
    formats: "PNG · JPEG · WEBP · BMP · GIF · TIFF",
    limits: "Defaults: 10 MB decoded image data · 50 million pixels",
    href: "/docs/images",
  },
];
export function LandingSections({ signedIn }: { signedIn: boolean }) {
  const { containerRef, pickerRef, operation, mode, selectOperation } =
    useOperationScroll(operations.length);
  const [cloud, setCloud] = useState(false);
  const [codeView, setCodeView] = useState<"request" | "response">("request");
  const [copied, setCopied] = useState(false);
  const [copyFailed, setCopyFailed] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(
        codeView === "request" ? example : resultExample,
      );
      setCopied(true);
      setCopyFailed(false);
    } catch {
      setCopyFailed(true);
    }
  }
  return (
    <>
      <section
        id="operacoes"
        className="landing-section landing-operations"
        data-reveal
      >
        <div className="section-index">
          <span>01 / CONVERT FOR AI. CONNECT YOUR DATA.</span>
          <span>ONE FILE OR A DATA PIPELINE</span>
        </div>
        <div className="section-intro">
          <h2>
            Convert for AI.
            <br />
            <span className="secondary-title">Connect your data.</span>
          </h2>
          <p>
            Start with a single conversion, or make it a step in your data
            pipeline. The same operations support both.
          </p>
        </div>
        <div className="landing-perspectives">
          <div>
            <h3>AI-ready conversion.</h3>
            <p>
              Turn documents, images and recordings into text your AI tools can
              use: Markdown, OCR results, transcripts and timestamps.
            </p>
          </div>
          <div>
            <h3>Data Engineering.</h3>
            <p>
              Build repeatable workflows around those conversions with API jobs,
              project context, document deduplication and page-level recovery.
            </p>
          </div>
        </div>
        <div
          className="operation-scroll"
          ref={containerRef}
          data-mode={mode}
          data-operation={operation}
        >
          <div className="operation-workspace">
            <div
              ref={pickerRef}
              className="operation-picker"
              role="group"
              aria-label="Choose an operation"
            >
              {operations.map((item, i) => (
                <button
                  key={item.name}
                  aria-label={item.name}
                  aria-pressed={operation === i}
                  onClick={() => selectOperation(i)}
                  aria-controls={`operation-panel-${i}`}
                >
                  <span>{item.index}</span>
                  {item.name}
                  <ArrowUpRight size={22} />
                </button>
              ))}
              <p>
                Scroll to explore.
                <br />
                Or choose an input.
              </p>
              <div className="operation-scroll-progress" aria-hidden="true">
                <span />
              </div>
            </div>
            {operations.map((active, index) => (
              <div
                className={`operation-canvas ${operation === index ? "is-active" : ""}`}
                key={active.name}
                id={`operation-panel-${index}`}
                aria-hidden={
                  mode === "pinned" && operation !== index ? true : undefined
                }
              >
                <div className="diagram-label">
                  <span>{active.format}</span>
                  <span>ILLUSTRATIVE WORKFLOW</span>
                </div>
                <OperationDiagram mode={index} />
                <pre className="operation-mobile-result">
                  <span>ILLUSTRATIVE OUTPUT</span>
                  {
                    [
                      "# Report\n| Item | Value |\n| Total | 42.00 |",
                      "00:00 → 00:03\nStart with the file.\n00:03 → 00:06\nBuild something new.",
                      "TOTAL 42.00\nExtracted text + image regions",
                    ][index]
                  }
                </pre>
                <div className="operation-caption">
                  <div>
                    <h3>{active.headline}</h3>
                    <p>{active.description}</p>
                    <div className="operation-formats">
                      <span>COMMON INPUT FORMATS</span>
                      <p>{active.formats}</p>
                      <small>{active.limits}</small>
                    </div>
                  </div>
                  <Link href={active.href} className="landing-text-link">
                    Explore
                    <ArrowUpRight size={18} />
                  </Link>
                </div>
              </div>
            ))}
          </div>
        </div>
        <p className="formats-docs">
          See the <Link href="/docs">documentation</Link> for the full format
          matrix, available operations and deployment limits.
        </p>
      </section>
      <section
        id="execucao"
        className="landing-section landing-compute"
        data-reveal
      >
        <div className="section-index">
          <span>02 / CONVERT, ORGANIZE AND RECOVER</span>
          <span>LOCAL ↔ OPTIONAL CLOUD</span>
        </div>
        <div className="compute-layout">
          <div>
            <h2>
              Conversions.
              <br />
              <span className="secondary-title">With control.</span>
            </h2>
            <p>
              Convert your files and keep the work organized with jobs,
              projects, page-level recovery and an API for your data workflows.
            </p>
            <div
              className="compute-toggle"
              role="group"
              aria-label="Illustrate audio execution"
            >
              <button aria-pressed={!cloud} onClick={() => setCloud(false)}>
                Local
              </button>
              <button aria-pressed={cloud} onClick={() => setCloud(true)}>
                Remote · audio
                <ArrowUpRight size={14} />
              </button>
            </div>
            <p className="compute-selection" aria-live="polite">
              {cloud
                ? "This audio example uses a configured remote transcription route. Documents and images stay with local workers."
                : "This audio example runs locally. Remote transcription is an optional processing route."}
            </p>
            <Link className="landing-text-link" href="/docs/compute">
              Explore execution
              <ArrowUpRight size={16} />
            </Link>
          </div>
          <ComputeDiagram cloud={cloud} />
        </div>
        <div className="pipeline-features">
          <div>
            <span>01 / REUSE</span>
            <h3>Document deduplication.</h3>
            <p>
              SHA-256 identifies repeat uploads within a project and reuses
              existing non-failed jobs.
            </p>
          </div>
          <div>
            <span>02 / RECOVER</span>
            <h3>Page-level recovery.</h3>
            <p>
              Track individual PDF pages and retry a failed page without
              resending the document.
            </p>
          </div>
          <div>
            <span>03 / ORGANIZE</span>
            <h3>Keep the context.</h3>
            <p>
              Projects, folders and tags keep conversion jobs connected to their
              source workload.
            </p>
          </div>
        </div>
      </section>
      <section id="api" className="landing-section landing-api" data-reveal>
        <div className="section-index">
          <span>03 / CONNECT YOUR DATA PIPELINE</span>
          <span>ONE API. YOUR WORKFLOW.</span>
        </div>
        <div className="api-heading">
          <h2>
            Convert. Track.
            <br />
            <span className="secondary-title">Retrieve.</span>
          </h2>
          <p>
            Use the conversion API from your orchestrator, script or
            application. Retrieve Markdown and metadata for the next step of
            your pipeline.
          </p>
        </div>
        <div className="api-workspace">
          <ol className="api-sequence">
            <li>
              <span>01</span>
              <strong>Send.</strong>
              <p>Authenticate with your API key and upload a document.</p>
            </li>
            <li>
              <span>02</span>
              <strong>Track.</strong>
              <p>Follow the job as it moves through processing.</p>
            </li>
            <li>
              <span>03</span>
              <strong>Use.</strong>
              <p>Retrieve the result and feed your downstream processing.</p>
            </li>
          </ol>
          <div className="landing-code">
            <div
              className="api-code-tabs"
              role="group"
              aria-label="API example"
            >
              <button
                aria-pressed={codeView === "request"}
                onClick={() => {
                  setCodeView("request");
                  setCopied(false);
                  setCopyFailed(false);
                }}
              >
                Upload request
              </button>
              <button
                aria-pressed={codeView === "response"}
                onClick={() => {
                  setCodeView("response");
                  setCopied(false);
                  setCopyFailed(false);
                }}
              >
                JSON result
              </button>
            </div>
            <div className="landing-code-bar">
              <span>
                <span className="status-dot" />
                {codeView === "request"
                  ? "POST /api/upload"
                  : "GET /api/jobs/{job_id}/result"}
              </span>
              <button
                onClick={copy}
                aria-label={
                  codeView === "request"
                    ? "Copy upload example"
                    : "Copy JSON example"
                }
              >
                {copied ? <Check size={16} /> : <Copy size={16} />}{" "}
                {copied ? "Copied" : "Copy"}
              </button>
            </div>
            <pre>
              <code>{codeView === "request" ? example : resultExample}</code>
            </pre>
            <p>
              {codeView === "request"
                ? "Authenticate with an API key, then poll the job until completed."
                : "Example values using the current document-result response contract."}
            </p>
            <p role="status">
              {copyFailed
                ? "Select the code above to copy it."
                : copied
                  ? "Example copied."
                  : ""}
            </p>
            <div className="api-reference-links">
              <a href="/api/docs">
                API reference
                <ArrowUpRight size={16} />
              </a>
              <a href="/api/openapi.json">
                OpenAPI JSON
                <ArrowUpRight size={16} />
              </a>
            </div>
          </div>
        </div>
        <SpectralLines variant="rail" />
      </section>
      <section
        id="data-lake"
        className="landing-section landing-lake"
        data-reveal
      >
        <div className="section-index">
          <span>04 / THE NEXT DESTINATION</span>
          <span className="roadmap-label">PLANNED · DATA LAKE DELIVERY</span>
        </div>
        <div className="section-intro">
          <h2>
            From conversion.
            <br />
            <span className="secondary-title">To your data lake.</span>
          </h2>
          <p>
            The next step for Ingestify: deliver converted data directly to your
            Data Lake. Choose a delivery adapter for MinIO, Amazon S3, Google
            Cloud Storage or Azure Blob.
          </p>
        </div>
        <LakeDeliveryDiagram />
        <div className="lake-detail">
          <p>
            <strong>Today:</strong> retrieve conversion results through the API.
            <br />
            <strong>Next:</strong> choose an adapter and deliver directly to
            your storage destination.
          </p>
          <p>
            Build downstream processing, quality checks and AI datasets around
            the data you ingest. Four planned adapters connect conversion to
            your storage: MinIO, Amazon S3, Google Cloud Storage (GCP) and Azure
            Blob.
          </p>
        </div>
        <div id="codigo-aberto" className="open-project">
          <div>
            <span className="landing-eyebrow">
              SELF-HOSTED. OPEN DEVELOPMENT.
            </span>
            <h3>
              Built for data and AI engineers.
              <br />
              Evolving with the community.
            </h3>
            <p>
              Follow the code and roadmap for an open source conversion and
              ingestion platform for AI Engineering.
            </p>
          </div>
          <div>
            <a href={GITHUB} className="landing-button">
              <Github size={18} />
              Explore the repository
              <ArrowUpRight size={18} />
            </a>
            <a className="license-link" href={`${GITHUB}#-licença`}>
              MIT license · declared in the README
              <ArrowUpRight size={14} />
            </a>
          </div>
        </div>
      </section>
      <section
        id="perguntas"
        className="landing-section landing-faq"
        data-reveal
      >
        <div>
          <p className="landing-eyebrow">A FEW THINGS TO KNOW</p>
          <h2>
            Before
            <br />
            you build.
          </h2>
        </div>
        <div>
          {faq.map(([q, a]) => (
            <details key={q}>
              <summary>
                {q}
                <span aria-hidden="true">+</span>
              </summary>
              <p>{a}</p>
            </details>
          ))}
        </div>
      </section>
      <section className="landing-section landing-final" data-reveal>
        <div className="final-invitation">
          <h2>
            Convert a file.
            <br />
            Build a pipeline.
          </h2>
          <div>
            <Link
              className="landing-button"
              href={signedIn ? "/dashboard" : "/login"}
            >
              Open workspace
              <ArrowRight size={18} />
            </Link>
            <Link className="landing-text-link" href="/docs">
              Read the docs
              <ArrowUpRight size={18} />
            </Link>
          </div>
        </div>
        <SpectralLines variant="rail" />
      </section>
    </>
  );
}
