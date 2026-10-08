"use client";

import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";
import { Pause, Play } from "lucide-react";
import { PublicHeader } from "@/components/public-header";
import styles from "./features.module.css";

/** Keep the content server-rendered; only motion controls need hydration. */
export function FeatureExperience({
  children,
  slug,
  accent,
}: {
  children: ReactNode;
  slug: string;
  accent?: string;
}) {
  const [paused, setPaused] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const preference = matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setPaused(preference.matches);
    update();
    preference.addEventListener("change", update);
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          entry.target.setAttribute(
            "data-in-view",
            String(entry.isIntersecting),
          );
        });
      },
      { threshold: 0.08 },
    );
    root.current
      ?.querySelectorAll("main > section")
      .forEach((section) => observer.observe(section));
    return () => {
      preference.removeEventListener("change", update);
      observer.disconnect();
    };
  }, []);

  return (
    <div
      ref={root}
      className={styles.page}
      lang="en"
      data-feature={slug}
      data-motion={paused ? "paused" : "running"}
      style={{ "--accent": accent || "#111" } as CSSProperties}
    >
      <a href="#feature-content" className={styles.skip}>
        Skip to content
      </a>
      <PublicHeader
        motionControl={
          <button
            type="button"
            onClick={() => setPaused(!paused)}
            aria-pressed={paused}
            aria-label={paused ? "Resume motion" : "Pause motion"}
          >
            <span>{paused ? "Resume motion" : "Pause motion"}</span>
            {paused ? (
              <Play size={15} aria-hidden="true" />
            ) : (
              <Pause size={15} aria-hidden="true" />
            )}
          </button>
        }
      />
      {children}
    </div>
  );
}
