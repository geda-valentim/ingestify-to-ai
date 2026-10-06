"use client";
import { useId, useState } from "react";

function Spectrum({ id }: { id: string }) {
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
export function SpectralLines({
  variant = "hero",
}: {
  variant?: "hero" | "orbit" | "rail";
}) {
  const id = useId();
  return (
    <svg
      className={`spectral-lines spectral-${variant}`}
      viewBox="0 0 1440 700"
      fill="none"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <defs>
        <Spectrum id={id} />
      </defs>
      {(variant === "orbit"
        ? [
            "M-80 350 C200 -150 1250 -150 1500 350 C1200 830 200 830 -80 350",
            "M150 -50 C1200 10 1200 700 200 760",
            "M1000 -100 C-150 250 700 900 1500 400",
          ]
        : [
            "M-100 570 C260 570 340 240 730 360 S1130 680 1550 370",
            "M-100 580 C260 580 350 250 735 370 S1140 690 1550 380",
            "M-100 590 C260 590 360 260 740 380 S1150 700 1550 390",
          ]
      ).map((d, i) => (
        <g key={d}>
          <path
            d={d}
            stroke={`url(#${id})`}
            strokeWidth={i ? ".6" : "1.4"}
            opacity={i ? ".3" : ".7"}
          />
          <path
            className="spectral-pulse"
            d={d}
            stroke={`url(#${id})`}
            strokeWidth="2"
            strokeDasharray="14 1900"
            style={{ animationDelay: `${-i * 3}s` }}
          />
        </g>
      ))}
    </svg>
  );
}
export function OperationDiagram({ mode }: { mode: number }) {
  const id = useId();
  return (
    <svg
      className="operation-svg"
      viewBox="0 0 1000 480"
      role="img"
      aria-label={
        [
          "A document becomes structured Markdown",
          "A recording becomes a timestamped transcript",
          "Image regions become extracted text",
        ][mode]
      }
    >
      <defs>
        <Spectrum id={id} />
        <pattern
          id={`${id}-grid`}
          width="32"
          height="32"
          patternUnits="userSpaceOnUse"
        >
          <circle cx="1" cy="1" r=".7" fill="#c8c8c8" />
        </pattern>
      </defs>
      <rect width="1000" height="480" fill={`url(#${id}-grid)`} opacity=".5" />
      <g className="diagram-input" fill="#fff" stroke="#b9b9b9" strokeWidth="1">
        <rect x="85" y="108" width="245" height="282" rx="4" />
        <rect x="96" y="97" width="245" height="282" rx="4" />
      </g>
      <text x="122" y="133" className="svg-micro">
        {
          [
            "SOURCE / REPORT.PDF",
            "SOURCE / RECORDING.WAV",
            "SOURCE / RECEIPT.PNG",
          ][mode]
        }
      </text>
      {mode === 0 ? (
        <g stroke="#222" fill="none">
          <path d="M124 176H255 M124 190H212" strokeWidth="8" />
          <path
            d="M124 224H306 M124 235H295 M124 246H305"
            stroke="#aaa"
            strokeWidth="3"
          />
          <rect x="124" y="274" width="182" height="66" stroke="#ccc" />
          <path d="M124 296H306 M124 318H306 M208 274V340" stroke="#ccc" />
        </g>
      ) : mode === 1 ? (
        <g>
          {Array.from({ length: 36 }, (_, i) => (
            <line
              className="wave-bar"
              key={i}
              x1={121 + i * 5.2}
              x2={121 + i * 5.2}
              y1={238 - Math.abs(Math.sin(i * 1.3) * Math.cos(i * 0.23)) * 62}
              y2={238 + Math.abs(Math.sin(i * 1.3) * Math.cos(i * 0.23)) * 62}
              stroke="#171717"
              strokeWidth="2.5"
              style={{ animationDelay: `${-i * 0.12}s` }}
            />
          ))}
          <text x="125" y="338" className="svg-micro">
            00:00 ────────── 00:06
          </text>
        </g>
      ) : (
        <g stroke="#aaa" fill="none">
          <path
            d="M124 174H260 M124 196H292 M124 218H245 M124 240H294"
            strokeWidth="5"
          />
          <rect
            className="scan-region"
            x="115"
            y="286"
            width="202"
            height="53"
            stroke={`url(#${id})`}
            strokeWidth="2"
          />
          <text
            x="129"
            y="318"
            fill="#111"
            stroke="none"
            fontSize="18"
            fontFamily="monospace"
          >
            TOTAL 42.00
          </text>
        </g>
      )}
      <path
        d="M342 238 H425 C467 238 467 170 504 170 S541 238 586 238 H645"
        fill="none"
        stroke="#ddd"
      />
      <path
        className="diagram-route"
        d="M342 238 H425 C467 238 467 170 504 170 S541 238 586 238 H645"
        fill="none"
        stroke={`url(#${id})`}
        strokeWidth="2"
      />
      <circle cx="504" cy="170" r="26" fill="#fff" stroke={`url(#${id})`} />
      <path d="M493 170H515 M504 159V181" stroke="#222" />
      <text x="469" y="220" className="svg-micro">
        INGESTIFY
      </text>
      <g className="diagram-output">
        <rect
          x="647"
          y="85"
          width="270"
          height="300"
          rx="4"
          fill="#fff"
          stroke="#b9b9b9"
        />
        <text x="673" y="121" className="svg-micro">
          {["OUTPUT / MARKDOWN", "OUTPUT / TRANSCRIPT", "OUTPUT / OCR"][mode]}
        </text>
        {mode === 0 ? (
          <g fontFamily="monospace" fill="#222" fontSize="17">
            <text x="673" y="177">
              # Report
            </text>
            <text x="673" y="216" fill="#777">
              | Item | Value |
            </text>
            <text x="673" y="244" fill="#777">
              | ———— | ————— |
            </text>
            <text x="673" y="272">
              | Total | 42.00 |
            </text>
          </g>
        ) : mode === 1 ? (
          <g fontFamily="monospace">
            <text x="673" y="178" fontSize="13" fill="#888">
              00:00 → 00:03
            </text>
            <text x="673" y="205" fontSize="16">
              Start with the file.
            </text>
            <text x="673" y="257" fontSize="13" fill="#888">
              00:03 → 00:06
            </text>
            <text x="673" y="284" fontSize="16">
              Build something new.
            </text>
          </g>
        ) : (
          <g fontFamily="monospace">
            <text x="673" y="188" fontSize="22">
              TOTAL 42.00
            </text>
            <path d="M673 220H886" stroke="#ddd" />
            <text x="673" y="252" fontSize="14" fill="#777">
              Text + image regions
            </text>
            <text x="673" y="284" fontSize="14" fill="#777">
              Ready for your workflow
            </text>
          </g>
        )}
        <circle
          className="diagram-status"
          cx="680"
          cy="347"
          r="3"
          fill="#111"
        />
        <text x="693" y="351" className="svg-micro">
          ILLUSTRATIVE RESULT
        </text>
      </g>
    </svg>
  );
}
export function ComputeDiagram({ cloud }: { cloud: boolean }) {
  const id = useId();
  return (
    <svg
      className="compute-svg"
      viewBox="0 0 1000 520"
      role="img"
      aria-label={`Documents and images use local workers. This audio example uses ${cloud ? "Modal" : "local transcription"}.`}
    >
      <defs>
        <Spectrum id={id} />
      </defs>
      <g fill="none" stroke="#333">
        <path d="M0 80H1000 M0 440H1000 M80 0V520 M920 0V520" />
        <circle cx="500" cy="250" r="200" />
        <circle cx="500" cy="250" r="150" strokeDasharray="2 8" />
      </g>
      <g
        className="compute-small"
        fontFamily="monospace"
        fontSize="13"
        fill="#aaa"
      >
        <text x="91" y="67">
          EXECUTION / YOUR CONFIGURATION
        </text>
        <text x="91" y="469">
          ONE AUDIO JOB. ONE DESTINATION.
        </text>
      </g>
      <rect
        x="403"
        y="98"
        width="194"
        height="76"
        rx="3"
        fill="#111"
        stroke="#666"
      />
      <text
        x="500"
        textAnchor="middle"
        y="142"
        fill="#fff"
        fontSize="16"
        fontFamily="monospace"
      >
        audio.wav
      </text>
      <path
        d="M500 174V215Q500 245 460 245H269V315"
        stroke="#444"
        fill="none"
      />
      <path
        d="M500 174V215Q500 245 540 245H731V315"
        stroke="#444"
        fill="none"
      />
      <path
        className="compute-route"
        key={String(cloud)}
        d={
          cloud
            ? "M500 174V215Q500 245 540 245H731V315"
            : "M500 174V215Q500 245 460 245H269V315"
        }
        stroke={`url(#${id})`}
        strokeWidth="3"
        fill="none"
      />
      <g fill="#101010" stroke="#777">
        <rect x="158" y="315" width="222" height="88" rx="3" />
        <rect x="620" y="315" width="222" height="88" rx="3" />
      </g>
      <text
        className="compute-node"
        x="269"
        y="354"
        textAnchor="middle"
        fill="#fff"
        fontSize="18"
      >
        Local workers
      </text>
      <text
        className="compute-node"
        x="731"
        y="354"
        textAnchor="middle"
        fill="#fff"
        fontSize="18"
      >
        Modal
      </text>
      <text className="compute-small" x="205" y="379" fill="#999" fontSize="12">
        Documents · images · audio
      </text>
      <text className="compute-small" x="666" y="379" fill="#999" fontSize="12">
        Optional transcription
      </text>
      <circle cx={cloud ? 818 : 356} cy="335" r="4" fill={`url(#${id})`} />
    </svg>
  );
}

const lakeAdapters = [
  { name: "MinIO", label: "SELF-HOSTED", destination: "your MinIO bucket" },
  { name: "Amazon S3", label: "AWS", destination: "your Amazon S3 bucket" },
  {
    name: "Google Cloud Storage",
    label: "GCP",
    destination: "your Google Cloud Storage bucket",
  },
  {
    name: "Azure Blob",
    label: "MICROSOFT AZURE",
    destination: "your Azure Blob container",
  },
];

export function LakeDeliveryDiagram() {
  const id = useId();
  const [selected, setSelected] = useState(0);
  return (
    <div className="lake-flow">
      <div className="lake-pipeline">
        <svg
          className="lake-connections"
          viewBox="0 0 1000 120"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <defs>
            <linearGradient
              id={id}
              gradientUnits="userSpaceOnUse"
              x1="166"
              y1="60"
              x2="500"
              y2="60"
            >
              <stop stopColor="#f06b91" />
              <stop offset=".25" stopColor="#eeb94a" />
              <stop offset=".5" stopColor="#6dc7ad" />
              <stop offset=".75" stopColor="#6e9fe9" />
              <stop offset="1" stopColor="#b889df" />
            </linearGradient>
          </defs>
          <path
            d="M166 60H500"
            stroke={`url(#${id})`}
            strokeWidth="2"
            className="diagram-route"
          />
          <path
            d="M500 60H1000"
            stroke="#999"
            strokeWidth="1.5"
            strokeDasharray="5 7"
          />
        </svg>
        <ol>
          <li>
            <span className="lake-node">
              <svg viewBox="0 0 48 48" aria-hidden="true">
                <path d="M13 7h16l7 7v27H13zM29 7v8h7M19 23h11M19 29h11M19 35h7" />
              </svg>
            </span>
            <span className="lake-state">AVAILABLE</span>
            <h3>Source files</h3>
            <p>
              Documents, images
              <br />
              and recordings
            </p>
          </li>
          <li>
            <span className="lake-node">
              <svg viewBox="0 0 48 48" aria-hidden="true">
                <path d="m5 16 19-10 19 10-19 10zM5 24l19 10 19-10M5 32l19 10 19-10" />
              </svg>
            </span>
            <span className="lake-state">AVAILABLE</span>
            <h3>Conversion API</h3>
            <p>
              Markdown, text,
              <br />
              transcripts and metadata
            </p>
          </li>
          <li className="lake-planned">
            <span className="lake-node">
              <svg viewBox="0 0 48 48" aria-hidden="true">
                <ellipse cx="24" cy="10" rx="17" ry="6" />
                <path d="M7 10v27c0 8 34 8 34 0V10M7 23c0 8 34 8 34 0" />
              </svg>
            </span>
            <span className="lake-state">PLANNED DELIVERY</span>
            <h3>Your Data Lake</h3>
            <p>
              Your destination.
              <br />
              Your choice of adapter.
            </p>
          </li>
        </ol>
      </div>
      <div
        className="lake-adapters"
        role="group"
        aria-label="Preview a planned Data Lake adapter"
      >
        <svg
          className="lake-branches"
          viewBox="0 0 48 292"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <defs>
            <Spectrum id={`${id}-branches`} />
          </defs>
          {lakeAdapters
            .map((adapter, index) => ({ ...adapter, index }))
            .sort(
              (a, b) =>
                Number(a.index === selected) - Number(b.index === selected),
            )
            .map(({ name, index }) => (
              <path
                key={name}
                d={`M0 44H12Q20 44 20 ${index === 0 ? 36 : 52}V${32 + index * 76}H48`}
                fill="none"
                stroke={selected === index ? `url(#${id}-branches)` : "#ddd"}
                strokeWidth={selected === index ? 2 : 1}
              />
            ))}
        </svg>
        {lakeAdapters.map((adapter, index) => (
          <button
            key={adapter.name}
            type="button"
            aria-pressed={selected === index}
            aria-controls="lake-adapter-preview"
            onClick={() => setSelected(index)}
          >
            <span>{adapter.label}</span>
            <strong>{adapter.name}</strong>
            <span className="lake-adapter-dot" aria-hidden="true" />
          </button>
        ))}
      </div>
      <p
        className="lake-adapter-preview"
        id="lake-adapter-preview"
        aria-live="polite"
        aria-atomic="true"
      >
        <span>PLANNED ADAPTER</span>
        <strong>{lakeAdapters[selected].name}</strong>
        <span>Converted data → {lakeAdapters[selected].destination}.</span>
      </p>
    </div>
  );
}
