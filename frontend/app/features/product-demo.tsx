"use client";

import { useId, useState, type CSSProperties } from "react";
import {
  ArrowDown,
  ArrowUpRight,
  AudioLines,
  Check,
  FileText,
  Image as ImageIcon,
  Layers,
  Sparkles,
} from "lucide-react";
import type { Feature } from "./content";
import styles from "./features.module.css";

const DEMOS = {
  documents: {
    file: "quarterly-report.pdf",
    label: "Document conversion",
    modes: ["Markdown", "Tables", "Pages"],
    results: [
      "# Quarterly report\n\nRevenue grew across all three regions.\n\n## Performance by region\n| Region | Revenue |\n| --- | --- |\n| Americas | $42,000 |",
      "| Region   | Revenue | Growth |\n| -------- | ------- | ------ |\n| Americas | $42,000 | +18%   |\n| Europe   | $31,000 | +12%   |\n| Asia     | $27,000 | +24%   |",
      "Page 01  →  completed  →  markdown\nPage 02  →  completed  →  markdown\nPage 03  →  completed  →  markdown\n\nMerged result + metadata + assets[]",
    ],
  },
  "audio-video": {
    file: "team-conversation.mp3",
    label: "Audio & video transcription",
    modes: ["Transcript", "Captions", "JSON"],
    results: [
      "[00:00 → 00:04]\nLet’s turn our recordings into knowledge.\n\n[00:04 → 00:08]\nEvery conversation has something to offer.",
      "1\n00:00:00,000 --> 00:00:04,000\nLet’s turn our recordings into knowledge.\n\n2\n00:00:04,000 --> 00:00:08,000\nEvery conversation has something to offer.",
      '{ "segments": [\n  { "start": 0.0, "end": 4.0,\n    "text": "Let’s turn our recordings into knowledge." },\n  { "start": 4.0, "end": 8.0,\n    "text": "Every conversation has something to offer." }\n] }',
    ],
  },
  images: {
    file: "product-still-life.png",
    label: "Image analysis",
    modes: ["Objects", "OCR", "Caption"],
    results: [
      "bottle  →  [124, 64, 229, 252]\nplant   →  [294, 48, 425, 248]\ncard    →  [42, 155, 139, 246]\n\nDetected objects + bounding boxes",
      'Text: "BOTANIC / DAILY CARE / 250 ml"\n\nOutput: extracted text + image regions\nTask: <OCR_WITH_REGION>',
      "A bottle sits on a light pedestal\nnext to a small potted plant and a card,\nagainst a warm studio background.\n\nTask: <DETAILED_CAPTION>",
    ],
  },
};

/** Exact spectral accents from the home, over a monochrome interface. */
function SpectrumGradient({ id }: { id: string }) {
  return (
    <linearGradient id={id} x1="0" x2="1">
      <stop stopColor="#f06b91" />
      <stop offset=".23" stopColor="#eeb94a" />
      <stop offset=".48" stopColor="#6dc7ad" />
      <stop offset=".73" stopColor="#6e9fe9" />
      <stop offset="1" stopColor="#b889df" />
    </linearGradient>
  );
}

