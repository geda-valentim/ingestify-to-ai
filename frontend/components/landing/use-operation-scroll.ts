"use client";

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";

type Mode = "flow" | "pinned";
const PIN_TOP = 92;

/** Scroll selects the visible operation; buttons navigate to that same position. */
export function useOperationScroll(count: number) {
  const containerRef = useRef<HTMLDivElement>(null);
  const pickerRef = useRef<HTMLDivElement>(null);
  const [operation, setOperation] = useState(0);
  const [mode, setMode] = useState<Mode>("flow");
  const activeRef = useRef(0);
  const modeRef = useRef<Mode>("flow");
  const travelRef = useRef(0);
  const restoreRef = useRef(false);

  const activate = useCallback((index: number) => {
    if (activeRef.current === index) return;
    activeRef.current = index;
    setOperation(index);
  }, []);

  const selectOperation = useCallback(
    (index: number) => {
      const container = containerRef.current;
      if (!container) return;
      const next = Math.max(0, Math.min(count - 1, index));
      activate(next);
      if (modeRef.current === "pinned") {
        scrollTo({
          top:
            scrollY +
            container.getBoundingClientRect().top -
            PIN_TOP +
            ((next + 0.5) / count) * travelRef.current,
          behavior: "instant",
        });
      } else {
        const panel =
          container.querySelectorAll<HTMLElement>(".operation-canvas")[next];
        if (!panel) return;
        const pickerHeight =
          innerWidth < 768 ? (pickerRef.current?.offsetHeight ?? 0) : 0;
        scrollTo({
          top:
            scrollY +
            panel.getBoundingClientRect().top -
            PIN_TOP -
            pickerHeight,
          behavior: "instant",
        });
      }
    },
    [activate, count],
  );

  // Keep the current operation in view when a resize changes the presentation.
  useLayoutEffect(() => {
    if (!restoreRef.current) return;
    restoreRef.current = false;
    selectOperation(activeRef.current);
  }, [mode, selectOperation]);

  useEffect(() => {
    const container = containerRef.current;
    const picker = pickerRef.current;
    if (!container || !picker) return;
    const panels = Array.from(
      container.querySelectorAll<HTMLElement>(".operation-canvas"),
    );
    const preference = matchMedia("(prefers-reduced-motion: reduce)");
    let frame = 0;
    let measureNeeded = true;
    let disposed = false;
    let wasVisible = false;

    const update = () => {
      frame = 0;
      if (measureNeeded) {
        measureNeeded = false;
        const panelHeight = Math.max(
          picker.offsetHeight,
          ...panels.map((panel) => panel.offsetHeight),
        );
        const nextMode: Mode =
          !preference.matches &&
          innerWidth >= 768 &&
          panelHeight <= innerHeight - PIN_TOP - 24
            ? "pinned"
            : "flow";
        container.style.setProperty(
          "--operation-panel-height",
          `${panelHeight}px`,
        );
        travelRef.current = Math.max(600, innerHeight * 1.6);
        container.style.setProperty(
          "--operation-travel",
          `${travelRef.current}px`,
        );
        if (nextMode !== modeRef.current) {
          const bounds = container.getBoundingClientRect();
          restoreRef.current ||=
            bounds.top < PIN_TOP && bounds.bottom > PIN_TOP;
          modeRef.current = nextMode;
          setMode(nextMode);
          return; // Read positions after React has applied the new layout.
        }
      }
      if (restoreRef.current) {
        restoreRef.current = false;
        selectOperation(activeRef.current);
      }
      const bounds = container.getBoundingClientRect();
      wasVisible = bounds.top <= PIN_TOP + 1 && bounds.bottom > PIN_TOP;
      if (modeRef.current === "pinned") {
        const progress = Math.max(
          0,
          Math.min(1, (PIN_TOP - bounds.top) / travelRef.current),
        );
        container.style.setProperty("--operation-progress", String(progress));
        activate(Math.min(count - 1, Math.floor(progress * count)));
      } else {
        const marker =
          PIN_TOP + (innerWidth < 768 ? picker.offsetHeight : 0) + 24;
        let index = 0;
        panels.forEach((panel, i) => {
          if (panel.getBoundingClientRect().top <= marker) index = i;
        });
        activate(index);
      }
    };
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };
    const measure = () => {
      measureNeeded = true;
      schedule();
    };
    const resize = () => {
      restoreRef.current ||= wasVisible;
      measure();
    };
    const observer = new ResizeObserver(measure);
    panels.forEach((panel) => observer.observe(panel));
    observer.observe(picker);
    measure();
    document.fonts.ready.then(() => {
      if (!disposed) measure();
    });
    addEventListener("scroll", schedule, { passive: true });
    addEventListener("resize", resize);
    preference.addEventListener("change", measure);
    return () => {
      disposed = true;
      observer.disconnect();
      cancelAnimationFrame(frame);
      removeEventListener("scroll", schedule);
      removeEventListener("resize", resize);
      preference.removeEventListener("change", measure);
    };
  }, [activate, count, selectOperation]);

  return { containerRef, pickerRef, operation, mode, selectOperation };
}
