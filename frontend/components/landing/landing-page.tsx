"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { ArrowDown, ArrowUpRight, Github, Pause, Play } from "lucide-react";
import { useAuthStore } from "@/lib/store/auth";
import { chapterProgress, timelineAt } from "./timeline";
import { chapters, GITHUB } from "./content";
import "./landing.css";
import { LandingSections, useLandingMotion } from "./landing-sections";
import { Brand } from "@/components/brand";
import { SpectralLines } from "./landing-svg";

function frame(chapter: number, end = false) {
  return `/landing/storyboard/white-rainbow/scene-0${chapter + 1}-${end ? (chapter === 4 ? "end-v2" : "end") : "start"}.png`;
}
function ResultExample({ chapter }: { chapter: number }) {
  if (chapter === 1)
    return (
      <pre className="landing-result">
        <span>MARKDOWN · EXAMPLE</span>
        {"# Report\n\n| Item | Value |\n| --- | --- |\n| Total | 42.00 |"}
      </pre>
    );
  if (chapter === 2)
    return (
      <div className="landing-result">
        <span>TRANSCRIPT · EXAMPLE</span>
        <p>
          <time>00:00 → 00:03</time> Let’s start with the document.
        </p>
        <p>
          <time>00:03 → 00:06</time> The result goes into the application.
        </p>
      </div>
    );
  if (chapter === 3)
    return (
      <div className="landing-result">
        <span>OCR · EXAMPLE</span>
        <p>TOTAL 42.00</p>
        <small>Extracted text + image regions</small>
      </div>
    );
  return null;
}
export function LandingPage() {
  useLandingMotion();
  const [motionPaused, setMotionPaused] = useState(false);
  const story = useRef<HTMLElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  const desiredTime = useRef(0);
  const [position, setPosition] = useState(() => timelineAt(0));
  const [staticMode, setStaticMode] = useState(false);
  const [preferencesReady, setPreferencesReady] = useState(false);
  const [mediaReady, setMediaReady] = useState(false);
  const [mediaFailed, setMediaFailed] = useState(false);
  const signedIn = useAuthStore((s) => s._hasHydrated && !!s.token && !!s.user);
  const current = chapters[position.chapter];
  const closing = position.segment === 14 && !position.result;
  const compact = position.bridge || closing;
  const transition =
    position.segment === 3
      ? {
          eyebrow: "NEXT INPUT · AUDIO",
          title: "Now, a recording.",
        }
      : position.segment === 5
        ? { eyebrow: "NEXT INPUT · IMAGE", title: "Now, an image." }
        : closing
          ? { eyebrow: current.eyebrow, title: "Build your data flow." }
          : null;

  useEffect(() => {
    const preference = matchMedia("(prefers-reduced-motion: reduce)");
    const connection = (
      navigator as Navigator & { connection?: { saveData?: boolean } }
    ).connection;
    const update = () =>
      setStaticMode(
        preference.matches || !!connection?.saveData || innerHeight < 620,
      );
    update();
    setPreferencesReady(true);
    preference.addEventListener("change", update);
    addEventListener("resize", update);
    return () => {
      preference.removeEventListener("change", update);
      removeEventListener("resize", update);
    };
  }, []);
  const seek = useCallback(() => {
    const media = video.current;
    if (
      !media ||
      media.readyState < 2 ||
      media.seeking ||
      !Number.isFinite(media.duration)
    )
      return;
    const target = Math.min(
      desiredTime.current,
      Math.max(0, media.duration - 0.04),
    );
    if (Math.abs(media.currentTime - target) > 0.025)
      media.currentTime = target;
  }, []);
  useEffect(() => {
    setMediaReady(false);
  }, [staticMode]);
  useEffect(() => {
    if (staticMode) return;
    let raf = 0;
    const update = () => {
      raf = 0;
      const el = story.current;
      if (!el) return;
      const next = timelineAt(
        (72 - el.getBoundingClientRect().top) /
          Math.max(1, el.offsetHeight - (innerHeight - 72)),
      );
      desiredTime.current = next.time;
      setPosition((previous) =>
        previous.segment === next.segment && previous.result === next.result
          ? previous
          : next,
      );
      seek();
    };
    const schedule = () => {
      if (!raf) raf = requestAnimationFrame(update);
    };
    update();
    addEventListener("scroll", schedule, { passive: true });
    addEventListener("resize", schedule);
    return () => {
      cancelAnimationFrame(raf);
      removeEventListener("scroll", schedule);
      removeEventListener("resize", schedule);
    };
  }, [staticMode, seek]);
  function goToChapter(index: number) {
    const el = story.current;
    if (!el) return;
    scrollTo({
      top:
        scrollY +
        el.getBoundingClientRect().top -
        72 +
        chapterProgress(index) * (el.offsetHeight - (innerHeight - 72)),
      behavior: "auto",
    });
  }

  return (
    <div
      className="landing"
      lang="en"
      data-motion={motionPaused ? "paused" : "running"}
    >
      <a className="landing-skip" href="#operacoes">
        Skip the introduction
      </a>
      <header className="landing-header">
        <Link className="landing-brand" href="/" aria-label="Ingestify home">
          <Brand />
        </Link>
        <nav aria-label="Main navigation">
          <button
            className="motion-toggle"
            onClick={() => setMotionPaused(!motionPaused)}
            aria-pressed={motionPaused}
            aria-label={motionPaused ? "Resume motion" : "Pause motion"}
          >
            <span>{motionPaused ? "Resume motion" : "Pause motion"}</span>
            {motionPaused ? <Play size={15} /> : <Pause size={15} />}
          </button>
          <a href="#operacoes">Platform</a>
          <Link href="/agents" className="landing-agents">
            Agents
          </Link>
          <Link href="/docs">Docs</Link>
          <a
            href={GITHUB}
            className="landing-github"
            aria-label="Ingestify on GitHub"
          >
            <Github size={18} />
          </a>
          <Link
            className="landing-button small"
            href={signedIn ? "/dashboard" : "/login"}
          >
            {signedIn ? "Open dashboard" : "Sign in"}
            <ArrowUpRight size={14} />
          </Link>
        </nav>
      </header>
      <main>
        <h1 className="sr-only">Data Engineering and AI-ready conversion</h1>
        <noscript>
          <style>{`.landing-story{height:calc(100svh - 72px)}.landing-story-bottom nav{display:none}`}</style>
        </noscript>
        {!staticMode ? (
          <section
            className="landing-story"
            ref={story}
            aria-label="Explore Ingestify as you scroll"
          >
            <div className="landing-stage">
              <SpectralLines variant="hero" />
              <div className="landing-film" aria-hidden="true">
                {/* Full frame preserves both sides of the transformation on mobile. */}
                <Image
                  src={frame(
                    mediaReady ? 0 : position.chapter,
                    !mediaReady && position.result,
                  )}
                  alt=""
                  width={1672}
                  height={941}
                  sizes="100vw"
                  priority
                />
                {preferencesReady && !mediaFailed && (
                  <video
                    ref={video}
                    muted
                    playsInline
                    preload="auto"
                    tabIndex={-1}
                    className={mediaReady ? "is-ready" : ""}
                    onLoadedData={() => {
                      setMediaReady(true);
                      seek();
                    }}
                    onSeeked={seek}
                    onError={(event) => {
                      // A rejected <source> can bubble here while the browser
                      // successfully loads the next compatible source.
                      if (event.target !== event.currentTarget) return;
                      setMediaFailed(true);
                      setMediaReady(false);
                    }}
                  >
                    <source
                      src="/landing/film/ingestify-scroll-mobile.mp4"
                      media="(max-width: 767px)"
                      type="video/mp4"
                    />
                    <source
                      src="/landing/film/ingestify-scroll.mp4"
                      type="video/mp4"
                    />
                  </video>
                )}
              </div>
              <div
                className={`landing-story-copy ${compact ? "is-bridge" : ""} ${closing ? "is-closing" : ""} ${position.result && position.chapter >= 1 && position.chapter <= 3 ? "has-result" : ""}`}
                data-chapter={position.chapter}
                data-segment={position.segment}
              >
                <p className="landing-eyebrow">
                  {position.future
                    ? "PLANNED / DATA LAKE DELIVERY"
                    : (transition?.eyebrow ?? current.eyebrow)}
                </p>
                <h2>{transition?.title ?? current.title}</h2>
                {!compact && (
                  <>
                    <p className="landing-story-description">{current.body}</p>
                    <div className="landing-story-actions">
                      <a
                        className={`landing-text-link ${position.chapter === 0 ? "hero-action" : ""}`}
                        href={current.href}
                      >
                        {current.action}
                        <ArrowUpRight size={16} />
                      </a>
                      {position.chapter === 0 && (
                        <a className="landing-text-link" href={GITHUB}>
                          <Github size={16} />
                          View source
                        </a>
                      )}
                    </div>
                    {current.note && (
                      <p className="landing-note">{current.note}</p>
                    )}
                    {position.result && (
                      <ResultExample chapter={position.chapter} />
                    )}
                  </>
                )}
              </div>
              <div className="landing-story-bottom">
                <span className="landing-scroll-hint">
                  <ArrowDown size={14} /> Scroll to transform
                </span>
                <nav aria-label="Introduction chapters">
                  {chapters.map((c, i) => (
                    <button
                      key={c.name}
                      onClick={() => goToChapter(i)}
                      aria-label={`Scene ${i + 1}: ${c.name}`}
                      aria-current={position.chapter === i ? "step" : undefined}
                    >
                      <span>{String(i + 1).padStart(2, "0")}</span>
                      <span className="chapter-name">{c.name}</span>
                    </button>
                  ))}
                </nav>
                <a href="#operacoes">
                  Skip <ArrowDown size={13} />
                </a>
              </div>
              <span className="landing-film-caption">
                Illustrative workflow
              </span>
            </div>
          </section>
        ) : (
          <section className="landing-static" aria-label="Discover Ingestify">
            {chapters.map((c, i) => (
              <article key={c.name}>
                <div>
                  <p className="landing-eyebrow">{c.eyebrow}</p>
                  <h2>{c.title}</h2>
                  <p>{c.body}</p>
                  {c.note && <p className="landing-note">{c.note}</p>}
                  <a className="landing-text-link" href={c.href}>
                    {c.action}
                    <ArrowUpRight size={16} />
                  </a>
                  <ResultExample chapter={i} />
                </div>
                <Image
                  width={1672}
                  height={941}
                  sizes="(max-width:767px) 100vw, 65vw"
                  src={frame(i, true)}
                  alt={`Illustration: ${c.title}`}
                  loading={i ? "lazy" : "eager"}
                />
              </article>
            ))}
          </section>
        )}

        <LandingSections signedIn={signedIn} />
      </main>
      <footer className="landing-footer">
        <a href="#" className="landing-brand" aria-label="Ingestify home">
          <Brand />
        </a>
        <p>Data Engineering + AI-ready conversion.</p>
        <nav aria-label="Footer links">
          <Link href="/agents" className="landing-agents">
            Agents
          </Link>
          <Link href="/docs">Docs</Link>
          <a href={GITHUB}>GitHub</a>
          <Link href="/login">Sign in</Link>
        </nav>
      </footer>
    </div>
  );
}
