"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowUpRight, ArrowRight, Github, Check, Copy } from "lucide-react";
import { GITHUB, example, faq } from "./content";
import {
  OperationDiagram,
  ComputeDiagram,
  SpectralLines,
  Wordmark,
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
    format: "PDF / DOCUMENT → MARKDOWN",
    href: "/docs?lang=en#documentos",
  },
  {
    name: "Audio & video",
    index: "02",
    headline: "Every word, reusable.",
    description:
      "Turn recordings into transcripts, timestamps and captions. Video transcription uses the audio track.",
    format: "AUDIO / VIDEO → TXT · JSON · VTT",
    href: "/docs?lang=en#transcribe",
  },
  {
    name: "Images",
    index: "03",
    headline: "Read the pixels.",
    description:
      "Extract text and image regions with OCR, or generate image descriptions through the API.",
    format: "IMAGE → TEXT + REGIONS",
    href: "/docs?lang=en#imagens",
  },
];
export function LandingSections({ signedIn }: { signedIn: boolean }) {
  const [operation, setOperation] = useState(0);
  const [cloud, setCloud] = useState(false);
  const [copied, setCopied] = useState(false);
  const [copyFailed, setCopyFailed] = useState(false);
  const active = operations[operation];
  async function copy() {
    try {
      await navigator.clipboard.writeText(example);
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
          <span>01 / THE TRANSFORMATION LAYER</span>
          <span>FILES → USEFUL INFORMATION</span>
        </div>
        <div className="section-intro">
          <h2>
            Different inputs.
            <br />
            <span className="outline-text">One direction.</span>
          </h2>
          <p>
            From the files you already have
            <br />
            to the information you need.
          </p>
        </div>
        <div className="operation-workspace">
          <div
            className="operation-picker"
            role="group"
            aria-label="Choose an operation"
          >
            {operations.map((item, i) => (
              <button
                key={item.name}
                aria-label={item.name}
                aria-pressed={operation === i}
                onClick={() => setOperation(i)}
              >
                <span>{item.index}</span>
                {item.name}
                <ArrowUpRight size={22} />
              </button>
            ))}
            <p>
              Choose an input.
              <br />
              Follow the transformation.
            </p>
          </div>
          <div className="operation-canvas" key={operation}>
            <div className="diagram-label">
              <span>{active.format}</span>
              <span>ILLUSTRATIVE WORKFLOW</span>
            </div>
            <OperationDiagram mode={operation} />
            <pre className="operation-mobile-result">
              <span>ILLUSTRATIVE OUTPUT</span>
              {
                [
                  "# Report\n| Item | Value |\n| Total | 42.00 |",
                  "00:00 → 00:03\nStart with the file.\n00:03 → 00:06\nBuild something new.",
                  "TOTAL 42.00\nExtracted text + image regions",
                ][operation]
              }
            </pre>
            <div className="operation-caption">
              <div>
                <h3>{active.headline}</h3>
                <p>{active.description}</p>
              </div>
              <Link href={active.href} className="landing-text-link">
                Explore
                <ArrowUpRight size={18} />
              </Link>
            </div>
          </div>
        </div>
        <div className="pilot-strip">
          <span className="status-dot" />
          <strong>Live microphone / Pilot</strong>
          <span>Requires operator activation and GPU capacity.</span>
          <Link href="/docs?lang=en#microfone-live">
            Explore the pilot
            <ArrowUpRight size={14} />
          </Link>
        </div>
      </section>
      <section
        id="execucao"
        className="landing-section landing-compute"
        data-reveal
      >
        <div className="section-index">
          <span>02 / EXECUTION, ON YOUR TERMS</span>
          <span>LOCAL ↔ OPTIONAL CLOUD</span>
        </div>
        <div className="compute-layout">
          <div>
            <h2>
              Your compute.
              <br />
              <span className="outline-text">Your call.</span>
            </h2>
            <p>
              Choose the resources behind the operation. Configure execution
              around your capacity, priority and budget.
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
                Modal · audio
                <ArrowUpRight size={14} />
              </button>
            </div>
            <p className="compute-selection" aria-live="polite">
              {cloud
                ? "This audio example runs on Modal. Documents and images stay with local workers."
                : "This audio example runs locally. Modal is an optional route for transcription."}
            </p>
            <Link className="landing-text-link" href="/docs?lang=en#compute">
              Explore execution
              <ArrowUpRight size={16} />
            </Link>
          </div>
          <ComputeDiagram cloud={cloud} />
        </div>
        <div className="compute-footnote">
          <span>Know where your data goes.</span>
          <p>
            Local workers do not guarantee local-only data handling. The engine
            and provider you configure also determine the destination.
          </p>
        </div>
      </section>
      <section id="api" className="landing-section landing-api" data-reveal>
        <div className="section-index">
          <span>03 / CONNECT THE DOTS</span>
          <span>ONE API. YOUR WORKFLOW.</span>
        </div>
        <div className="api-heading">
          <h2>
            Build it into
            <br />
            <span className="outline-text">what comes next.</span>
          </h2>
          <p>
            Upload a file. Track the job. Put the result to work.
            <br />
            The same operations, inside your application.
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
              <p>Bring the completed result into your application.</p>
            </li>
          </ol>
          <div className="landing-code">
            <div className="landing-code-bar">
              <span>
                <span className="status-dot" />
                POST /upload
              </span>
              <button onClick={copy} aria-label="Copy upload example">
                {copied ? <Check size={16} /> : <Copy size={16} />}{" "}
                {copied ? "Copied" : "Copy"}
              </button>
            </div>
            <pre>
              <code>{example}</code>
            </pre>
            <p>
              Development environment. Requires a valid account and API key.
            </p>
            <p role="status">
              {copyFailed
                ? "Select the code above to copy it."
                : copied
                  ? "Example copied."
                  : ""}
            </p>
            <a href="/api/docs">
              API reference
              <ArrowUpRight size={16} />
            </a>
          </div>
        </div>
        <SpectralLines variant="rail" />
      </section>
      <section
        id="codigo-aberto"
        className="landing-section landing-community"
        data-reveal
      >
        <SpectralLines variant="orbit" />
        <div className="section-index">
          <span>04 / AN OPEN DIRECTION</span>
          <span>PLANNED EVOLUTION</span>
        </div>
        <div className="community-copy">
          <p className="landing-eyebrow">
            START WITH AN OPERATION. BUILD A POSSIBILITY.
          </p>
          <h2>
            Made to connect.
            <br />
            <span className="outline-text">Built to evolve.</span>
          </h2>
          <p>
            Our vision is an open source platform for everyday AI
            transformations. More machines. Reusable operations. A project you
            can help shape.
          </p>
          <a href={GITHUB} className="landing-button">
            <Github size={18} />
            Explore the code
            <ArrowUpRight size={18} />
          </a>
          <p className="landing-note">
            General distributed execution and operation composition are planned
            capabilities.
          </p>
        </div>
        <div className="community-coordinates">
          <span>LOCAL / DISTRIBUTED / OPEN</span>
          <span>FOLLOW THE PROJECT ON GITHUB ↗</span>
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
            The file is
            <br />
            just the beginning.
          </h2>
          <div>
            <Link
              className="landing-button"
              href={signedIn ? "/dashboard" : "/login"}
            >
              Start building
              <ArrowRight size={18} />
            </Link>
            <Link className="landing-text-link" href="/docs?lang=en">
              Read the docs
              <ArrowUpRight size={18} />
            </Link>
          </div>
        </div>
        <Wordmark />
        <SpectralLines variant="rail" />
      </section>
    </>
  );
}
