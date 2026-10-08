import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  AudioLines,
  Building2,
  Check,
  Database,
  FileText,
  FolderTree,
  Image as ImageIcon,
  Layers,
} from "lucide-react";
import { Brand } from "@/components/brand";
import { PublicHeader } from "@/components/public-header";
import { GITHUB } from "@/components/landing/content";
import { DOCS_ORIGIN } from "../docs/config";
import styles from "./business.module.css";

export const dynamic = "error";
export const metadata: Metadata = {
  title: "Ingestify for Business — Usable data for your AI application",
  description:
    "Turn documents, images and recordings into content for your application. Organize projects and track jobs. Full Analysis and faces image results can be delivered to S3, MinIO, Google Cloud Storage and Azure Blob Storage.",
  alternates: { canonical: `${DOCS_ORIGIN}/business` },
  openGraph: {
    title: "Ingestify for Business",
    description:
      "From files to organized data. A processing platform for integrators, AI products and data teams.",
    url: `${DOCS_ORIGIN}/business`,
    type: "website",
    locale: "en_US",
  },
};

const audiences = [
  {
    number: "01",
    title: "Agencies and integrators",
    body: "Reuse your processing workflow across client projects. Organize each client's jobs and connect the results to your application.",
    example: "Prepare documents and recordings for your clients' applications.",
  },
  {
    number: "02",
    title: "AI products and agents",
    body: "Connect your application to the API to submit files, track jobs and retrieve text and metadata when they are ready.",
    example:
      "Give your agent access to the content of a PDF, an image or a conversation.",
  },
  {
    number: "03",
    title: "Data and automation teams",
    body: "Turn scattered files into results your team can retrieve and use through the API. For Full Analysis and faces images, configure delivery to your storage.",
    example:
      "Prepare data for queries, automation and analysis on your infrastructure.",
  },
];

const capabilities = [
  {
    icon: FileText,
    label: "DOCUMENTS",
    title: "Give content structure.",
    body: "Convert documents into Markdown and metadata. Track PDFs by page and retrieve available results.",
    href: "/docs/documents",
    link: "Document conversion",
  },
  {
    icon: AudioLines,
    label: "AUDIO AND VIDEO",
    title: "Turn conversations into data.",
    body: "Submit recordings through the API and get timestamped transcripts. Capture microphone audio in the interface and view results in the platform.",
    href: "/docs/transcription",
    link: "Recording transcription",
  },
  {
    icon: ImageIcon,
    label: "IMAGES",
    title: "More context from every image.",
    body: "Extract text, descriptions and regions. Use Full Analysis to explore available analyses and track each step.",
    href: "/docs/platform-images",
    link: "Use images and Full Analysis",
  },
];

const questions = [
  {
    title: "Do I need an API integration to get started?",
    answer:
      "Start with documents and images in the interface, or capture microphone audio on the Live screen. Audio and video file uploads are available through the API. Track jobs and view results in the platform. Access depends on your account permissions and deployment configuration.",
    href: "/docs/platform-start",
    link: "Get started with the platform",
  },
  {
    title: "Where are results delivered?",
    answer:
      "Retrieve documents, transcripts and image analyses through the platform and API. Automatic delivery to Amazon S3, MinIO, Google Cloud Storage and Azure Blob Storage is connected to Full Analysis and faces image analyses. Configure the destination bucket or container, partitioning and credentials for these modes. Your application can retrieve and store results from other operations through the API.",
    href: "/docs/platform-datalakes",
    link: "Configure storage",
  },
  {
    title: "Can I analyze all conversations with a customer?",
    answer:
      "Organize transcription jobs by project and folder. Your application retrieves transcripts through the API, associates each conversation with the customer and stores the data for aggregation. Your application or analysis tool performs the consolidated conversation analysis. Partitioning by customer_id and automatic JSONL delivery are available for Full Analysis and faces image analyses.",
    href: "/docs/platform-transcription",
    link: "Use transcripts",
  },
  {
    title: "Can I run this on my own infrastructure?",
    answer:
      "The repository supports deployment with Docker Compose and local workers. Choose processing routes and storage destinations that suit your environment. The data path depends on the providers and routes you enable.",
    href: "/docs/compute",
    link: "Explore processing options",
  },
];