function DocumentArtwork({ id, mode }: { id: string; mode: number }) {
  return (
    <>
      <defs>
        <SpectrumGradient id={`${id}-spectrum`} />
        <linearGradient id={`${id}-paper`} x2="1" y2="1">
          <stop stopColor="#fff" />
          <stop offset="1" stopColor="#ededed" />
        </linearGradient>
        <linearGradient id={`${id}-scan`} x2="0" y2="1">
          <stop stopColor="#b0b0b0" stopOpacity="0" />
          <stop offset="1" stopColor="#b0b0b0" stopOpacity=".28" />
        </linearGradient>
      </defs>
      <circle
        cx="245"
        cy="155"
        r="118"
        fill="none"
        stroke="currentColor"
        opacity=".15"
      />
      <circle
        cx="245"
        cy="155"
        r="147"
        fill="none"
        stroke="currentColor"
        opacity=".08"
        strokeDasharray="4 8"
      />
      <g className={styles.floatingSheet}>
        <rect
          x="138"
          y="43"
          width="210"
          height="238"
          rx="8"
          fill="#939393"
          opacity=".22"
          transform="rotate(9 243 162)"
        />
        <rect
          x="138"
          y="37"
          width="210"
          height="238"
          rx="8"
          fill="#bcbcbc"
          opacity=".4"
          transform="rotate(-6 243 156)"
        />
        <rect
          x="138"
          y="32"
          width="210"
          height="238"
          rx="8"
          fill={`url(#${id}-paper)`}
        />
        <rect x="160" y="53" width="25" height="5" rx="2" fill="#7c7c7c" />
        <text x="160" y="82" fill="#2e2e2e" fontSize="16" fontWeight="600">
          Quarterly report
        </text>
        <text x="160" y="99" fill="#818181" fontSize="8" letterSpacing="1.5">
          PERFORMANCE OVERVIEW
        </text>
        {[118, 126, 134].map((y, i) => (
          <rect
            key={y}
            x="160"
            y={y}
            width={i === 2 ? 123 : 166}
            height="3"
            rx="1.5"
            fill="#c9c9c9"
          />
        ))}
        <rect
          x="160"
          y="150"
          width="166"
          height="72"
          rx="3"
          fill="#f4f4f4"
          stroke="#d8d8d8"
        />
        <path
          d="M160 170H326M160 188H326M160 205H326M230 150V222M282 150V222"
          stroke="#d8d8d8"
        />
        <text x="170" y="163" fill="#5e5e5e" fontSize="7">
          Region
        </text>
        <text x="238" y="163" fill="#5e5e5e" fontSize="7">
          Revenue
        </text>
        {[182, 199, 216].map((y, i) => (
          <g key={y}>
            <text x="170" y={y} fill="#5e5e5e" fontSize="7">
              {["Americas", "Europe", "Asia"][i]}
            </text>
            <text x="238" y={y} fill="#5e5e5e" fontSize="7">
              {["$42,000", "$31,000", "$27,000"][i]}
            </text>
            <rect
              x="292"
              y={y - 5}
              width={12 + i * 5}
              height="4"
              rx="2"
              fill="#979797"
            />
          </g>
        ))}
        <text x="160" y="247" fill="#989898" fontSize="8">
          INGESTIFY / SAMPLE DOCUMENT
        </text>
        <rect
          x="151"
          y={mode === 1 ? 145 : 70}
          width="184"
          height={mode === 1 ? 82 : 159}
          rx="4"
          stroke={`url(#${id}-spectrum)`}
          strokeWidth="1.5"
          strokeDasharray="5 3"
          fill="#8b8b8b"
          fillOpacity=".04"
          className={styles.detectionBox}
        />
        <g className={styles.scanLine}>
          <rect
            x="138"
            y="46"
            width="210"
            height="42"
            fill={`url(#${id}-scan)`}
          />
          <path
            d="M138 88H348"
            stroke={`url(#${id}-spectrum)`}
            strokeWidth="2"
          />
        </g>
      </g>
      <g className={styles.floatingBadge}>
        <rect
          x="315"
          y="53"
          width="108"
          height="29"
          rx="14.5"
          fill="#2c2c2c"
          stroke="#6a6a6a"
        />
        <circle cx="331" cy="67" r="3" fill="#bcbcbc" />
        <text x="342" y="71" fill="#e5e5e5" fontSize="9">
          {mode === 1 ? "Tables preserved" : "Structure detected"}
        </text>
      </g>
      <g>
        <rect
          x="52"
          y="215"
          width="122"
          height="34"
          rx="8"
          fill="#2d2d2d"
          stroke="#6a6a6a"
        />
        <text x="67" y="236" fill="#d7d7d7" fontSize="10">
          PDF → Markdown
        </text>
      </g>
    </>
  );
}

