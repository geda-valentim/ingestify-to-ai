"use client";

import { useEffect, useId, useRef, useState } from "react";
import { ArrowUpRight, Check, Copy, Pause, Play } from "lucide-react";
import Link from "next/link";
import styles from "./agents.module.css";

const steps = [
  {
    name: "Ingest",
    title: "Ask for the data. Get a job ID.",
    description:
      "Your tool uploads a file with its project context. Ingestify handles document conversion in the background.",
    route: "POST /api/upload",
    output: '{\n  "job_id": "example-job-id",\n  "status": "queued"\n}',
    docs: "/docs/documents",
    label: "JOB ACCEPTED",
    code: 'curl -X POST "https://dev.ingestify.ai/api/upload" \\\n  -H "X-API-Key: YOUR_API_KEY" \\\n  -F "file=@report.pdf" \\\n  -F "project=Research"',
  },
  {
    name: "Track",
    title: "Long jobs. Short tool calls.",
    description:
      "Keep the job ID in your workflow state. Check progress on a later call while your agent continues its work.",
    route: "GET /api/jobs/{job_id}",
    output:
      '{\n  "status": "processing",\n  "total_pages": 48,\n  "pages_completed": 32\n}',
    docs: "/docs/job-status",
    label: "PROGRESS AVAILABLE",
    code: 'curl "https://dev.ingestify.ai/api/jobs/JOB_ID" \\\n  -H "X-API-Key: YOUR_API_KEY"',
  },
  {
    name: "Read",
    title: "Bring back the pages that matter.",
    description:
      "Retrieve a converted PDF page instead of loading the whole document into the agent’s context. Read the full result when you need it.",
    route: "GET /api/jobs/{job_id}/pages/4/result",
    output:
      "# Quarterly report\n\n| Metric | Value |\n| --- | --- |\n| Revenue | 42.0 |",
    docs: "/docs/pdf-pages",
    label: "PAGE 4 · MARKDOWN",
    code: 'curl "https://dev.ingestify.ai/api/jobs/JOB_ID/pages/4/result" \\\n  -H "X-API-Key: YOUR_API_KEY"',
  },
  {
    name: "Search",
    title: "Find the work already done.",
    description:
      "Search indexed content, inspect matching job previews and retrieve the results your agent needs next.",
    route: "GET /api/search?query=quarterly",
    output:
      '{\n  "query": "quarterly",\n  "total": 1,\n  "results": [\n    { "filename": "report.pdf",\n      "preview": "Quarterly report…" }\n  ]\n}',
    docs: "/docs/introduction",
    label: "INDEXED CONTENT",
    code: 'curl --get "https://dev.ingestify.ai/api/search" \\\n  -H "X-API-Key: YOUR_API_KEY" \\\n  --data-urlencode "query=quarterly"',
  },
];

export function AgentWorkflow() {
  const container = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [active, setActive] = useState(0);
  useEffect(() => {
    if (!container.current) return;
    const observer = new IntersectionObserver(([entry]) =>
      setVisible(entry.isIntersecting),
    );
    observer.observe(container.current);
    return () => observer.disconnect();
  }, []);
  const [paused, setPaused] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  const id = useId();
  const step = steps[active];
  async function copy() {
    try {
      await navigator.clipboard.writeText(step.code);
      setCopied(step.name);
    } catch {
      setCopied(null);
    }
  }
  return (
    <div
      ref={container}
      className={styles.workflow}
      data-paused={paused}
      data-visible={visible}
    >
      <div className={styles.workflowTop}>
        <div
          role="group"
          aria-label="Explore the agent workflow"
          className={styles.steps}
        >
          {steps.map((item, index) => (
            <button
              key={item.name}
              type="button"
              aria-pressed={active === index}
              aria-controls="agent-workflow-panel"
              onClick={() => {
                setActive(index);
                setCopied(null);
              }}
            >
              <span>0{index + 1}</span>
              {item.name}
            </button>
          ))}
        </div>
        <button
          className={styles.motion}
          type="button"
          aria-label={paused ? "Resume diagram motion" : "Pause diagram motion"}
          aria-pressed={paused}
          onClick={() => setPaused(!paused)}
        >
          {paused ? <Play size={14} /> : <Pause size={14} />}
        </button>
      </div>
      <div className={styles.workflowBody} id="agent-workflow-panel">
        <div className={styles.workflowStory}>
          <svg
            viewBox="0 0 620 180"
            className={styles.diagram}
            aria-hidden="true"
          >
            <defs>
              <linearGradient id={id}>
                <stop stopColor="#f06b91" />
                <stop offset=".25" stopColor="#eeb94a" />
                <stop offset=".5" stopColor="#6dc7ad" />
                <stop offset=".75" stopColor="#6e9fe9" />
                <stop offset="1" stopColor="#b889df" />
              </linearGradient>
              <radialGradient id={`${id}-glass`} cx=".32" cy=".2" r=".9">
                <stop stopColor="white" />
                <stop offset=".65" stopColor="#f2f2f2" />
                <stop offset="1" stopColor="#bbb" />
              </radialGradient>
            </defs>
            <path d="M70 90H550" stroke="#e5e5e5" fill="none" />
            <path
              d="M70 90H550"
              stroke={`url(#${id})`}
              strokeWidth="2"
              className={styles.signal}
              fill="none"
            />
            {[70, 230, 390, 550].map((x, index) => (
              <g key={x}>
                <circle
                  cx={x}
                  cy="90"
                  r={active === index ? 40 : 28}
                  fill={active === index ? `url(#${id}-glass)` : "white"}
                  stroke={active === index ? "#333" : "#ddd"}
                />
                <text
                  x={x}
                  y="96"
                  textAnchor="middle"
                  fontSize="17"
                  fontFamily="monospace"
                  fill="#111"
                >
                  0{index + 1}
                </text>
              </g>
            ))}
          </svg>
          <div aria-live="polite" aria-atomic="true">
            <span className={styles.eyebrow}>{step.label}</span>
            <h3>{step.title}</h3>
            <p>{step.description}</p>
          </div>
          <Link href={step.docs} className={styles.textLink}>
            Explore the API <ArrowUpRight size={16} />
          </Link>
        </div>
        <div className={styles.toolWindow}>
          <div className={styles.windowBar}>
            <span>ILLUSTRATIVE TOOL EXCHANGE</span>
            <span>HTTP</span>
          </div>
          <code className={styles.route}>{step.route}</code>
          <pre className={styles.output}>{step.output}</pre>
          <div className={styles.request}>
            <div className={styles.windowBar}>
              <span>REQUEST EXAMPLE</span>
              <button
                type="button"
                onClick={copy}
                aria-label="Copy agent request"
              >
                {copied === step.name ? (
                  <Check size={15} />
                ) : (
                  <Copy size={15} />
                )}
                <span>{copied === step.name ? "Copied" : "Copy"}</span>
              </button>
            </div>
            <pre>{step.code}</pre>
          </div>
        </div>
      </div>
      <p className={styles.demoNote}>
        Example responses are abbreviated. No files are uploaded and no jobs are
        created by this preview.
      </p>
    </div>
  );
}