function Pipeline() {
  return (
    <figure className={styles.pipeline} aria-labelledby="pipeline-caption">
      <div className={styles.pipelineHeading}>
        <span>ONE DATA WORKFLOW</span>
        <span className={styles.exampleBadge}>Illustrative example</span>
      </div>
      <div className={styles.sources}>
        <div>
          <FileText size={19} aria-hidden="true" />
          <span>contract.pdf</span>
        </div>
        <div>
          <AudioLines size={19} aria-hidden="true" />
          <span>conversation.mp3</span>
        </div>
        <div>
          <ImageIcon size={19} aria-hidden="true" />
          <span>image.png</span>
        </div>
      </div>
      <div className={styles.connector} aria-hidden="true">
        <ArrowDown size={21} />
      </div>
      <div className={styles.processor}>
        <div>
          <Layers size={23} aria-hidden="true" />
          <strong>Ingestify</strong>
          <span>Interface + API</span>
        </div>
        <ol>
          <li>
            <span>01</span> Receive and organize
          </li>
          <li>
            <span>02</span> Process and track
          </li>
          <li>
            <span>03</span> Make results available
          </li>
        </ol>
      </div>
      <div className={styles.connector} aria-hidden="true">
        <ArrowDown size={21} />
      </div>
      <div className={styles.output}>
        <Database size={24} aria-hidden="true" />
        <div>
          <strong>Results in the platform and API</strong>
          <p>Text · metadata · analyses</p>
        </div>
        <Check size={17} aria-hidden="true" />
      </div>
      <figcaption id="pipeline-caption">
        Your application retrieves the result. Full Analysis and faces images
        also support automatic delivery to your configured storage.
      </figcaption>
    </figure>
  );
}