function AudioArtwork({ id }: { id: string }) {
  return (
    <>
      <defs>
        <SpectrumGradient id={`${id}-wave`} />
      </defs>
      <rect
        x="35"
        y="48"
        width="410"
        height="202"
        rx="14"
        fill="#ffffff"
        fillOpacity=".035"
        stroke="#ffffff"
        strokeOpacity=".12"
      />
      <text x="55" y="73" fill="#a1a1a1" fontSize="9" letterSpacing="2">
        TEAM CONVERSATION
      </text>
      <circle
        cx="420"
        cy="69"
        r="3"
        fill="#c0c0c0"
        className={styles.statusPulse}
      />
      {[108, 149, 190].map((y) => (
        <path key={y} d={`M55 ${y}H425`} stroke="#ffffff" strokeOpacity=".06" />
      ))}
      <g fill={`url(#${id}-wave)`}>
        {Array.from({ length: 53 }, (_, i) => {
          const h = 12 + Math.abs(Math.sin(i * 0.76) * Math.cos(i * 0.27)) * 82;
          return (
            <rect
              key={i}
              x={55 + i * 7}
              y={149 - h / 2}
              width="3"
              height={h}
              rx="1.5"
              className={styles.waveBar}
              style={{ "--delay": `${i * -0.09}s` } as CSSProperties}
            />
          );
        })}
      </g>
      <g className={styles.playhead}>
        <path d="M68 88V206" stroke="#e1e1e1" strokeWidth="1.5" />
        <circle cx="68" cy="89" r="4" fill="#e1e1e1" />
      </g>
      <text x="55" y="226" fill="#9e9e9e" fontSize="8" fontFamily="monospace">
        00:00
      </text>
      <text x="402" y="226" fill="#9e9e9e" fontSize="8" fontFamily="monospace">
        00:08
      </text>
      <g className={styles.floatingBadge}>
        <rect
          x="94"
          y="235"
          width="290"
          height="37"
          rx="9"
          fill="#303030"
          stroke="#6a6a6a"
        />
        <text x="110" y="258" fill="#dbdbdb" fontSize="11">
          “Let’s turn our recordings into knowledge.”
        </text>
      </g>
    </>
  );
}

