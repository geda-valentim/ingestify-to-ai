import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  AudioLines,
  FileText,
  Github,
  Image as ImageIcon,
  Layers,
} from "lucide-react";
import { Brand } from "@/components/brand";
import { PublicHeader } from "@/components/public-header";
import { GITHUB } from "@/components/landing/content";
import { DOCS_ORIGIN } from "../docs/config";
import { AgentWorkflow } from "./workflow";
import styles from "./agents.module.css";

export const dynamic = "error";
export const metadata: Metadata = {
  title: "Ingestify for Agents — Turn files into usable context",
  description:
    "Connect AI agents to document conversion, transcription, OCR and indexed content through one API. Build on asynchronous jobs, project context and Data Lake delivery.",
  alternates: { canonical: `${DOCS_ORIGIN}/agents` },
  openGraph: {
    title: "Give your agents usable data. | Ingestify",
    description:
      "One ingestion platform for agent context and Data Engineering workflows.",
    url: `${DOCS_ORIGIN}/agents`,
    type: "website",
  },
};

const benefits = [
  [
    "01",
    "Work beyond a single tool call.",
    "Document conversion and file transcription return a job ID. Your application tracks progress and resumes when the data is ready.",
  ],
  [
    "02",
    "Keep the context focused.",
    "Retrieve individual PDF page results. Give the agent relevant material without filling its context with the entire document.",
  ],
  [
    "03",
    "Reuse what you have ingested.",
    "Document deduplication within a project and search over indexed content help your workflow find and reuse existing work.",
  ],
  [
    "04",
    "Keep the source in context.",
    "Organize jobs by project, folder and tags. Carry source and processing metadata into the next step of your workflow.",
  ],
  [
    "05",
    "Recover at the right level.",
    "Follow PDF processing by page and retry failed pages. Keep recovery in the data pipeline instead of asking the agent to start over.",
  ],
  [
    "06",
    "Operate the compute behind it.",
    "Configure local workers, supported remote processing and routing budgets. Your agent calls the API; your team controls how work is executed.",
  ],
];
const tools = [
  ["Ingest a document", "POST /upload", "/docs/documents"],
  ["Transcribe a recording", "POST /transcribe", "/docs/transcription"],
  ["Extract text from an image", "POST /images/ocr", "/docs/images"],
  ["Check a job", "GET /jobs/{job_id}", "/docs/job-status"],
  [
    "Read a PDF page",
    "GET /jobs/{job_id}/pages/{page}/result",
    "/docs/pdf-pages",
  ],
  ["Search indexed content", "GET /search?query=…", "/api/openapi.json"],
];
const faq = [
  [
    "How does my agent connect?",
    "Define HTTP tools in your agent application that call the Ingestify API using X-API-Key. Upload files from your application, retain the returned job ID, check status and retrieve results. The agent framework and reasoning model remain your choice.",
  ],
  [
    "Can I use MCP?",
    "You can wrap the HTTP API in your own MCP adapter. A native Ingestify MCP server is not included today. The same ingest, status, read and search operations are the foundation for that integration.",
  ],
  [
    "Does a project-bound API key isolate an agent?",
    "A bound key supplies a default project for uploads. Access still follows the user account’s permissions; project binding is not a separate authorization boundary. Design agent access around those account permissions.",
  ],
  [
    "Is this a vector database or a complete RAG system?",
    "Ingestify prepares source data and exposes conversion results, metadata and search over indexed content. Your downstream application handles chunking, embeddings, retrieval strategy and agent reasoning.",
  ],
  [
    "Can the data stay on infrastructure I control?",
    "You can self-host Ingestify and run local workers. Configure processing routes and storage destinations appropriate for your deployment; data sent to an external provider follows the route you enable.",
  ],
];

