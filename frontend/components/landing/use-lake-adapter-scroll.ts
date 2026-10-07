"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const HEADER_HEIGHT = 72;

/** Keep the selected branch aligned with the adapter passing the reading line. */
export function useLakeAdapterScroll() {
  const adaptersRef = useRef<HTMLDivElement>(null);
  const [selected, setSelected] = useState(0);

  const selectAdapter = useCallback((index: number) => {
    setSelected(index);
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const button = adaptersRef.current?.querySelectorAll("button")[index];
    if (!button) return;
    const bounds = button.getBoundingClientRect();
    scrollTo({
      top:
        scrollY +
        bounds.top +
        bounds.height / 2 -
        (innerHeight + HEADER_HEIGHT) / 2,
      behavior: "instant",
    });
  }, []);

  useEffect(() => {
    const adapters = adaptersRef.current;
    if (!adapters) return;
    const preference = matchMedia("(prefers-reduced-motion: reduce)");
    let frame = 0;
    const update = () => {
      frame = 0;
      if (preference.matches) return;
      const bounds = adapters.getBoundingClientRect();
      if (bounds.bottom <= HEADER_HEIGHT || bounds.top >= innerHeight) return;
      const marker = (innerHeight + HEADER_HEIGHT) / 2;
      let closest = 0;
      let distance = Infinity;
      adapters.querySelectorAll("button").forEach((button, index) => {
        const box = button.getBoundingClientRect();
        const nextDistance = Math.abs(box.top + box.height / 2 - marker);
        if (nextDistance < distance) {
          closest = index;
          distance = nextDistance;
        }
      });
      setSelected(closest);
    };
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };
    const observer = new ResizeObserver(schedule);
    observer.observe(adapters);
    schedule();
    addEventListener("scroll", schedule, { passive: true });
    addEventListener("resize", schedule);
    preference.addEventListener("change", schedule);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      removeEventListener("scroll", schedule);
      removeEventListener("resize", schedule);
      preference.removeEventListener("change", schedule);
    };
  }, []);

  return { adaptersRef, selected, selectAdapter };
}