function ImageArtwork({ id, mode }: { id: string; mode: number }) {
  return (
    <>
      <defs>
        <SpectrumGradient id={`${id}-spectrum`} />
        <linearGradient id={`${id}-studio`} x2="0" y2="1">
          <stop stopColor="#e7e7e7" />
          <stop offset="1" stopColor="#d2d2d2" />
        </linearGradient>
        <linearGradient id={`${id}-bottle`} x2="1" y2="0">
          <stop stopColor="#545454" />
          <stop offset=".5" stopColor="#8a8a8a" />
          <stop offset="1" stopColor="#505050" />
        </linearGradient>
      </defs>
      <rect
        x="30"
        y="27"
        width="420"
        height="253"
        rx="12"
        fill={`url(#${id}-studio)`}
      />
      <path
        d="M30 197H450V268Q450 280 438 280H42Q30 280 30 268Z"
        fill="#c4c4c4"
      />
      <ellipse
        cx="246"
        cy="244"
        rx="155"
        ry="13"
        fill="#858585"
        opacity=".18"
      />
      <path d="M109 204L246 199V261H109Z" fill="#dfdfdf" />
      <path d="M109 204L141 190H270L246 204Z" fill="#f3f3f3" />
      <path d="M246 204L270 190V247L246 261Z" fill="#c6c6c6" />
      <g className={styles.productBottle}>
        <rect x="161" y="61" width="39" height="25" rx="5" fill="#373737" />
        <path
          d="M153 82Q142 92 142 109V211Q142 222 153 222H208Q219 222 219 211V109Q219 92 208 82Z"
          fill={`url(#${id}-bottle)`}
        />
        <path
          d="M151 110V200"
          stroke="#d6d6d6"
          opacity=".3"
          strokeWidth="3"
          strokeLinecap="round"
        />
        <rect x="151" y="125" width="59" height="63" rx="2" fill="#e9e9e9" />
        <path
          d="M175 139Q185 132 186 142Q176 148 175 139M181 140V152"
          stroke="#7f7f7f"
          fill="none"
        />
        <text
          x="180"
          y="162"
          textAnchor="middle"
          fill="#515151"
          fontSize="8"
          letterSpacing="1"
        >
          BOTANIC
        </text>
        <text
          x="180"
          y="174"
          textAnchor="middle"
          fill="#8d8d8d"
          fontSize="5"
          letterSpacing="1"
        >
          DAILY CARE
        </text>
        <text x="180" y="183" textAnchor="middle" fill="#8d8d8d" fontSize="5">
          250 ml
        </text>
      </g>
      <path
        d="M332 194V97M332 145L306 119M332 168L369 134M332 121L357 94"
        stroke="#6f6f6f"
        strokeWidth="3"
        fill="none"
      />
      <g fill="#7a7a7a">
        <ellipse
          cx="305"
          cy="112"
          rx="12"
          ry="26"
          transform="rotate(-38 305 112)"
        />
        <ellipse
          cx="360"
          cy="91"
          rx="12"
          ry="24"
          transform="rotate(38 360 91)"
        />
        <ellipse
          cx="372"
          cy="135"
          rx="13"
          ry="28"
          transform="rotate(48 372 135)"
        />
        <ellipse
          cx="330"
          cy="91"
          rx="12"
          ry="28"
          transform="rotate(-8 330 91)"
        />
        <ellipse
          cx="303"
          cy="160"
          rx="10"
          ry="22"
          transform="rotate(-48 303 160)"
        />
      </g>
      <path d="M303 189H364L356 240Q332 248 312 240Z" fill="#969696" />
      <ellipse cx="333" cy="189" rx="30" ry="7" fill="#b9b9b9" />
      <ellipse cx="333" cy="189" rx="23" ry="4" fill="#575757" />
      <g transform="rotate(-9 87 217)">
        <rect x="55" y="174" width="59" height="75" rx="2" fill="#f4f4f4" />
        <path
          d="M67 194H101M67 200H95M67 206H100M67 227H92"
          stroke="#b5b5b5"
          strokeWidth="2"
        />
        <circle cx="85" cy="216" r="4" fill="#939393" />
      </g>
      {mode === 0 && (
        <g
          fill="none"
          stroke={`url(#${id}-spectrum)`}
          strokeWidth="1.5"
          className={styles.detectionBox}
        >
          <rect x="132" y="53" width="98" height="178" rx="4" />
          <rect x="285" y="57" width="111" height="192" rx="4" />
          <rect x="46" y="164" width="80" height="92" rx="4" />
          <g fill="#363636" stroke="none">
            <rect x="132" y="40" width="44" height="16" rx="3" />
            <rect x="285" y="44" width="38" height="16" rx="3" />
          </g>
          <g fill="#ebebeb" stroke="none" fontSize="9">
            <text x="140" y="51">
              bottle
            </text>
            <text x="293" y="55">
              plant
            </text>
          </g>
        </g>
      )}
      {mode === 1 && (
        <g
          fill="#9b9b9b"
          fillOpacity=".09"
          stroke={`url(#${id}-spectrum)`}
          strokeWidth="1.5"
          className={styles.detectionBox}
        >
          <rect x="154" y="153" width="53" height="13" rx="2" />
          <rect x="155" y="169" width="51" height="8" rx="1" />
          <rect x="169" y="178" width="23" height="8" rx="1" />
        </g>
      )}
      <path
        d="M42 45V36H53M427 36H439V48M439 259V271H427M54 271H42V259"
        stroke="#ffffff"
        strokeOpacity=".8"
        strokeWidth="2"
        fill="none"
      />
    </>
  );
}