export default function AgentsPage() {
  return (
    <div className={styles.page} lang="en">
      <a href="#agents-content" className={styles.skip}>
        Skip to content
      </a>
      <PublicHeader />
      <main id="agents-content">
        <section className={styles.hero}>
          <p className={styles.eyebrow}>
            FOR AGENTS · BUILT ON DATA ENGINEERING
          </p>
          <h1>
            Give your agents
            <br />
            <span>usable data.</span>
          </h1>
          <div className={styles.heroBottom}>
            <p>
              Turn documents, recordings and images into context your agents can
              use. One API connects conversion, processing state and results to
              the rest of your data workflow.
            </p>
            <div className={styles.actions}>
              <a href="#workflow" className={styles.button}>
                Explore the workflow <ArrowDown size={17} />
              </a>
              <Link href="/docs" className={styles.textLink}>
                Read the documentation <ArrowUpRight size={16} />
              </Link>
            </div>
          </div>
          <div className={styles.inputRail}>
            <div>
              <FileText size={22} />
              <strong>Documents</strong>
              <span>Markdown + metadata</span>
            </div>
            <div>
              <AudioLines size={22} />
              <strong>Audio & video</strong>
              <span>Transcripts + timestamps</span>
            </div>
            <div>
              <ImageIcon size={22} />
              <strong>Images</strong>
              <span>OCR + descriptions</span>
            </div>
          </div>
        </section>
        <section className={styles.section} id="workflow">
          <div className={styles.sectionLabel}>
            <span>01 / THE AGENT WORKFLOW</span>
            <span>ONE API. YOUR TOOLS.</span>
          </div>
          <div className={styles.sectionIntro}>
            <h2>
              From a file.
              <br />
              <span>To the next decision.</span>
            </h2>
            <p>
              Your agent asks for information. Ingestify prepares the source
              data and makes the processing state visible. Connect these
              operations as tools in your application.
            </p>
          </div>
          <AgentWorkflow />
          <ol className={styles.processSummary}>
            <li>
              <span>01 / INGEST</span>Send a source with project context.
            </li>
            <li>
              <span>02 / TRACK</span>Retain the job ID and check progress.
            </li>
            <li>
              <span>03 / READ</span>Retrieve the result or a specific PDF page.
            </li>
            <li>
              <span>04 / SEARCH</span>Find relevant content already indexed.
            </li>
          </ol>
        </section>
        <section className={`${styles.section} ${styles.dark}`}>
          <div className={styles.sectionLabel}>
            <span>02 / THE OPERATIONAL LAYER</span>
            <span>YOUR AGENT REASONS. YOUR PIPELINE RUNS.</span>
          </div>
          <h2>
            Keep the agent focused.
            <br />
            <span>Keep the data under control.</span>
          </h2>
          <div className={styles.benefits}>
            {benefits.map(([number, title, body]) => (
              <article key={number}>
                <span>{number}</span>
                <div>
                  <h3>{title}</h3>
                  <p>{body}</p>
                </div>
              </article>
            ))}
          </div>
        </section>
        <section className={styles.section} id="data-platform">
          <div className={styles.sectionLabel}>
            <span>03 / BEYOND THE CONTEXT WINDOW</span>
            <span>DATA ENGINEERING + AI ENGINEERING</span>
          </div>
          <div className={styles.sectionIntro}>
            <h2>
              A useful answer.
              <br />
              <span>A reusable data asset.</span>
            </h2>
            <p>
              Use conversion results in the agent now. Deliver them to your
              storage for downstream processing, analytics and future AI
              workflows.
            </p>
          </div>
          <div className={styles.destinations}>
            <div className={styles.sourceNode}>
              <span className={styles.glassMark}>
                <Layers size={42} />
              </span>
              <h3>Ingestify</h3>
              <p>
                Converted content
                <br />+ source metadata
              </p>
            </div>
            <svg
              className={styles.fork}
              viewBox="0 0 200 300"
              preserveAspectRatio="none"
              aria-hidden="true"
            >
              <defs>
                <linearGradient id="agent-destination-spectrum">
                  <stop stopColor="#f06b91" />
                  <stop offset=".3" stopColor="#eeb94a" />
                  <stop offset=".55" stopColor="#6dc7ad" />
                  <stop offset=".8" stopColor="#6e9fe9" />
                  <stop offset="1" stopColor="#b889df" />
                </linearGradient>
              </defs>
              <path
                d="M0 150H50C110 150 90 75 140 75H200M50 150C110 150 90 225 140 225H200"
                fill="none"
                stroke="url(#agent-destination-spectrum)"
                strokeWidth="2"
              />
            </svg>
            <div className={styles.destinationList}>
              <article>
                <span className={styles.eyebrow}>FOR THE AGENT</span>
                <h3>Context to work with.</h3>
                <p>Markdown, transcripts, OCR results and job metadata.</p>
              </article>
              <article>
                <span className={styles.eyebrow}>FOR THE DATA PLATFORM</span>
                <h3>A destination you choose.</h3>
                <p>
                  Configure a delivery connection and keep the output in your
                  bucket or container.
                </p>
                <div className={styles.providers}>
                  {[
                    "MinIO",
                    "Amazon S3",
                    "Google Cloud Storage",
                    "Azure Blob",
                  ].map((name) => (
                    <span key={name}>{name}</span>
                  ))}
                </div>
              </article>
            </div>
          </div>
          <Link className={styles.textLink} href="/docs/datalakes">
            Explore Data Lake delivery <ArrowUpRight size={16} />
          </Link>
        </section>
        <section className={`${styles.section} ${styles.useCases}`}>
          <div className={styles.sectionLabel}>
            <span>04 / PUT THE DATA TO WORK</span>
            <span>EXAMPLE WORKFLOWS</span>
          </div>
          <div className={styles.useCaseGrid}>
            <article>
              <span>RESEARCH AGENTS</span>
              <h3>Read the evidence.</h3>
              <p>
                Convert a report, locate relevant material and read individual
                PDF pages before preparing a source-grounded response.
              </p>
              <Link href="/docs/pdf-pages">
                Explore page results <ArrowRight size={16} />
              </Link>
            </article>
            <article>
              <span>MEETING WORKFLOWS</span>
              <h3>Keep the conversation.</h3>
              <p>
                Transcribe a recording with timestamps. Pass the text to your
                agent to draft decisions, action items or a searchable meeting
                record.
              </p>
              <Link href="/docs/transcription">
                Explore transcription <ArrowRight size={16} />
              </Link>
            </article>
            <article>
              <span>DOCUMENT OPERATIONS</span>
              <h3>Build on every input.</h3>
              <p>
                Extract text from files and images. Let your application
                validate the output and route it to the project or downstream
                process it belongs to.
              </p>
              <Link href="/docs/images">
                Explore image operations <ArrowRight size={16} />
              </Link>
            </article>
          </div>
        </section>
        <section className={styles.section} id="integration">
          <div className={styles.sectionLabel}>
            <span>05 / CONNECT YOUR AGENT</span>
            <span>HTTP API · SELF-HOSTED</span>
          </div>
          <div className={styles.sectionIntro}>
            <h2>
              Your framework.
              <br />
              <span>A standard HTTP contract.</span>
            </h2>
            <p>
              Define the tools your agent needs around the API. Keep credentials
              in your application and share the returned content with the model.
            </p>
          </div>
          <div className={styles.toolTable}>
            {tools.map(([title, path, href]) => (
              <a href={href} key={title}>
                <span>{title}</span>
                <code>{path}</code>
                <ArrowUpRight size={18} />
              </a>
            ))}
          </div>
          <p className={styles.integrationNote}>
            Routes shown relative to <code>/api</code>. Upload local files from
            the tool runtime that can access them. Document conversion and file
            transcription use asynchronous jobs; image operations return their
            result directly.
          </p>
          <div className={styles.integrationActions}>
            <Link href="/docs/authentication" className={styles.button}>
              Connect with an API key <ArrowUpRight size={16} />
            </Link>
            <a href="/api/openapi.json" className={styles.textLink}>
              Inspect the OpenAPI schema <ArrowUpRight size={16} />
            </a>
          </div>
        </section>
        <section className={`${styles.section} ${styles.faq}`}>
          <div>
            <span className={styles.eyebrow}>BEFORE YOU BUILD</span>
            <h2>
              A few practical
              <br />
              <span>answers.</span>
            </h2>
          </div>
          <div>
            {faq.map(([question, answer]) => (
              <details key={question}>
                <summary>
                  {question}
                  <span aria-hidden="true">+</span>
                </summary>
                <p>{answer}</p>
              </details>
            ))}
          </div>
        </section>
        <section className={`${styles.section} ${styles.final}`}>
          <span className={styles.eyebrow}>
            START WITH ONE FILE. BUILD FROM THERE.
          </span>
          <h2>
            Your agent’s next move
            <br />
            <span>starts with better data.</span>
          </h2>
          <div className={styles.actions}>
            <Link href="/docs" className={styles.button}>
              Start building <ArrowUpRight size={17} />
            </Link>
            <a href={GITHUB} className={styles.textLink}>
              Explore the code <Github size={18} />
            </a>
          </div>
        </section>
      </main>
      <footer className={styles.footer}>
        <Link href="/" aria-label="Ingestify home">
          <Brand />
        </Link>
        <p>Data Engineering + AI-ready conversion.</p>
        <nav aria-label="Footer links">
          <Link href="/">Platform</Link>
          <Link href="/business">Business</Link>
          <Link href="/docs">Docs</Link>
          <a href={GITHUB}>GitHub</a>
          <Link href="/login">Sign in</Link>
        </nav>
      </footer>
    </div>
  );
}