export default function BusinessPage() {
  return (
    <div className={styles.page} lang="en">
      <a href="#business-content" className={styles.skip}>
        Skip to content
      </a>
      <PublicHeader />
      <main id="business-content">
        <section className={styles.hero}>
          <div className={styles.heroCopy}>
            <p className={styles.eyebrow}>INGESTIFY FOR BUSINESS</p>
            <h1>
              From files.
              <br />
              To data.
              <br />
              <span>To your product.</span>
            </h1>
            <p className={styles.heroDescription}>
              Documents, images and conversations in one processing workflow.
              Organized data for the AI application you are building.
            </p>
            <div className={styles.actions}>
              <Link href="/convert" className={styles.button}>
                Process a file <ArrowUpRight size={17} aria-hidden="true" />
              </Link>
              <a href="#para-quem" className={styles.textLink}>
                Explore use cases <ArrowDown size={16} aria-hidden="true" />
              </a>
            </div>
            <p className={styles.heroNote}>
              Documents and images in the interface. Recordings through the API.
              Microphone audio on the Live screen.
            </p>
          </div>
          <Pipeline />
        </section>

        <div
          className={styles.providerRail}
          aria-label="Storage destinations for Full Analysis and faces image analyses"
        >
          <span>AUTOMATIC DELIVERY · FULL ANALYSIS AND FACES IMAGES</span>
          <strong>Amazon S3</strong>
          <strong>MinIO</strong>
          <strong>Google Cloud Storage</strong>
          <strong>Azure Blob Storage</strong>
        </div>

        <section className={styles.section} id="para-quem">
          <div className={styles.sectionLabel}>
            <span>01 / FOR BUILDERS</span>
            <span>ONE WORKFLOW. DIFFERENT APPLICATIONS.</span>
          </div>
          <div className={styles.sectionIntro}>
            <h2>
              Your work starts
              <br />
              <span>with better data.</span>
            </h2>
            <p>
              Receiving a file is just the beginning. Prepare its content, track
              processing and connect the result to what your team delivers.
            </p>
          </div>
          <div className={styles.audiences}>
            {audiences.map((audience) => (
              <article key={audience.number}>
                <span>{audience.number}</span>
                <h3>{audience.title}</h3>
                <div>
                  <p>{audience.body}</p>
                  <p className={styles.audienceExample}>{audience.example}</p>
                </div>
                <ArrowUpRight size={22} aria-hidden="true" />
              </article>
            ))}
          </div>
        </section>

        <section
          className={`${styles.section} ${styles.dark}`}
          id="processamento"
        >
          <div className={styles.sectionLabel}>
            <span>02 / WHAT YOU CAN PROCESS</span>
            <span>CONTENT YOUR APPLICATION CAN USE</span>
          </div>
          <h2>
            Every format.
            <br />
            <span>A next step.</span>
          </h2>
          <div className={styles.capabilities}>
            {capabilities.map(({ icon: Icon, ...item }) => (
              <article key={item.label}>
                <Icon size={32} strokeWidth={1.5} aria-hidden="true" />
                <span>{item.label}</span>
                <h3>{item.title}</h3>
                <p>{item.body}</p>
                <Link href={item.href} className={styles.textLink}>
                  {item.link}
                  <ArrowUpRight size={16} aria-hidden="true" />
                </Link>
              </article>
            ))}
          </div>
        </section>

        <section className={styles.section} id="resultados-por-cliente">
          <div className={styles.sectionLabel}>
            <span>03 / ONE CUSTOMER, MANY RESULTS</span>
            <span>FULL ANALYSIS AND FACES IMAGES · PARTITIONED DELIVERY</span>
          </div>
          <div className={styles.customerGrid}>
            <div>
              <h2>
                Organize by customer.
                <br />
                <span>Prepare your analysis.</span>
              </h2>
              <p className={styles.sectionDescription}>
                One service photo today. Another next week. For Full Analysis
                and faces image analyses, use an identifier such as{" "}
                <code>customer_id</code> to organize results for the same
                customer in your storage.
              </p>
              <ul className={styles.checklist}>
                <li>
                  <Check size={17} aria-hidden="true" />
                  Define the strategy through the interface or API.
                </li>
                <li>
                  <Check size={17} aria-hidden="true" />
                  Include the identifier in the Full Analysis or faces
                  destination.
                </li>
                <li>
                  <Check size={17} aria-hidden="true" />
                  Combine customer, project and date in your partitioning.
                </li>
                <li>
                  <Check size={17} aria-hidden="true" />
                  Enable JSONL to prepare datasets you can query.
                </li>
              </ul>
              <Link
                href="/docs/platform-partitioning"
                className={styles.textLink}
              >
                See how to configure it{" "}
                <ArrowUpRight size={16} aria-hidden="true" />
              </Link>
            </div>
            <figure className={styles.customerExample}>
              <figcaption>
                <FolderTree size={18} aria-hidden="true" />
                <span>EXAMPLE · CUSTOMER ACME-042</span>
              </figcaption>
              <div className={styles.conversations}>
                <div>
                  <ImageIcon size={18} aria-hidden="true" />
                  <span>service-photo-01.jpg</span>
                  <small>Full Analysis · customer_id = acme-042</small>
                </div>
                <div>
                  <ImageIcon size={18} aria-hidden="true" />
                  <span>service-photo-02.jpg</span>
                  <small>Full Analysis · customer_id = acme-042</small>
                </div>
              </div>
              <div className={styles.datasetTitle}>
                <Database size={17} aria-hidden="true" />
                <strong>Organized dataset</strong>
                <span>JSONL</span>
              </div>
              <pre aria-label="Simplified example of a partitioned path">
                {
                  "datasets/\n  layout-…/\n    customer_id=acme-042/\n      year=2026/\n        month=10/\n          day=07/\n            <job_id>.jsonl"
                }
              </pre>
              <p>
                Simplified Full Analysis image layout. Each job delivers its own
                record; your application queries the data and analyzes the
                combined results.
              </p>
            </figure>
          </div>
        </section>

        <section className={`${styles.section} ${styles.soft}`} id="operacao">
          <div className={styles.sectionLabel}>
            <span>04 / FROM FIRST CONVERSION TO INTEGRATION</span>
            <span>VISIBILITY FOR OPERATORS</span>
          </div>
          <div className={styles.sectionIntro}>
            <h2>
              Start in the interface.
              <br />
              <span>Connect to your workflow.</span>
            </h2>
            <p>
              Validate results with real files and incorporate processing into
              your application when it makes sense.
            </p>
          </div>
          <div className={styles.operationGrid}>
            <article>
              <Building2 size={27} aria-hidden="true" />
              <h3>Use the platform</h3>
              <p>
                Create projects, submit documents and images, track progress and
                view results. For Full Analysis and faces images, select a
                storage connection for automatic delivery.
              </p>
              <Link href="/docs/platform-start" className={styles.textLink}>
                Usage guide <ArrowUpRight size={16} aria-hidden="true" />
              </Link>
            </article>
            <article>
              <Layers size={27} aria-hidden="true" />
              <h3>Integrate through the API</h3>
              <p>
                Authenticate your application, submit sources and save the job
                ID. Include project context, check status and retrieve results.
                Your application can store transcripts and other results in its
                chosen destination.
              </p>
              <Link href="/docs" className={styles.textLink}>
                API documentation <ArrowUpRight size={16} aria-hidden="true" />
              </Link>
            </article>
          </div>
          <div className={styles.operatingNotes}>
            <p>
              <strong>Organization.</strong> Projects, folders and tags help you
              find what has been processed.
            </p>
            <p>
              <strong>Tracking.</strong> Jobs show progress, results and
              failures to guide recovery.
            </p>
            <p>
              <strong>Infrastructure.</strong> Configure processing routes and
              destinations for your operating environment.
            </p>
          </div>
        </section>

        <section className={styles.section} id="duvidas">
          <div className={styles.sectionLabel}>
            <span>05 / BEFORE YOU START</span>
            <span>FROM USE TO OPERATION</span>
          </div>
          <div className={styles.faqGrid}>
            <h2>
              Practical
              <br />
              <span>questions.</span>
            </h2>
            <div>
              {questions.map((question) => (
                <details key={question.title}>
                  <summary>
                    {question.title}
                    <span aria-hidden="true">+</span>
                  </summary>
                  <p>{question.answer}</p>
                  <Link href={question.href} className={styles.textLink}>
                    {question.link}
                    <ArrowUpRight size={15} aria-hidden="true" />
                  </Link>
                </details>
              ))}
            </div>
          </div>
        </section>

        <section className={styles.closing}>
          <p className={styles.eyebrow}>YOUR NEXT STEP</p>
          <h2>
            Bring a real file.
            <br />
            <span>See where it can go.</span>
          </h2>
          <p>
            Start with one use case for your team. Validate the content and
            build your integration around the result.
          </p>
          <div className={styles.actions}>
            <Link href="/convert" className={styles.button}>
              Open the platform <ArrowRight size={17} aria-hidden="true" />
            </Link>
            <Link href="/agents" className={styles.textLink}>
              Ingestify for agents <ArrowUpRight size={16} aria-hidden="true" />
            </Link>
          </div>
        </section>
      </main>
      <footer className={styles.footer}>
        <Link href="/" aria-label="Ingestify home">
          <Brand />
        </Link>
        <p>Data Engineering + AI-ready conversion.</p>
        <nav aria-label="Footer links">
          <Link href="/agents">For agents</Link>
          <Link href="/docs">Docs</Link>
          <a href={GITHUB}>GitHub</a>
        </nav>
      </footer>
    </div>
  );
}