/** Native vector artwork stays crisp on mobile and has no image download cost. */
export function FeatureArtwork({
  slug,
  mode = 0,
}: {
  slug: Feature["slug"];
  mode?: number;
}) {
  const id = useId().replaceAll(":", "");
  return (
    <svg
      className={styles.artwork}
      viewBox="0 0 480 300"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      {slug === "documents" ? (
        <DocumentArtwork id={id} mode={mode} />
      ) : slug === "audio-video" ? (
        <AudioArtwork id={id} />
      ) : (
        <ImageArtwork id={id} mode={mode} />
      )}
    </svg>
  );
}

export function ProductDemo({ feature }: { feature: Feature }) {
  const [mode, setMode] = useState(0);
  const id = useId();
  const demo = DEMOS[feature.slug];
  const InputIcon =
    feature.slug === "documents"
      ? FileText
      : feature.slug === "audio-video"
        ? AudioLines
        : ImageIcon;
  return (
    <figure
      className={styles.demo}
      aria-label={`${feature.name}: interactive illustrative example`}
    >
      <div className={styles.demoChrome}>
        <span className={styles.windowDots} aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
        <span>{demo.label}</span>
        <Sparkles size={14} aria-hidden="true" />
      </div>
      <div className={styles.demoFile}>
        <InputIcon size={13} aria-hidden="true" />
        <span>{demo.file}</span>
        <span>INPUT</span>
      </div>
      <div className={styles.demoStage}>
        <FeatureArtwork slug={feature.slug} mode={mode} />
      </div>
      <div className={styles.demoProcessing}>
        <span className={styles.processingLine} />
        <span>
          <Layers size={14} aria-hidden="true" />
          {feature.figure.operation}
          <ArrowDown size={13} aria-hidden="true" />
        </span>
        <span className={styles.processingLine} />
      </div>
      <div className={styles.demoResult}>
        <div
          className={styles.demoTabs}
          role="group"
          aria-label="Example output format"
        >
          {demo.modes.map((name, index) => (
            <button
              key={name}
              type="button"
              aria-pressed={mode === index}
              aria-controls={`${id}-output`}
              onClick={() => setMode(index)}
            >
              {name}
            </button>
          ))}
          <span>
            <Check size={12} aria-hidden="true" /> RESULT
          </span>
        </div>
        <pre
          id={`${id}-output`}
          className={styles.demoOutput}
          tabIndex={0}
          aria-label="Example output"
          aria-live="polite"
          aria-atomic="true"
        >
          <code>{demo.results[mode]}</code>
        </pre>
      </div>
      <figcaption>
        <span className={styles.exampleDot} aria-hidden="true" />
        Illustrative example · explore the output formats
        <ArrowUpRight size={12} aria-hidden="true" />
      </figcaption>
    </figure>
  );
}

export function PlatformArtwork() {
  const id = useId().replaceAll(":", "");
  return (
    <div className={styles.platformArtwork} aria-hidden="true">
      <div className={styles.platformFiles}>
        <span>PDF</span>
        <span>MP3</span>
        <span>PNG</span>
      </div>
      <svg viewBox="0 0 480 170" fill="none" className={styles.platformLines}>
        <defs>
          <SpectrumGradient id={`${id}-spectrum`} />
        </defs>
        <path
          d="M80 0V35Q80 65 110 65H210Q240 65 240 95V170M240 0V170M400 0V35Q400 65 370 65H270Q240 65 240 95V170"
          stroke="#d5d5d5"
        />
        <path
          className={styles.flowPath}
          d="M80 0V35Q80 65 110 65H210Q240 65 240 95V170M240 0V170M400 0V35Q400 65 370 65H270Q240 65 240 95V170"
          stroke={`url(#${id}-spectrum)`}
          strokeWidth="2"
          strokeDasharray="12 160"
        />
      </svg>
      <div className={styles.platformCore}>
        <Layers size={32} strokeWidth={1.4} />
        <span>Ingestify</span>
        <small>ONE PLATFORM. EVERY INPUT.</small>
      </div>
      <div className={styles.platformOutput}>
        <span />
        <code>Structured. Searchable. AI-ready.</code>
      </div>
    </div>
  );
}
